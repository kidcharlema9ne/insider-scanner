"""Read-only real-data smoke test for the D-051 outcome and HTML pipeline."""

import hashlib
import json
import os
import re
from contextlib import closing
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import exchange_calendars as xcals
import pyarrow.parquet as pq

from form4_parser import parse_form4
from integrated_research_dataset import integrate
from r2_storage import BUCKET, client
from research_html_report import write_report

PRICE_PREFIX = "samples/marketparquet/stock_daily/"
ACCESSION = "0001868288-26-000002"
FILING_KEY = f"sec/edgar/smoke-test/{ACCESSION}.txt"
FILING_SHA = "2642eb3b99cbc6f05bbd84ba1ef63118f276ec9a9fb9c1979308c1d6ddf4c4c3"


def checked_object(storage, key, expected=None):
    obj = storage.get_object(Bucket=BUCKET, Key=key)
    with closing(obj["Body"]) as body:
        data = body.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != (expected or obj.get("Metadata", {}).get("verified-sha256")):
        raise ValueError(f"Missing or incorrect SHA-256 for {key}")
    return data, digest


def main():
    storage = client()
    raw, _ = checked_object(storage, FILING_KEY, FILING_SHA)
    raw = raw.decode("utf-8", errors="replace")
    filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", raw)
    if not filed:
        raise ValueError("SEC original has no filing date")
    filing_date = date.fromisoformat(filed[1]).isoformat()
    filing = parse_form4(raw)
    purchases = filing["candidate_purchases"]
    identity = {(row["issuer_cik"], row["issuer_ticker"], row["security_title"]) for row in purchases}
    if len(identity) != 1 or not all(row["acquired_disposed"] == "A" for row in purchases):
        raise ValueError("Unexpected SEC smoke-test transaction identity")
    cik, ticker, title = identity.pop()
    if ticker != "GME" or int(cik) != 1326380:
        raise ValueError("SEC smoke-test identity changed")

    calendar = xcals.get_calendar("XNYS")
    days = [str(day.date()) for day in calendar.sessions_in_range("2025-11-06", "2026-11-05")]
    keys = {
        item["Key"].removeprefix(PRICE_PREFIX)
        for page in storage.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PRICE_PREFIX)
        for item in page.get("Contents", [])
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.parquet", item["Key"].removeprefix(PRICE_PREFIX))
    }
    missing = sorted({f"{day}.parquet" for day in days} - keys)
    extra = sorted(key for key in keys if days[0] <= key[:-8] <= days[-1] and key[:-8] not in days)
    if missing or extra:
        raise ValueError(f"R2 session coverage mismatch: missing={missing}, extra={extra}")

    bars = []
    partition_hashes = {}
    fields = ["open", "high", "low", "close", "volume"]
    for day in days:
        data, partition_hashes[day] = checked_object(storage, f"{PRICE_PREFIX}{day}.parquet")
        parquet = pq.ParquetFile(BytesIO(data))
        columns = set(parquet.schema_arrow.names)
        date_col = "date" if "date" in columns else "timestamp"
        if not {"symbol", date_col, *fields} <= columns or not parquet.metadata.num_rows:
            raise ValueError(f"Unexpected Parquet schema or empty partition on {day}")
        rows = pq.read_table(BytesIO(data), columns=[date_col, *fields],
                             filters=[("symbol", "=", ticker)], use_threads=False).to_pylist()
        if len(rows) != 1 or str(rows[0].pop(date_col))[:10] != day:
            raise ValueError(f"Missing, duplicate or misdated {ticker} bar on {day}")
        bar = rows[0]
        o, h, l, c, v = (Decimal(str(bar[field])) for field in fields)
        if not all(x.is_finite() for x in (o, h, l, c, v)) or not 0 < l <= min(o, c) <= max(o, c) <= h or v < 0:
            raise ValueError(f"Invalid {ticker} OHLCV on {day}")
        bars.append(dict(bar, date=day))

    security_id = "smoke-test:xnys:gme"
    record = {
        "accession": ACCESSION, "issuer_cik": cik, "ticker_at_filing": ticker,
        "security_title": title, "filing_date": filing_date, "security_id": security_id,
        "transaction_dates": sorted({row["transaction_date"] for row in purchases}),
        "aggregate_dollars": str(sum(Decimal(row["transaction_value"]) for row in purchases)),
        "owners": filing["owners"],
        "review_flags": sorted({flag for row in purchases for flag in row["review_flags"]}),
    }
    dataset = integrate([record], {security_id: bars}, sessions=days)
    result = dataset["opportunities"][0]
    if result.get("next_open_date") != "2026-01-27":
        raise ValueError(f"Unexpected D-051 entry: {result}")
    entry_index = days.index("2026-01-27")
    ranges = [
        max(Decimal(str(bars[i]["high"])), Decimal(str(bars[i-1]["close"])))
        - min(Decimal(str(bars[i]["low"])), Decimal(str(bars[i-1]["close"])))
        for i in range(entry_index - 14, entry_index)
    ]
    expected_atr = sum(ranges) / 14
    entry = Decimal(str(bars[entry_index]["open"]))
    last = Decimal(str(bars[entry_index + 20]["close"]))
    if (Decimal(result["atr14"]) != expected_atr or Decimal(result["next_open"]) != entry
            or Decimal(result["horizons"]["21"]["next_open"]["end_return_atr"]) != (last - entry) / expected_atr
            or result["horizons"]["6m"]["status"] != "ok"):
        raise ValueError("Independent price calculation differs from integrated results")
    dataset["metadata"] = {
        "scope": "Single known SEC candidate; manually pinned sample identity; price-only engineering smoke test",
        "commit": os.environ.get("GITHUB_SHA"), "sec_key": FILING_KEY, "sec_sha256": FILING_SHA,
        "price_prefix": PRICE_PREFIX, "price_sha256_by_date": partition_hashes,
        "calendar": "XNYS", "pre_entry_true_ranges": [str(value) for value in ranges],
        "limits": "No universe, eligibility, liquidity, adjustments or historical identity validation.",
    }
    write_report(dataset, "reports/free_year_smoke.html", title="Insider Buying Research — Real-data smoke test")
    Path("reports/free_year_smoke.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
