"""Build resumable historical candidate SQLite database from archived SEC quarterly ZIPs."""
import hashlib, json, sqlite3, tempfile
from contextlib import closing
from pathlib import Path
from r2_storage import BUCKET, client
from sec_bulk_importer import import_zip
from sec_archive_scope import QUARTERS, missing_quarters

PREFIX="sec/insider-transactions/quarterly-original-zips/"
OUTKEY="sec/insider-transactions/derived/purchase_candidates.sqlite3"
storage=client()
with tempfile.TemporaryDirectory() as tmp:
    dbpath=Path(tmp)/"purchase_candidates.sqlite3"
    db=sqlite3.connect(str(dbpath))
    db.execute("CREATE TABLE IF NOT EXISTS imported_quarters(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, candidate_rows INTEGER NOT NULL)")
    keys = sorted(
        obj["Key"] for page in storage.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX)
        for obj in page.get("Contents", []) if obj["Key"].removeprefix(PREFIX) in QUARTERS
    )
    missing = missing_quarters(key.removeprefix(PREFIX) for key in keys)
    if missing:
        raise SystemExit(f"Archive incomplete: {len(missing)} missing quarters; first: {missing[:5]}")
    summaries=[]
    for key in keys:
        name=key.rsplit("/",1)[-1]
        obj=storage.get_object(Bucket=BUCKET,Key=key)
        with closing(obj["Body"]) as body:
            payload = body.read()
        sha=hashlib.sha256(payload).hexdigest()
        if sha!=obj.get("Metadata",{}).get("verified-sha256"):
            raise SystemExit(f"Checksum mismatch for {name}")
        count=import_zip(payload,db)
        db.execute("INSERT OR REPLACE INTO imported_quarters VALUES(?,?,?)",(name,sha,count))
        db.commit()
        summaries.append({"quarter":name,"purchase_rows":count})
        print(f"Imported {name}: {count} candidate rows",flush=True)
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    total=db.execute("SELECT COUNT(*) FROM purchase_candidates").fetchone()[0]
    db.close()
    with dbpath.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    storage.upload_file(str(dbpath),BUCKET,OUTKEY,ExtraArgs={"Metadata":{"verified-sha256":digest,"source":"sec-bulk-quarterly"}})
    remote=storage.head_object(Bucket=BUCKET,Key=OUTKEY)
    if remote["ContentLength"]!=dbpath.stat().st_size or remote.get("Metadata",{}).get("verified-sha256")!=digest:
        raise SystemExit("Historical database upload verification failed")
    report={"quarters":len(summaries),"candidate_rows":total,"database_r2_key":OUTKEY,"database_bytes":dbpath.stat().st_size,"database_sha256":digest,"quarter_counts":summaries}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sec_historical_import_summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="quarter_counts"},indent=2))
