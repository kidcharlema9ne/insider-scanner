"""Reconcile Form 4/4-A accession coverage against SEC quarterly master indexes.

No claim of complete SEC coverage is made if any index is inaccessible.
Compare by accession (not CIK) because SEC ownership filing CIK can differ.
"""
import collections
import csv
import html
import io
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
from datetime import date, datetime, timezone

START = date(2025, 11, 6)
END = date(2026, 11, 5)
INDEXES = [(2025, 4), (2026, 1), (2026, 2), (2026, 3), (2026, 4)]
ACCESSION = re.compile(r"(\d{10}-\d{2}-\d{6})\.txt$")
FORMS = {"4", "4/A"}


def parse_master_idx(text):
    records = {}
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            continue
        cik, company, form, filed, path = (x.strip() for x in fields)
        if form not in FORMS:
            continue
        try:
            filing_date = date.fromisoformat(filed)
        except ValueError:
            continue
        if not START <= filing_date <= END:
            continue
        match = ACCESSION.search(path)
        if not match:
            raise ValueError(f"Form 4 index row lacks accession: {line[:180]}")
        accession = match.group(1)
        record = {"accession": accession, "form": form, "filed": filed, "cik": cik, "company": company, "path": path}
        if accession in records:
            prior = records[accession]
            if prior["filed"] != filed or prior["form"] != form:
                raise ValueError(f"Conflicting SEC index filing metadata for accession {accession}: {prior} vs {record}")
            # Ownership filings are indexed under both issuer and reporting-owner CIKs.
            # The accession is one filing, but retain all associated CIK/path records.
            prior.setdefault("additional_index_rows", []).append(record)
            continue
        records[accession] = record
    return records


def load_manifest(path):
    accessions = set()
    for line in Path(path).read_text().splitlines():
        match = ACCESSION.search(line.strip())
        if not match:
            raise ValueError(f"Malformed manifest row: {line[:150]}")
        if match.group(1) in accessions:
            raise ValueError(f"Duplicate manifest accession: {match.group(1)}")
        accessions.add(match.group(1))
    return accessions


def fetch_index(year, quarter):
    url = f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        raise RuntimeError("SEC_USER_AGENT GitHub secret required (identifying contact)")
    request = Request(url, headers={"User-Agent": agent, "Accept-Encoding": "identity"})
    with urlopen(request, timeout=45) as response:
        data = response.read()
    if len(data) < 100 or b"CIK|Company Name|Form Type|Date Filed|Filename" not in data:
        raise ValueError(f"Invalid or blocked SEC master index: {url}")
    return url, data.decode("latin-1")


def reconcile(index_texts, manifest):
    sec = {}
    for key, index_text in index_texts.items():
        rows = parse_master_idx(index_text)
        overlap = set(rows) & set(sec)
        if overlap:
            raise ValueError(f"Repeated SEC accession across indexes: {next(iter(overlap))}")
        sec.update(rows)
    missing = sorted(set(sec) - manifest)
    archived = sorted(set(sec) & manifest)
    unmatched = sorted(manifest - set(sec))
    by_month = collections.defaultdict(lambda: {"sec": 0, "archived": 0, "missing": 0})
    for accession, row in sec.items():
        month = row["filed"][:7]
        by_month[month]["sec"] += 1
        by_month[month]["archived" if accession in manifest else "missing"] += 1
    return sec, missing, archived, unmatched, dict(sorted(by_month.items()))


def main():
    manifest = load_manifest("edgar-free-year-manifest.txt")
    index_texts = {}
    sources = []
    for year, quarter in INDEXES:
        url, text = fetch_index(year, quarter)
        index_texts[(year, quarter)] = text
        sources.append(url)
        print(f"Fetched {url} ({len(text):,} characters)", flush=True)
        time.sleep(0.25)
    sec, missing, archived, unmatched, monthly = reconcile(index_texts, manifest)
    out = Path("reports")
    out.mkdir(exist_ok=True)
    with (out / "sec_missing_form4_accessions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["accession", "form", "filed", "cik", "company", "path"])
        writer.writeheader()
        writer.writerows({field: sec[a][field] for field in writer.fieldnames} for a in missing)
    with (out / "manifest_not_in_sec_window.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["accession"])
        writer.writerows([a] for a in unmatched)
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "filing_date_start": START.isoformat(), "filing_date_end": END.isoformat(),
        "scope": "SEC quarterly master-index Form 4/4-A by filing date versus existing manifest accession; NOT a content/eligibility audit",
        "index_sources": sources,
        "sec_form4_4a": len(sec),
        "manifest_total": len(manifest),
        "sec_accessions_in_manifest": len(archived),
        "missing_from_manifest": len(missing),
        "manifest_not_in_sec_window": len(unmatched),
        "monthly": monthly,
        "limitations": [
            "Index uses date filed; previous archive audit groups by acceptance timestamp.",
            "A missing accession may be a non-P transaction; no purchase eligibility classification here.",
            "SEC quarterly index for current quarter may be updated; rerun for final coverage.",
            "Manifest-not-in-window may reflect different dates or filing types and requires classification.",
        ],
    }
    (out / "sec_master_index_reconciliation.json").write_text(json.dumps(summary, indent=2))
    rows = "".join(f"<tr><td>{html.escape(month)}</td><td>{v['sec']:,}</td><td>{v['archived']:,}</td><td>{v['missing']:,}</td></tr>" for month,v in monthly.items())
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>SEC master-index reconciliation</title><style>body{{font:16px system-ui;max-width:950px;margin:35px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}</style><h1>SEC Form 4/4-A index reconciliation</h1><p>Filing dates {START} through {END}</p><p><strong>SEC filings:</strong> {len(sec):,}; <strong>in manifest:</strong> {len(archived):,}; <strong>missing from manifest:</strong> {len(missing):,}; <strong>manifest accessions outside SEC index window:</strong> {len(unmatched):,}.</p><p>Counts include ALL Form 4 and 4/A, not only discretionary code-P purchases. Source index date is filing date, not acceptance timestamp.</p><table><tr><th>Filed month</th><th>SEC Form 4/4-A</th><th>In manifest</th><th>Missing</th></tr>{rows}</table><p>See CSV files for accession-level details. SEC current-quarter indexes may be revised.</p></html>"""
    (out / "sec_master_index_reconciliation.html").write_text(page)
    print(json.dumps(summary, indent=2), flush=True)
    print("Report generated; missing accessions are reported, not treated as a workflow crash.")


if __name__ == "__main__":
    main()
