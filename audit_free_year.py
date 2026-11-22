"""Reconcile the archived SEC originals against the accession manifest and emit an HTML audit.
This is a manifest/storage audit, NOT proof that the manifest covers every SEC filing.
"""
import hashlib, html, json, os, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from r2_storage import BUCKET, client

PREFIX = "sec/edgar/free-year/originals/"
PATTERN = re.compile(r"edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt$")
ACCEPT = re.compile(rb"<ACCEPTANCE-DATETIME>(\d{14})")
FORM = re.compile(rb"<FORM-TYPE>\s*(4/A|4)\b", re.I)

def audit():
    lines = Path("edgar-free-year-manifest.txt").read_text().splitlines()
    expected = {}
    for line in lines:
        match = PATTERN.fullmatch(line)
        if not match:
            raise ValueError("Malformed manifest line: " + line)
        cik, accession = match.groups()
        if accession in expected:
            raise ValueError("Duplicate accession: " + accession)
        expected[accession] = cik
    s3 = client()
    objects = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            objects[obj["Key"][len(PREFIX):]] = obj
    missing = sorted(a for a in expected if a + ".txt" not in objects)
    unexpected = sorted(k for k in objects if k[:-4] not in expected)
    problems, timestamps, forms = [], Counter(), Counter()
    checked = 0
    for accession in expected:
        if accession in missing:
            continue
        key = PREFIX + accession + ".txt"
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        with obj["Body"] as body:
            data = body.read()
        checksum = obj.get("Metadata", {}).get("verified-sha256")
        if not checksum or hashlib.sha256(data).hexdigest() != checksum:
            problems.append(accession + ": missing or incorrect SHA-256 metadata")
        if accession.encode() not in data:
            problems.append(accession + ": accession absent from original")
        stamp = ACCEPT.search(data)
        if not stamp:
            problems.append(accession + ": acceptance timestamp missing")
        else:
            try:
                dt = datetime.strptime(stamp.group(1).decode(), "%Y%m%d%H%M%S")
                timestamps[dt.strftime("%Y-%m")] += 1
            except ValueError:
                problems.append(accession + ": invalid acceptance timestamp")
        form = FORM.search(data)
        forms[form.group(1).decode().upper() if form else "unknown"] += 1
        checked += 1
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "manifest-versus-R2 archive; SEC index completeness NOT established",
        "manifest_accessions": len(expected), "archived_objects": len(objects),
        "verified_content": checked, "missing": missing,
        "unexpected_objects": unexpected, "content_problems": problems,
        "accepted_months": dict(sorted(timestamps.items())),
        "forms": dict(forms),
        "price_data_and_research": "not tested by this audit",
        "sec_index_completeness": "NOT VERIFIED: reconcile all Form 4/4-A accession numbers in SEC master indexes before claiming complete year",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/free_year_coverage_audit.json").write_text(json.dumps(report, indent=2))
    status = "PASS: manifest archived" if not missing and not problems else "FAIL: archive gaps"
    rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td>{v:,}</td></tr>" for k,v in sorted(timestamps.items()))
    def li(items):
        return "".join("<li>"+html.escape(x)+"</li>" for x in items[:100]) or "<li>None</li>"
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>EDGAR free-year coverage audit</title>
<style>body{{font:16px system-ui;max-width:900px;margin:36px auto;padding:0 20px;color:#17202a}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:9px;text-align:left}}.warning{{border-left:4px solid #b7791f;padding:12px;background:#fff8e8}}</style>
<h1>EDGAR free-year archive audit</h1><p><strong>{status}</strong></p>
<p>Manifest accessions: {len(expected):,}; archived objects: {len(objects):,}; inspected originals: {checked:,}; missing: {len(missing):,}; checksum/header issues: {len(problems):,}.</p>
<div class="warning"><strong>Not a full-year SEC coverage certification.</strong> This checks every accession in our existing manifest, not whether the manifest contains all Form 4/4-A filings. SEC master-index reconciliation, eligibility classification, insider identity mapping, dividend/split adjustments and benchmark-relative research are outstanding.</div>
<h2>Acceptance timestamp distribution</h2><table><tr><th>Month (Eastern local header date)</th><th>Originals</th></tr>{rows}</table>
<h2>Missing accessions</h2><ul>{li(missing)}</ul><h2>Content problems</h2><ul>{li(problems)}</ul>
<p>Generated {html.escape(report["generated_utc"])}</p></html>"""
    Path("reports/free_year_coverage_audit.html").write_text(page)
    print(json.dumps({k:v for k,v in report.items() if k not in ("missing","content_problems","unexpected_objects")}, indent=2))
    print(f"missing={len(missing)} problems={len(problems)} unexpected={len(unexpected)}")
    if missing or problems:
        raise SystemExit("Archive audit failed; see JSON and HTML reports")

if __name__ == "__main__":
    audit()
