"""Inspect one official SEC quarterly insider-transactions ZIP without bulk ingestion."""
import csv, io, json, os, urllib.request, zipfile
from collections import Counter
from pathlib import Path

URL = "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip"
agent = os.environ.get("SEC_USER_AGENT", "").strip()
if not agent:
    raise SystemExit("SEC_USER_AGENT GitHub Actions secret is required")
req = urllib.request.Request(URL, headers={"User-Agent": agent, "Accept-Encoding": "identity"})
with urllib.request.urlopen(req, timeout=90) as response:
    payload = response.read()
if len(payload) > 100_000_000:
    raise SystemExit("Unexpectedly large sample ZIP")
report = {"source": URL, "compressed_bytes": len(payload), "files": {}, "sample_P": [], "warnings": []}
with zipfile.ZipFile(io.BytesIO(payload)) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        if info.file_size > 200_000_000:
            raise SystemExit("Unexpectedly large member: " + info.filename)
        with z.open(info) as f:
            sample = f.read(4096)
        header = sample.splitlines()[0].decode("utf-8-sig", "replace")
        delimiter = "\\t" if "\\t" in header else ("\\|" if "|" in header else ",")
        # SEC dataset tables use tab-delimited .tsv files.
        delimiter = "\t" if "\t" in header else ("|" if "|" in header else ",")
        columns = next(csv.reader([header], delimiter=delimiter))
        report["files"][info.filename] = {"bytes": info.file_size, "columns": columns}
        upper = [c.upper() for c in columns]
        if "TRANS_CODE" in upper or "TRANS_CODE" in [c.replace(" ", "_") for c in upper]:
            with z.open(info) as f:
                rows = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"), delimiter=delimiter)
                count = 0
                codes = Counter()
                for row in rows:
                    count += 1
                    normalized = {k.upper(): v for k, v in row.items() if k}
                    code = normalized.get("TRANS_CODE", "")
                    codes[code] += 1
                    if code == "P" and len(report["sample_P"]) < 3:
                        report["sample_P"].append(normalized)
                report["files"][info.filename]["row_count"] = count
                report["files"][info.filename]["transaction_codes"] = dict(codes)
report["checks"] = {
    "has_submission_table": any("SUBMISSION" in n.upper() for n in report["files"]),
    "has_nonderivative_table": any("NONDERIV" in n.upper() for n in report["files"]),
    "has_footnote_table": any("FOOTNOTE" in n.upper() for n in report["files"]),
    "has_filing_date": any("FILING_DATE" in [c.upper() for c in v["columns"]] for v in report["files"].values()),
    "has_P_transaction": bool(report["sample_P"]),
}
Path("reports").mkdir(exist_ok=True)
Path("reports/sec_bulk_q3_schema.json").write_text(json.dumps(report, indent=2))
print(json.dumps({k:v for k,v in report.items() if k!="sample_P"},indent=2))
print("Sample P transaction rows:", len(report["sample_P"]))
if not report["checks"]["has_P_transaction"]:
    raise SystemExit("No P transaction rows found; inspect schema")
