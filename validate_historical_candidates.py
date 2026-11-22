"""Unattended post-import audit of historical SEC purchase database in R2."""
import hashlib, json, sqlite3, tempfile
from datetime import date
from collections import Counter
from pathlib import Path
from r2_storage import BUCKET, client
from sec_archive_scope import QUARTERS, missing_quarters
from sec_bulk_importer import disclosure_opportunities
from sec_episode_research import build_episodes, prior_disclosure_counts

KEY="sec/insider-transactions/derived/purchase_candidates.sqlite3"
storage=client()
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"candidates.sqlite3"
    remote = storage.head_object(Bucket=BUCKET, Key=KEY)
    storage.download_file(BUCKET, KEY, str(path))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != remote.get("Metadata", {}).get("verified-sha256"):
        raise SystemExit("Historical database checksum mismatch after R2 download")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity!="ok": raise SystemExit("SQLite integrity check failed: "+integrity)
    rows = db.execute("SELECT accession, transaction_row_key, filing_date, transaction_date, issuer_cik, ticker, payload FROM purchase_candidates")
    quarters=db.execute("SELECT name,candidate_rows FROM imported_quarters ORDER BY name").fetchall()
    counts=Counter()
    filings=set()
    opportunities=set()
    years=Counter()
    for accession, row_key, filing_date, transaction_date, cik, ticker, raw in rows:
        r=json.loads(raw)
        counts["rows"]+=1
        filing=r.get("filing_date")
        if not filing: counts["missing_filing_date"]+=1
        else:
            try:
                years[str(date.fromisoformat(filing).year)] += 1
            except ValueError:
                counts["invalid_filing_date"] += 1
        if (accession, row_key, filing_date, transaction_date, cik, ticker) != (
            r.get("accession"), r.get("transaction_row_key"), filing, r.get("transaction_date"),
            r.get("issuer_cik"), r.get("ticker_at_filing"),
        ):
            counts["payload_column_mismatch"] += 1
        if not r.get("transaction_date"): counts["missing_transaction_date"]+=1
        if not r.get("owners"): counts["missing_owners"]+=1
        if not r.get("ticker_at_filing"): counts["missing_ticker"]+=1
        if not r.get("shares") or not r.get("price_per_share"): counts["missing_numeric"]+=1
        if r.get("acquired_disposed")!="A": counts["non_acquisition_P"]+=1
        if r.get("review_flags"): counts["flagged_rows"]+=1
        if r.get("form") not in ("4","4/A"): counts["unexpected_form"]+=1
        filings.add(r["accession"])
        opportunities.add((r["accession"],r["issuer_cik"],r["security_title"]))
    disclosures=list(disclosure_opportunities(db))
    episodes=build_episodes(disclosures)
    history=prior_disclosure_counts(disclosures)
    quarter_names = {name for name, _ in quarters}
    missing = missing_quarters(quarter_names)
    unexpected = sorted(quarter_names - QUARTERS)
    source_rows = sum(count for _, count in quarters)
    report={"episode_count":len(episodes),"insider_history_keys":len(history),"stage":"sec_preprice_validation","db_key":KEY,"integrity":integrity,
      "imported_quarters":len(quarters),"candidate_rows":counts["rows"], "quarter_source_rows":source_rows,
      "missing_quarters":missing, "unexpected_quarters":unexpected,
      "database_sha256":digest,
      "unique_filings":len(filings),"filing_security_opportunities":len(opportunities),
      "field_quality":dict(counts),"year_counts":dict(sorted(years.items())),
      "quarter_counts":dict(quarters),
      "episode_rule":"Descriptive grouping only; individual disclosure entries remain separate",
      "historical_entry_rule":"D-051: next regular trading session open after SEC filing date; acceptance timestamp not needed",
      "status":"passed" if not missing and not unexpected and source_rows == counts["rows"] > 0 and not any(counts[k] for k in ("missing_filing_date", "invalid_filing_date", "unexpected_form", "payload_column_mismatch")) else "blocked"}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/preprice_validation.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ("year_counts","quarter_counts")},indent=2))
    if report["status"]!="passed": raise SystemExit("Historical SEC preprice validation blocked; see report")
