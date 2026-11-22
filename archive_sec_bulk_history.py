"""Resumable SEC quarterly insider transactions ZIP archive to Cloudflare R2."""
import hashlib, json, os, time, urllib.error, urllib.request, zipfile, io
from datetime import datetime, timezone
from r2_storage import BUCKET, client
from sec_archive_scope import SEC_CATALOG, catalog_links

PREFIX = "sec/insider-transactions/quarterly-original-zips/"
agent = os.environ["SEC_USER_AGENT"].strip()
if not agent:
    raise SystemExit("SEC_USER_AGENT is required")
storage = client()
results = []
request = urllib.request.Request(SEC_CATALOG, headers={"User-Agent": agent})
with urllib.request.urlopen(request, timeout=90) as response:
    catalog = catalog_links(response.read().decode("utf-8"))
for name, url in sorted(catalog.items()):
    key = PREFIX + name
    try:
        obj = storage.head_object(Bucket=BUCKET, Key=key)
        if obj.get("Metadata", {}).get("verified-sha256"):
            print(f"SKIP previously verified {name}", flush=True)
            results.append({"name":name,"status":"reused","bytes":obj["ContentLength"],"sha256":obj["Metadata"]["verified-sha256"]})
            continue
    except storage.exceptions.ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
            raise
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":agent,"Accept-Encoding":"identity"})
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = response.read()
            if not 1000 < len(payload) < 100_000_000:
                raise ValueError(f"Unexpected ZIP size {len(payload)}")
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if archive.testzip() is not None:
                    raise ValueError("ZIP CRC failure")
                if not any(n.upper().startswith("SUBMISSION") for n in archive.namelist()):
                    raise ValueError("No SUBMISSION table")
            digest = hashlib.sha256(payload).hexdigest()
            storage.put_object(Bucket=BUCKET, Key=key, Body=payload, Metadata={"verified-sha256":digest,"source":"sec-quarterly-insider-transactions"})
            obj = storage.head_object(Bucket=BUCKET, Key=key)
            if obj["ContentLength"] != len(payload) or obj.get("Metadata",{}).get("verified-sha256") != digest:
                raise ValueError("R2 upload verification failed")
            print(f"VERIFIED {name} bytes={len(payload)} sha256={digest}",flush=True)
            results.append({"name":name,"status":"uploaded","bytes":len(payload),"sha256":digest})
            break
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            permanent = isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404)
            if attempt == 4 or permanent:
                print(f"FAILED {name}: {exc}",flush=True)
                results.append({"name":name,"url":url,"status":"failed","error":str(exc)})
                break
            else:
                time.sleep(min(30, 2**attempt * 3))
    time.sleep(0.25)
summary = {"generated_utc":datetime.now(timezone.utc).isoformat(),"expected":len(results),"uploaded":sum(x["status"]=="uploaded" for x in results),"reused":sum(x["status"]=="reused" for x in results),"failed":sum(x["status"]=="failed" for x in results),"quarters":results}
os.makedirs("reports",exist_ok=True)
with open("reports/sec_bulk_archive_manifest.json","w") as f:
    json.dump(summary,f,indent=2)
print(json.dumps({k:v for k,v in summary.items() if k!="quarters"},indent=2),flush=True)
if summary["failed"]:
    raise SystemExit(f'{summary["failed"]} quarters failed; rerun to resume')
