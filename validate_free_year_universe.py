"""Exercise the audited SEC database and price archive at sample scale.

Ticker joins here are explicitly provisional. Production requires verified
effective-dated identity and eligibility. This run measures pipeline coverage.
"""

import json
import os
import sqlite3
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import exchange_calendars as xcals
import pyarrow.parquet as pq

from integrated_research_dataset import integrate
from price_outcomes import atr14
from r2_storage import BUCKET, client
from research_html_report import write_report
from sec_bulk_importer import disclosure_opportunities
from validate_free_year_report import PRICE_PREFIX, checked_object

DB_KEY = "sec/insider-transactions/derived/purchase_candidates.sqlite3"
START, END = "2025-11-06", "2026-11-05"


def main():
    storage = client()
    database, digest = checked_object(storage, DB_KEY)
    with TemporaryDirectory() as directory:
        path = Path(directory) / "sec.sqlite"
        path.write_bytes(database)
        del database
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            disclosures = [row for row in disclosure_opportunities(db, START, END)]
    if not disclosures:
        raise ValueError("Audited database returned no disclosures in the sample")
    days = [str(day.date()) for day in xcals.get_calendar("XNYS").sessions_in_range(START, END)]
    identities = defaultdict(set)
    for row in disclosures:
        ticker = (row.get("ticker_at_filing") or "").upper()
        if ticker:
            identities[ticker].add((row["issuer_cik"], row["security_title"]))
    provisional = {ticker for ticker, matches in identities.items() if len(matches) == 1}
    for row in disclosures:
        ticker = (row.get("ticker_at_filing") or "").upper()
        if ticker in provisional:
            row["security_id"] = "provisional:" + ticker
            row["review_flags"].append("unverified_price_identity")
        elif ticker:
            row["review_flags"].append("conflicting_sec_ticker_identity")

    series = defaultdict(list)
    hashes = {}
    rejected_bars = Counter()
    fields = ["open", "high", "low", "close", "volume"]
    for day in days:
        data, hashes[day] = checked_object(storage, f"{PRICE_PREFIX}{day}.parquet")
        parquet = pq.ParquetFile(BytesIO(data))
        schema = set(parquet.schema_arrow.names)
        date_col = "date" if "date" in schema else "timestamp"
        if not {"symbol", date_col, *fields} <= schema or not parquet.metadata.num_rows:
            raise ValueError(f"Invalid price partition schema on {day}")
        rows = pq.read_table(BytesIO(data), columns=["symbol", date_col, *fields],
                             filters=[("symbol", "in", sorted(provisional))]).to_pylist()
        counts = Counter(row["symbol"] for row in rows)
        for row in rows:
            ticker = row.pop("symbol")
            if counts[ticker] != 1 or str(row.pop(date_col))[:10] != day:
                rejected_bars["duplicate_or_misdated"] += 1
                continue
            if any(row[field] is None for field in fields):
                rejected_bars["null_ohlcv"] += 1
                continue
            o, h, l, c, v = (Decimal(str(row[field])) for field in fields)
            if not all(x.is_finite() for x in (o, h, l, c, v)) or not 0 < l <= min(o, c) <= max(o, c) <= h or v < 0:
                rejected_bars["invalid_ohlcv"] += 1
                continue
            series["provisional:" + ticker].append(dict(row, date=day))

    dataset = integrate(disclosures, series, sessions=days)
    priced = [row for row in dataset["opportunities"] if row["outcome_status"] == "ok"]
    if len({row["security_id"] for row in priced}) < 2:
        raise ValueError("Multi-stock integration requires priced disclosures on at least two stocks")
    for row in priced:
        expected = days[bisect_right(days, row["filing_date"])]
        if row["next_open_date"] != expected:
            raise ValueError(f"D-051 entry mismatch for {row['accession']}")
    # Purchase-date context is descriptive. The outcome still starts after filing.
    for row in priced:
        trade_dates = row.get("transaction_dates") or []
        if not trade_dates:
            continue
        purchase_date = max(trade_dates)
        index = bisect_left(days, purchase_date)
        if index < 22 or purchase_date > row["filing_date"]:
            continue
        context_days = days[index - 22:index]
        wanted = set(context_days)
        by_day = {bar["date"]: bar for bar in series[row["security_id"]] if bar["date"] in wanted}
        if len(by_day) != len(context_days):
            continue
        history = [by_day[day] for day in context_days]
        risk = atr14(history, len(history))
        if risk is None or risk <= 0:
            continue
        row["purchase_context"] = {
            "date": purchase_date,
            "last_completed_session": context_days[-1],
            "atr14": str(risk),
            "signed_21_session_atr": str((Decimal(str(history[-1]["close"])) -
                                          Decimal(str(history[0]["close"]))) / risk),
        }
    coverage = {
        "candidate_disclosures": len(disclosures),
        "priced_candidate_disclosures": len(priced),
        "priced_provisional_tickers": len({row["security_id"] for row in priced}),
        "available_outcomes": dict(Counter(h for row in priced for h, v in row["horizons"].items() if v["status"] == "ok")),
        "review_flags": dict(Counter(flag for row in disclosures for flag in row["review_flags"])),
        "rejected_bars": dict(rejected_bars),
    }
    dataset["metadata"] = {"coverage": coverage, "database_sha256": digest,
                           "price_sha256_by_date": hashes, "commit": os.environ.get("GITHUB_SHA"),
                           "scope": "Provisional engineering sample. Ticker joins, eligibility, corporate actions and adjustments require verification."}
    output = Path("reports")
    output.mkdir(exist_ok=True)
    (output / "free_year_coverage.json").write_text(json.dumps(dataset["metadata"], indent=2))
    (output / "free_year_candidates.json").write_text(json.dumps(dataset))
    write_report(dataset, output / "free_year_candidates.html", title="Free-year integration — provisional candidates",
                 detail_limit=100, scope_note=dataset["metadata"]["scope"])
    print(json.dumps(coverage, indent=2))


if __name__ == "__main__":
    main()
