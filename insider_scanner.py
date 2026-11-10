#!/usr/bin/env python3
"""
insider_scanner.py - SEC Form 4 open-market-purchase scanner.

Scoring weights are PRIORS taken from the public literature (see README.md),
not fitted values. Every signal is logged with its features so `track` can
measure which factors actually pay, and weights can be revised from evidence.

Commands
  scan      pull new Form 4 filings (Atom feed + recent daily indexes), score, alert
  backfill  load history from the SEC's free quarterly Insider Transactions
            Data Sets (needed for first-purchase / routine-trader checks)
  track     compute forward returns (vs SPY) for logged signals
  report    show recent logged signals
  digest    email an analysis report: recent signals (who bought, when, how much),
            the scorecard by tier, and which factors are paying
  notify-test  send a test push/email alert

Requires: Python 3.9+, `requests`. Optional: `yfinance` (liquidity + price context).
SEC rules: declared User-Agent with contact info, <= 10 requests/sec (we use ~4).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html as _html
import io
import json
import math
import os
import re
import smtplib
import sqlite3
import statistics
import sys
import time
import traceback
import zipfile
from email.message import EmailMessage
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration (priors from the literature; edit freely)
# --------------------------------------------------------------------------
CFG = {
    "min_value_usd": 10_000,      # ignore token buys (lowered from 25k on 2026-11-05)
    # No price floor (removed 2026-11-05). The $3M ADV floor below is the only liquidity gate.
    # The old floors are kept ONLY to tag signals the old rules would have blocked, so
    # `track`/`digest` data can later show whether loosening them helped.
    "legacy_min_value_usd": 25_000,
    "legacy_min_price": 2.0,
    "min_adv_usd": 3_000_000,     # user's liquidity floor (20-day avg dollar volume)
    "big_adv_usd": 100_000_000,   # very liquid/large names: weaker signal in studies
    # Published cluster definitions are far tighter than a month: same or consecutive
    # trading days / within 2 days (academic), 7-15 days (practitioner screens).
    # 14 days is the compromise; the tight bonus below still rewards buys within 2 days.
    "cluster_window_days": 14,
    "tight_cluster_days": 2,
    "late_filing_days": 4,        # calendar days tx->filing beyond which we flag "late"
    "alert_min_score": 40,
    "failure_alert_hours": 6,     # at most one "scanner FAILED" alert per command per this many hours
}
ROLE_PTS = {"CFO": 20, "CEO": 17, "OFFICER": 14, "DIRECTOR": 12, "10%OWNER": 4, "OTHER": 4}
CLUSTER_PTS = {1: 0, 2: 14, 3: 22}   # 4+ -> 28
CLUSTER_4PLUS = 28
TIGHT_CLUSTER_BONUS = 4
FIRST_PURCHASE_PTS = 12              # first buy by this insider in 12 months (history verified)
FIRST_PURCHASE_UNVERIFIED_PTS = 6    # history too short to verify
ROUTINE_PENALTY = -20                # Cohen-Malloy-Pomorski "routine" pattern
BIG_ADV_PENALTY = -8
RELSIZE_PTS = [(0.50, 10), (0.10, 6), (0.02, 3)]   # holdings increase thresholds

DEFAULT_HOME = Path(os.environ.get("INSIDER_SCANNER_HOME", Path.home() / "insider_scanner"))
ATOM_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
            "&company=&dateb=&owner=include&start={start}&count=100&output=atom")
DAILY_IDX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_TXT = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{acc}.txt"
MIN_HISTORY_DAYS = 60                # fewer trading days than this => recent IPO, skip
BULK_URL = ("https://www.sec.gov/files/structureddata/data/"
            "insider-transactions-data-sets/{y}q{q}_form345.zip")

SCHEMA = """
CREATE TABLE IF NOT EXISTS filing_retries (
    accession TEXT PRIMARY KEY, filed_at TEXT NOT NULL, url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_outbox (
    id INTEGER PRIMARY KEY, payload TEXT NOT NULL, channels TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filings(
  accession TEXT PRIMARY KEY, filed_at TEXT, n_purchases INTEGER);
CREATE TABLE IF NOT EXISTS purchases(
  accession TEXT, issuer_cik TEXT, ticker TEXT, issuer_name TEXT,
  owner_cik TEXT, owner_name TEXT, role TEXT, title TEXT,
  tx_date TEXT, filed_date TEXT, filed_at TEXT,
  shares REAL, price REAL, value REAL, post_shares REAL,
  plan10b5 INTEGER, source TEXT,
  PRIMARY KEY(accession, owner_cik, tx_date));
CREATE INDEX IF NOT EXISTS ix_p_issuer ON purchases(issuer_cik, tx_date);
CREATE INDEX IF NOT EXISTS ix_p_owner ON purchases(owner_cik, issuer_cik, tx_date);
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, detected_at TEXT, issuer_cik TEXT,
  ticker TEXT, latest_accession TEXT, latest_filed_date TEXT,
  score REAL, tier TEXT, payload TEXT,
  UNIQUE(issuer_cik, latest_accession));
CREATE TABLE IF NOT EXISTS gapfill(
  issuer_cik TEXT PRIMARY KEY, done_at TEXT, ok INTEGER, n_filings INTEGER);
CREATE TABLE IF NOT EXISTS outcomes(
  signal_id INTEGER, horizon INTEGER, ret REAL, spy_ret REAL,
  PRIMARY KEY(signal_id, horizon));
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# --------------------------------------------------------------------------
# HTTP (SEC fair-access compliant)
# --------------------------------------------------------------------------
class Edgar:
    def __init__(self, user_agent: str, rps: float = 4.0):
        # Secrets pasted on a phone often carry a trailing newline/space or smart quotes, which
        # makes `requests` reject the header. Collapse whitespace and drop non-ASCII/quotes.
        user_agent = " ".join((user_agent or "").split()).strip("\"'")
        user_agent = user_agent.encode("ascii", "ignore").decode("ascii").strip()
        if "@" not in (user_agent or ""):
            raise SystemExit(
                "SEC requires a declared User-Agent with contact info.\n"
                "Set SEC_USER_AGENT='Your Name you@example.com' or pass --user-agent.")
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.gap = 1.0 / rps
        self._last = 0.0

    def get(self, url: str, retries: int = 4, soft403: bool = False):
        for i in range(retries):
            wait = self.gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = self.s.get(url, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            if r.status_code == 403 and soft403:
                return None          # SEC answers 403 for index files that do not exist yet
            if r.status_code in (403, 429, 500, 502, 503, 504):
                time.sleep(2 ** (i + 1))
                continue
            r.raise_for_status()
        raise RuntimeError(f"giving up on {url}")


# --------------------------------------------------------------------------
# Form 4 parsing
# --------------------------------------------------------------------------
def _t(node, path):
    n = node.find(path)
    return n.text.strip() if n is not None and n.text else None


def _truthy(v):
    return (v or "").strip().lower() in ("1", "true", "y", "yes")


def _num(v):
    try:
        return float(v.replace(",", "")) if v else None
    except ValueError:
        return None


def classify_role(is_dir, is_off, is_ten, title):
    t = (title or "").lower()
    if re.search(r"chief financial|\bcfo\b|principal financial", t):
        return "CFO"
    if re.search(r"chief executive|\bceo\b|principal executive", t):
        return "CEO"
    if is_off or t:
        return "OFFICER"
    if is_dir:
        return "DIRECTOR"
    if is_ten:
        return "10%OWNER"
    return "OTHER"


def extract_xml(raw: str):
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", raw, re.S)
    return m.group(0) if m else None


IPO_STRONG = re.compile(r"initial public offering|\bIPO\b|directed share|public offering price|"
                        r"concurrent private placement|purchased from the underwriters?", re.I)
# Non-discretionary buys (automatic plans, dividend reinvestment, employee stock purchase plans) are excluded,
# as in the research study (insider-buying-research: form4_parser.py, sec_bulk_importer.py).
NON_DISCRETIONARY = re.compile(r"automatic|dividend reinvest|employee stock purchase|\bESPP\b", re.I)
IPO_WEAK = re.compile(r"underwrit|follow-?on offering|secondary offering|private placement|"
                      r"registered direct|offering price", re.I)


def parse_form4(raw: str, accession: str, filed_at: str, *, strict=False):
    """Return a list of aggregated open-market-purchase dicts from one filing."""
    xml = extract_xml(raw)
    if not xml:
        if strict:
            raise ValueError("missing ownership XML")
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        if strict:
            raise ValueError("invalid ownership XML")
        return []
    if _t(root, "documentType") not in (None, "4"):
        return []
    issuer = root.find("issuer")
    if issuer is None:
        if strict:
            raise ValueError("missing issuer")
        return []
    issuer_cik = (_t(issuer, "issuerCik") or "").lstrip("0")
    ticker = (_t(issuer, "issuerTradingSymbol") or "").upper()
    issuer_name = _t(issuer, "issuerName") or ""

    # owners: use first as primary identity, OR the relationship flags (joint filers)
    owners = root.findall("reportingOwner")
    if not owners:
        if strict:
            raise ValueError("missing reporting owner")
        return []
    o0 = owners[0]
    owner_cik = (_t(o0, "reportingOwnerId/rptOwnerCik") or "").lstrip("0")
    owner_name = _t(o0, "reportingOwnerId/rptOwnerName") or ""
    is_dir = is_off = is_ten = False
    title = ""
    for o in owners:
        rel = o.find("reportingOwnerRelationship")
        if rel is None:
            continue
        is_dir |= _truthy(_t(rel, "isDirector"))
        is_off |= _truthy(_t(rel, "isOfficer"))
        is_ten |= _truthy(_t(rel, "isTenPercentOwner"))
        title = title or (_t(rel, "officerTitle") or "")
    role = classify_role(is_dir, is_off, is_ten, title)

    footnotes = {f.get("id"): (f.text or "") for f in root.findall("footnotes/footnote")}
    plan_flag = _truthy(_t(root, "aff10b5One"))
    all_fn = " ".join(footnotes.values())
    doc_is_ipo = bool(IPO_STRONG.search(all_fn))

    groups: dict = {}
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if _t(tx, "transactionCoding/transactionCode") != "P":
            continue
        if _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value") != "A":
            continue
        shares = _num(_t(tx, "transactionAmounts/transactionShares/value"))
        price = _num(_t(tx, "transactionAmounts/transactionPricePerShare/value"))
        if not shares or not price:
            continue
        tx_date = (_t(tx, "transactionDate/value") or "")[:10]
        post = _num(_t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"))
        fn_text = " ".join(footnotes.get(f.get("id"), "") for f in tx.iter("footnoteId"))
        fn_plan = bool(re.search(r"10b5-?1", fn_text, re.I)) and not re.search(
            r"\b(not|no)\b.{0,60}10b5-?1", fn_text, re.I)
        if doc_is_ipo or IPO_WEAK.search(fn_text) or NON_DISCRETIONARY.search(fn_text):
            continue                  # IPO / directed-share / placement / automatic-plan purchase, not discretionary open-market
        g = groups.setdefault(tx_date, {"shares": 0.0, "value": 0.0, "post": None, "plan": False})
        g["shares"] += shares
        g["value"] += shares * price
        g["post"] = post if post is not None else g["post"]
        g["plan"] |= fn_plan
    out = []
    filed_date = filed_at[:10]
    for tx_date, g in groups.items():
        out.append({
            "accession": accession, "issuer_cik": issuer_cik, "ticker": ticker,
            "issuer_name": issuer_name, "owner_cik": owner_cik, "owner_name": owner_name,
            "role": role, "title": title, "tx_date": tx_date, "filed_date": filed_date,
            "filed_at": filed_at, "shares": g["shares"], "price": g["value"] / g["shares"],
            "value": g["value"], "post_shares": g["post"],
            "plan10b5": int(plan_flag or g["plan"]), "source": "live",
        })
    return out


# --------------------------------------------------------------------------
# Discovery: Atom feed, daily index
# --------------------------------------------------------------------------
def parse_atom(xml_text: str):
    """-> list of (accession, filed_at_iso, txt_url). Skips 4/A and duplicate accessions."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    seen, out = set(), []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        if not title.startswith("4 -"):
            continue
        link = e.find("a:link", ns)
        href = link.get("href") if link is not None else ""
        m = re.search(r"(\d{10}-\d{2}-\d{6})", href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        updated = e.findtext("a:updated", default="", namespaces=ns) or ""
        out.append((m.group(1), updated, href.replace("-index.htm", ".txt")))
    return out


def parse_daily_index(text: str):
    """-> list of (accession, filed_date_iso, txt_url) for Form 4 rows."""
    seen, out = set(), []
    for line in text.splitlines():
        m = re.match(r"^4\s{2,}.+?\s{2,}\d+\s+(\d{8})\s+(edgar/data/\S+\.txt)\s*$", line)
        if not m:
            continue
        acc = re.search(r"(\d{10}-\d{2}-\d{6})", m.group(2))
        if not acc or acc.group(1) in seen:
            continue
        seen.add(acc.group(1))
        d = m.group(1)
        out.append((acc.group(1), f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "https://www.sec.gov/Archives/" + m.group(2)))
    return out


def discover_atom(edgar, con, max_pages=10):
    found = []
    for p in range(max_pages):
        r = edgar.get(ATOM_URL.format(start=p * 100))
        if r is None:
            break
        page = parse_atom(r.text)
        if not page:
            break
        new = [x for x in page if not con.execute(
            "SELECT 1 FROM filings WHERE accession=?", (x[0],)).fetchone()]
        found += new
        if not new:           # whole page already processed -> caught up
            break
    return found


def discover_daily(edgar, con, day: dt.date):
    q = (day.month - 1) // 3 + 1
    r = edgar.get(DAILY_IDX_URL.format(y=day.year, q=q, ymd=day.strftime("%Y%m%d")), soft403=True)
    if r is None:
        return []
    return [x for x in parse_daily_index(r.text) if not con.execute(
        "SELECT 1 FROM filings WHERE accession=?", (x[0],)).fetchone()]


def parse_submissions(js: dict, since_iso: str):
    """-> [(accession, filing_date)] of Form 4s from a data.sec.gov submissions JSON, newest first."""
    rec = (js.get("filings") or {}).get("recent") or {}
    out = [(a, d) for f, a, d in zip(rec.get("form", []), rec.get("accessionNumber", []),
                                      rec.get("filingDate", [])) if f == "4" and d >= since_iso]
    return sorted(out, key=lambda x: x[1], reverse=True)


def gapfill_issuer(edgar, con, issuer_cik: str, today: dt.date, days: int = 400,
                   max_filings: int = 60, recheck_days: int = 30) -> int:
    """Fill holes left by lagging quarterly bulk files: fetch this issuer's own Form 4 list from
    data.sec.gov and parse any filing we do not have. Returns #filings added, or -1 on failure."""
    row = con.execute("SELECT done_at, ok FROM gapfill WHERE issuer_cik=?", (issuer_cik,)).fetchone()
    if row and row["ok"] and row["done_at"] >= (today - dt.timedelta(days=recheck_days)).isoformat():
        return 0
    try:
        r = edgar.get(SUBMISSIONS_URL.format(cik=int(issuer_cik)))
        if r is None:
            raise RuntimeError("submissions not found")
        wanted = parse_submissions(r.json(), (today - dt.timedelta(days=days)).isoformat())
        missing = [(a, d) for a, d in wanted if not con.execute(
            "SELECT 1 FROM filings WHERE accession=?", (a,)).fetchone()][:max_filings]
        items = [(a, d + "T00:00:00",
                  ARCHIVE_TXT.format(cik=int(issuer_cik), nodash=a.replace("-", ""), acc=a))
                 for a, d in missing]
        ingest(edgar, con, items, verbose=False)
        n = sum(con.execute("SELECT 1 FROM filings WHERE accession=?", (a,)).fetchone() is not None
                for a, _, _ in items)
        ok = int(n == len(items))
        if not ok:
            n = -1
    except Exception as e:                      # never let a gap-fill failure kill the scan
        print(f"  gap-fill failed for CIK {issuer_cik}: {e}", file=sys.stderr)
        ok, n = 0, -1
    con.execute("INSERT OR REPLACE INTO gapfill VALUES (?,?,?,?)",
                (issuer_cik, today.isoformat(), ok, max(n, 0)))
    con.commit()
    return n


def ingest(edgar, con, items, verbose=True, recovered=None):
    n_new = 0
    for i, (acc, filed_at, url) in enumerate(items, 1):
        try:
            r = edgar.get(url)
            if r is None:
                raise ValueError("filing unavailable")
            rows = parse_form4(r.text, acc, filed_at, strict=True)
        except (ValueError, RuntimeError, OSError) as exc:
            con.execute("INSERT OR REPLACE INTO filing_retries VALUES (?,?,?)", (acc, filed_at, url))
            con.commit()
            print(f"  queued filing {acc} for retry: {exc}", file=sys.stderr)
            continue
        retry = con.execute("DELETE FROM filing_retries WHERE accession=?", (acc,))
        if retry.rowcount and recovered is not None:
            recovered.update(row["issuer_cik"] for row in rows
                             if row["ticker"] not in ("", "NONE", "N/A", "NA")
                             and not row["plan10b5"] and row["value"] >= CFG["min_value_usd"])
        for row in rows:
            con.execute("""INSERT OR IGNORE INTO purchases VALUES
              (:accession,:issuer_cik,:ticker,:issuer_name,:owner_cik,:owner_name,:role,:title,
               :tx_date,:filed_date,:filed_at,:shares,:price,:value,:post_shares,:plan10b5,:source)""", row)
        con.execute("INSERT OR IGNORE INTO filings VALUES (?,?,?)", (acc, filed_at, len(rows)))
        n_new += len(rows)
        if i % 50 == 0:
            con.commit()
            if verbose:
                print(f"  ...{i}/{len(items)} filings parsed", file=sys.stderr)
    con.commit()
    return n_new


# --------------------------------------------------------------------------
# Historical backfill from SEC Insider Transactions Data Sets (bulk TSV)
# NOTE: column names follow the SEC readme; lookup is case-insensitive with fallbacks.
# --------------------------------------------------------------------------
def _tsv(zf, member):
    with zf.open(member) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
        rd = csv.DictReader(text, delimiter="\t")
        rd.fieldnames = [f.strip().upper() for f in rd.fieldnames or []]
        yield from rd


def _first(row, *names):
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return v.strip()
    return None


def _bulk_date(s):
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip().title(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def load_bulk_zip(con, zip_path_or_bytes) -> int:
    zf = zipfile.ZipFile(zip_path_or_bytes)
    subs = {}
    for r in _tsv(zf, "SUBMISSION.tsv"):
        if (_first(r, "DOCUMENT_TYPE", "FORM_TYPE") or "4") != "4":
            continue
        subs[r["ACCESSION_NUMBER"]] = {
            "filed": _bulk_date(_first(r, "FILING_DATE")),
            "cik": (_first(r, "ISSUERCIK") or "").lstrip("0"),
            "ticker": (_first(r, "ISSUERTRADINGSYMBOL") or "").upper(),
            "name": _first(r, "ISSUERNAME") or "",
            "plan": (_first(r, "AFF10B5ONE") or "").lower() in ("1", "true", "y"),
        }
    owners = {}
    for r in _tsv(zf, "REPORTINGOWNER.tsv"):
        a = r["ACCESSION_NUMBER"]
        rel = (_first(r, "RPTOWNER_RELATIONSHIP") or "").lower()
        title = _first(r, "RPTOWNER_TITLE") or ""
        cur = owners.get(a)
        if cur is None:
            owners[a] = {"cik": (_first(r, "RPTOWNERCIK") or "").lstrip("0"),
                         "name": _first(r, "RPTOWNERNAME") or "", "rel": rel, "title": title}
        else:
            cur["rel"] += "," + rel
            cur["title"] = cur["title"] or title
    groups = {}
    for r in _tsv(zf, "NONDERIV_TRANS.tsv"):
        a = r["ACCESSION_NUMBER"]
        if a not in subs or a not in owners:
            continue
        if (_first(r, "TRANS_CODE") or "") != "P" or (_first(r, "TRANS_ACQUIRED_DISP_CD") or "A") != "A":
            continue
        try:
            sh = float(_first(r, "TRANS_SHARES") or 0)
            px = float(_first(r, "TRANS_PRICEPERSHARE") or 0)
        except ValueError:
            continue
        d = _bulk_date(_first(r, "TRANS_DATE"))
        if not sh or not px or not d:
            continue
        post = _first(r, "SHRS_OWNED_FOLLOWING_TRANS")
        g = groups.setdefault((a, d), {"sh": 0.0, "val": 0.0, "post": None})
        g["sh"] += sh
        g["val"] += sh * px
        if post:
            try:
                g["post"] = float(post)
            except ValueError:
                pass
    n = 0
    for (a, d), g in groups.items():
        s, o = subs[a], owners[a]
        role = classify_role("director" in o["rel"], "officer" in o["rel"],
                             "tenpercent" in o["rel"].replace(" ", "").replace("_", ""), o["title"])
        con.execute("""INSERT OR IGNORE INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (a, s["cik"], s["ticker"], s["name"], o["cik"], o["name"], role, o["title"], d,
                     s["filed"], s["filed"], g["sh"], g["val"] / g["sh"], g["val"], g["post"],
                     int(s["plan"]), "bulk"))
        n += 1
    con.execute("INSERT OR IGNORE INTO filings SELECT DISTINCT accession, filed_at, 1 FROM purchases")
    con.commit()
    return n


def cmd_backfill(args, con):
    edgar = Edgar(args.user_agent)
    today = dt.date.today()
    qs = []
    y, q = today.year, (today.month - 1) // 3 + 1
    for _ in range(args.quarters):
        qs.append((y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    for y, q in qs:
        url = BULK_URL.format(y=y, q=q)
        print(f"Downloading {y}Q{q} ...", file=sys.stderr)
        r = edgar.get(url)
        if r is None:
            print(f"  not available: {url}", file=sys.stderr)
            continue
        n = load_bulk_zip(con, io.BytesIO(r.content))
        print(f"  loaded {n} purchase rows", file=sys.stderr)


# --------------------------------------------------------------------------
# Price context (optional, only for the handful of candidate tickers)
# --------------------------------------------------------------------------
def fetch_history(ticker: str, start: dt.date, end: dt.date):
    """-> list of (date, close, volume). Returns [] if yfinance unavailable/fails."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        return [(i.date(), float(r["Close"]), float(r["Volume"])) for i, r in h.iterrows()]
    except Exception:
        return []


def price_features(ticker: str, today: dt.date | None = None):
    today = today or dt.date.today()
    h = fetch_history(ticker, today - dt.timedelta(days=380), today + dt.timedelta(days=1))
    if not h:
        return None
    closes = [c for _, c, _ in h]
    last = closes[-1]
    adv = statistics.mean(c * v for _, c, v in h[-20:])
    hi, lo = max(closes[-252:]), min(closes[-252:])
    ret63 = last / closes[-64] - 1 if len(closes) > 64 else None
    return {"last": last, "adv20": adv, "dist_hi": last / hi - 1, "dist_lo": last / lo - 1,
            "ret63": ret63, "n_days": len(h)}


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def _d(s):
    return dt.date.fromisoformat(s)


def history_features(con, owner_cik, issuer_cik, tx_date: str):
    """First-purchase and routine-trader checks from stored history."""
    td = _d(tx_date)
    lo = con.execute("SELECT MIN(tx_date) m FROM purchases").fetchone()["m"]
    coverage = (td - _d(lo)).days if lo else 0
    prior = con.execute(
        "SELECT COUNT(*) c FROM purchases WHERE owner_cik=? AND issuer_cik=? AND tx_date<? AND tx_date>=?",
        (owner_cik, issuer_cik, tx_date, (td - dt.timedelta(days=365)).isoformat())).fetchone()["c"]
    first = (prior == 0) if coverage >= 365 else None
    routine = None
    # history must reach back to the first day of the same calendar month three years ago
    if lo and lo <= f"{td.year - 3}-{td.month:02d}-01":
        hits = 0
        for k in (1, 2, 3):
            ym = f"{td.year - k}-{td.month:02d}"
            hits += con.execute(
                "SELECT COUNT(*) c FROM purchases WHERE owner_cik=? AND issuer_cik=? AND substr(tx_date,1,7)=?",
                (owner_cik, issuer_cik, ym)).fetchone()["c"] > 0
        routine = hits == 3
    return {"first_in_12m": first, "routine": routine, "coverage_days": coverage}


ENTITY_RE = re.compile(r"\b(fund|funds|partners|capital|ventures?|lp|l\.p\.|llc|management|advisors?|"
                       r"trust|holdings|investments?|equity|associates|gp)\b", re.I)


def family_key(name: str, owner_cik: str) -> str:
    """Funds from one sponsor (ARCH Venture Fund X / ARCH Venture Partners XIV) count as ONE insider."""
    if name and ENTITY_RE.search(name):
        toks = re.findall(r"[a-z]+", name.lower())
        toks = [t for t in toks if t not in ("the",)]
        if toks:
            return "fam:" + " ".join(toks[:2])
    return owner_cik


def collapse_rows(rows):
    """Drop the same lot reported twice by joint filers (identical date/shares/price and
    identical post-holdings, or identical lots >= $1M), and key owners by sponsor family."""
    seen, seen_lots, out = set(), set(), []
    for r in sorted(rows, key=lambda r: -ROLE_PTS[r["role"]]):
        lot = (r["tx_date"], round(r["shares"]), round(r["price"], 2))
        post = r["post_shares"]
        key = lot + ((round(post),) if post else ())
        if (post and key in seen) or (r["value"] >= 1_000_000 and lot in seen_lots):
            continue
        seen.add(key)
        seen_lots.add(lot)
        out.append(r)
    return out


def build_buyers(by_owner):
    """One entry per insider: who, position, when, how much, and holdings afterwards."""
    buyers = []
    for rs in by_owner.values():
        names = []
        for x in rs:
            if x["owner_name"] not in names:
                names.append(x["owner_name"])
        best = max(rs, key=lambda x: ROLE_PTS[x["role"]])
        shares = sum(x["shares"] for x in rs)          # internal only, never displayed
        value = sum(x["value"] for x in rs)
        label = " / ".join(names[:2]) + (f" +{len(names) - 2} more" if len(names) > 2 else "")
        newest = max(rs, key=lambda x: x["tx_date"])
        post = newest["post_shares"]
        px = value / shares if shares else 0.0
        hold_usd = round(post * px) if (post is not None and px) else None
        if post is None or not shares:
            pct = None
        elif post > shares:
            pct = round(shares / (post - shares), 3)     # purchase as % added to prior holdings
        else:
            pct = "new"                                   # no prior holdings: brand-new position
        buyers.append({
            "name": label, "role": best["role"], "title": best["title"] or best["role"].title(),
            "first_tx": min(x["tx_date"] for x in rs), "last_tx": max(x["tx_date"] for x in rs),
            "filed": max(x["filed_date"] for x in rs),
            "value": round(value), "holdings_after_usd": hold_usd, "pct_increase": pct,
        })
    buyers.sort(key=lambda b: (b["first_tx"], -b["value"]))
    return buyers


def score_issuer(con, issuer_cik, px=None, cfg=CFG):
    """Score an issuer's current insider-buying cluster. Returns dict or None."""
    latest = con.execute("SELECT MAX(tx_date) m FROM purchases WHERE issuer_cik=?", (issuer_cik,)).fetchone()["m"]
    if not latest:
        return None
    since = (_d(latest) - dt.timedelta(days=cfg["cluster_window_days"])).isoformat()
    rows = con.execute(
        """SELECT * FROM purchases WHERE issuer_cik=? AND tx_date>=? AND plan10b5=0 AND value>=?
           ORDER BY tx_date""", (issuer_cik, since, cfg["min_value_usd"])).fetchall()
    if not rows:
        return None
    rows = collapse_rows(rows)
    by_owner: dict = {}
    for r in rows:
        by_owner.setdefault(family_key(r["owner_name"], r["owner_cik"]), []).append(r)
    n = len(by_owner)
    lead_rows = max(by_owner.values(),
                    key=lambda rs: (ROLE_PTS[rs[0]["role"]], sum(x["value"] for x in rs)))
    lead = lead_rows[0]
    total_value = sum(r["value"] for r in rows)

    pts = {"role": ROLE_PTS[lead["role"]],
           "cluster": CLUSTER_PTS.get(n, CLUSTER_4PLUS) if n < 4 else CLUSTER_4PLUS}
    firsts = sorted(min(x["tx_date"] for x in rs) for rs in by_owner.values())
    tight = any((_d(b) - _d(a)).days <= cfg["tight_cluster_days"] for a, b in zip(firsts, firsts[1:]))
    if n >= 2 and tight:
        pts["cluster"] += TIGHT_CLUSTER_BONUS

    hist = history_features(con, lead["owner_cik"], issuer_cik, lead_rows[0]["tx_date"])
    flags = []
    if hist["first_in_12m"] is True:
        pts["first_buy"] = FIRST_PURCHASE_PTS
    elif hist["first_in_12m"] is None:
        pts["first_buy"] = FIRST_PURCHASE_UNVERIFIED_PTS
        flags.append("history_unverified(run backfill)")
    if hist["routine"] is True:
        pts["routine"] = ROUTINE_PENALTY
        flags.append("ROUTINE_PATTERN")
    elif hist["routine"] is None:
        flags.append("routine_unchecked")

    lead_sh = sum(x["shares"] for x in lead_rows)
    post = lead_rows[-1]["post_shares"]
    if post and post > lead_sh:
        inc = lead_sh / (post - lead_sh)
    else:
        inc = None if post is None else float("inf")
    if inc is not None:
        for thr, p in RELSIZE_PTS:
            if inc >= thr:
                pts["rel_size"] = p
                break

    ctx = {}
    if px:
        ctx = {"last": round(px["last"], 2), "adv20_usd": round(px["adv20"]),
               "dist_52w_high": round(px["dist_hi"], 3), "ret_63d": None if px["ret63"] is None else round(px["ret63"], 3)}
        if px["adv20"] > cfg["big_adv_usd"]:
            pts["big_adv"] = BIG_ADV_PENALTY
    else:
        flags.append("liquidity_unverified")

    lag = (_d(lead["filed_date"]) - _d(lead["tx_date"])).days
    if lag > cfg["late_filing_days"]:
        flags.append(f"LATE_FILING({lag}d)")
    if lead["role"] == "10%OWNER":
        flags.append("10pct_owner_only(weak evidence)")

    # Tag signals the retired floors ($25k size, $2 price) would have blocked or shrunk,
    # so forward-return tracking can compare them against the rest.
    old_size = cfg["legacy_min_value_usd"]
    old_px = cfg["legacy_min_price"]
    size_block = not any(x["value"] >= old_size for x in rows)
    last_px = px["last"] if px else None
    price_block = (last_px < old_px) if last_px is not None else all(x["price"] < old_px for x in rows)
    if size_block or price_block:
        why = "+".join(n for n, b in (("under25k", size_block), ("under2usd", price_block)) if b)
        flags.append(f"OLD_FILTER_WOULD_BLOCK({why})")
    elif any(x["value"] < old_size for x in rows):
        flags.append("OLD_FILTER_PARTIAL(buys under 25k included)")

    score = sum(pts.values())
    tier = "A" if score >= 60 else "B" if score >= cfg["alert_min_score"] else "C"
    acc = max(r["accession"] for r in rows)
    return {
        "issuer_cik": issuer_cik, "ticker": lead["ticker"], "issuer": lead["issuer_name"],
        "score": score, "tier": tier, "points": pts, "n_insiders": n, "tight_cluster": tight,
        "lead_role": lead["role"], "lead_owner": lead["owner_name"], "lead_title": lead["title"],
        "total_value": round(total_value), "holdings_increase": None if inc is None else (
            "new/>100%" if inc == float("inf") else round(inc, 3)),
        "window_start": min(r["tx_date"] for r in rows), "latest_tx": latest,
        "latest_filed": max(r["filed_date"] for r in rows),
        "latest_accession": acc, "flags": flags, "context": ctx,
        "buyers": build_buyers(by_owner),
    }


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def candidates(con, lookback_days: int, today: dt.date):
    since = (today - dt.timedelta(days=lookback_days)).isoformat()
    return [r["issuer_cik"] for r in con.execute(
        """SELECT DISTINCT issuer_cik FROM purchases
           WHERE filed_date>=? AND plan10b5=0 AND value>=?
             AND UPPER(COALESCE(ticker,'')) NOT IN ('', 'NONE', 'N/A', 'NA')""",
        (since, CFG["min_value_usd"]))]


def run_scoring(con, lookback_days, today=None, use_prices=True, edgar=None, recovered=()):
    today = today or dt.date.today()
    results = []
    for cik in dict.fromkeys([*candidates(con, lookback_days, today), *sorted(recovered)]):
        gap_failed = bool(edgar) and gapfill_issuer(edgar, con, cik, today) < 0
        px = None
        if use_prices:
            ticker = con.execute(
                "SELECT ticker FROM purchases WHERE issuer_cik=? LIMIT 1", (cik,)
            ).fetchone()["ticker"]
            px = price_features(ticker, today)
            if px and not math.isfinite(px["adv20"]):
                print(f"  skip {ticker} ({cik}): 20-day dollar volume unavailable", file=sys.stderr)
                continue
        if px and px.get("n_days", 999) < MIN_HISTORY_DAYS:
            print(f"  skip {cik}: only {px['n_days']} trading days of history (recent IPO)", file=sys.stderr)
            continue
        res = score_issuer(con, cik, px)
        if not res:
            continue
        if gap_failed:
            res["flags"].append("HISTORY_GAP")
        if px and px["adv20"] < CFG["min_adv_usd"]:
            continue                      # fails the $3M ADV liquidity floor
        results.append(res)
    return sorted(results, key=lambda r: -r["score"])


def log_signals(con, results, min_score, channels=()):
    new = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for r in results:
        if r["score"] < min_score:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO signals(detected_at,issuer_cik,ticker,latest_accession,latest_filed_date,score,tier,payload)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now, r["issuer_cik"], r["ticker"], r["latest_accession"], r["latest_filed"],
             r["score"], r["tier"], json.dumps(r)))
        if cur.rowcount:
            new.append(r)
    if new and channels:
        con.execute("INSERT INTO alert_outbox(payload, channels) VALUES (?,?)",
                    (json.dumps(new), json.dumps(channels)))
    con.commit()
    return new


def _money(v):
    return f"${v:,.0f}"


def _when(b):
    return b["first_tx"] if b["first_tx"] == b["last_tx"] else f"{b['first_tx']} to {b['last_tx']}"


def _pct(v):
    return "n/a" if v is None else format(v, "+.0%")


def _holdings(b):
    """-> (dollar value of holdings after the buy, % increase) as display strings.
    Falls back to the old share-based fields so previously logged signals still render."""
    usd, pct = b.get("holdings_after_usd"), b.get("pct_increase", "?")
    if usd is None and b.get("holdings_after") is not None and b.get("avg_price"):
        usd = b["holdings_after"] * b["avg_price"]
    if pct == "?":
        sh, post = b.get("shares"), b.get("holdings_after")
        pct = (sh / (post - sh) if post is not None and sh and post > sh else "new" if post is not None else None)
    usd_s = "n/a" if usd is None else _money(usd)
    pct_s = "n/a" if pct is None else ("new position" if pct == "new" else f"+{pct:.0%}")
    return usd_s, pct_s


BASIS = {
    "role": "CFO > CEO > other officers > directors; 10% owners weak (CXO Advisory summary of 1992-2002 data; Zhao 2026)",
    "cluster": "Several insiders buying beats one (Alldredge & Blank; cluster paper: 3.8% vs 2.0% over 21 days)",
    "first_buy": "First buy in 12 months beats repeat buys (Zhao 2026: 5.0% vs 2.7%)",
    "routine": "Same-month buying 3 years running = routine, ~0 edge (Cohen, Malloy, Pomorski 2012)",
    "rel_size": "Size relative to what they already own, not raw dollars (literature prior, not fitted)",
    "big_adv": "Signal weaker in very liquid large caps (CEO Watcher data; literature prior)",
}


def score_breakdown(r):
    """-> [(factor, what triggered it, points, evidence basis)] explaining the score."""
    if r.get("rule") == "research":
        return [(RULE_FACTORS[k][0], _research_detail(k, r), r["points"].get(k) or 0, RULE_FACTORS[k][1])
                for k in RULE_FACTORS]
    pts = r.get("points") or {}
    hi = r.get("holdings_increase")
    hi_s = "n/a" if hi is None else ("new position" if hi == "new/>100%" else f"+{hi:.0%}")
    detail = {
        "role": f"Lead buyer is {r.get('lead_role')} ({r.get('lead_owner')})",
        "cluster": f"{r.get('n_insiders')} separate insider(s) within {CFG['cluster_window_days']} days"
                   + (", two started within 2 days" if r.get("tight_cluster") else ""),
        "first_buy": "Verified first buy in 12 months" if pts.get("first_buy") == FIRST_PURCHASE_PTS
                     else "Could not verify buy history (half credit)",
        "routine": "Buys in this same month for 3 straight years",
        "rel_size": f"Lead buyer's holdings up {hi_s}",
        "big_adv": "Very liquid stock (avg daily volume over $100M)",
    }
    names = {"role": "Role", "cluster": "Cluster", "first_buy": "First buy", "routine": "Routine pattern",
             "rel_size": "Size vs holdings", "big_adv": "Large-cap penalty"}
    return [(names.get(k, k), detail.get(k, ""), v, BASIS.get(k, "")) for k, v in pts.items()]


def breakdown_line(r):
    return "; ".join(f"{f} {v:+.0f}" for f, _, v, _ in score_breakdown(r))


def buyer_lines(r):
    """Who bought, their position, how much in dollars, when, and what they hold afterwards."""
    out = []
    for b in r.get("buyers") or []:
        usd_s, pct_s = _holdings(b)
        out.append(f"  - {b['name']} ({b['title']}): bought {_money(b['value'])} ({pct_s} to holdings), "
                   f"now holds ~{usd_s}; bought {_when(b)}, filed {b['filed']}")
    return out


def signal_block(r):
    """Multi-line plain-text description of one signal."""
    if r.get("rule") == "research":
        lines = [f"{r['ticker']} - {research_headline(r)}: {r['n_insiders']} officers/directors bought "
                 f"${r['total_value']:,}, fourth filing {r['latest_filed']}"
                 + (f" [{' '.join(r['flags'])}]" if r.get("flags") else "")]
        lines += [f"  {k}: {v}" for k, v in r.get("stats", [])]
        lines += [f"  {x}" for x in research_lines(r)]
        lines.append(f"  Buy dates {r['window_start']} to {r['latest_tx']}")
        return "\n".join(lines + buyer_lines(r))
    c = r.get("context") or {}
    extra = f" | ADV ${c['adv20_usd'] / 1e6:.1f}M" if c.get("adv20_usd") is not None else ""
    flags = f" [{' '.join(r['flags'])}]" if r.get("flags") else ""
    lines = [f"{r['tier']}{r['score']:.0f} {r['ticker']} - {r['n_insiders']} insider(s), lead {r['lead_role']} "
             f"{r['lead_owner']}, ${r['total_value']:,} filed {r['latest_filed']}{extra}{flags}"]
    if r.get("window_start"):
        lines.append(f"  Buys dated {r['window_start']} to {r['latest_tx']}")
    lines += buyer_lines(r)
    if r.get("points"):
        lines.append(f"  Score: {breakdown_line(r)}")
    if c.get("last") is not None:
        lines.append(f"  Price ${c['last']:.2f}, {_pct(c.get('dist_52w_high'))} vs 52-wk high, "
                     f"63-day move {_pct(c.get('ret_63d'))}")
    return "\n".join(lines)


def format_alert(new, limit=3800) -> str:
    text = "\n\n".join(signal_block(r) for r in new)
    return text if len(text) <= limit else text[:limit - 20] + "\n...(truncated)"


def push_text(new, limit=1000) -> str:
    """Compact version for Pushover (1,024-character message cap)."""
    lines = []
    for r in new[:5]:
        c = r.get("context") or {}
        if r.get("rule") == "research":
            lines.append(f"{r['ticker']}: {research_headline(r)} - {r['n_insiders']} officers/directors bought "
                         f"${r['total_value']:,}")
            lines.append(f"Entry {dt.date.fromisoformat(r['entry_date']):%a %b %d} open, 21-session hold")
            for key, name in RULE_SHORT.items():
                p = r["points"].get(key)
                lines.append(f"{'+1' if p else ('?' if p is None else ' 0')} {name}{_research_value(key, r)}")
            if c.get("adv15") is not None:
                lines.append(f"Avg daily volume ${c['adv15'] / 1e6:.1f}M, last ${c['last']:.2f}")
            for b in (r.get("buyers") or [])[:4]:
                lines.append(f" {b['name']} ({b['title']}) {_money(b['value'])}")
            continue
        lines.append(f"{r['tier']}{r['score']:.0f} {r['ticker']} {r['n_insiders']} insider(s) ${r['total_value']:,}"
                     + (f" ADV${c['adv20_usd'] / 1e6:.1f}M" if c.get("adv20_usd") is not None else ""))
        for b in (r.get("buyers") or [])[:4]:
            lines.append(f" {b['name']} ({b['title']}) {_money(b['value'])} {_when(b)}")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _label(r) -> str:
    """Short rating label: 'Score 3 of 4' for the research rule, 'Tier A, score 72' for the old scorer."""
    if r.get("rule") == "research":
        return research_headline(r)
    return f"Tier {r['tier']}, score {r['score']:.0f}"


def email_html(new, heading) -> str:
    e = _html.escape
    out = [f"<div style='font-family:Arial,sans-serif;font-size:14px'><h2>{e(heading)}</h2>"]
    for r in new:
        c = r.get("context") or {}
        link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r['issuer_cik']}&type=4"
        out.append(f"<h3 style='margin-bottom:2px'>{e(r['ticker'])} - {e(r.get('issuer', ''))} "
                   f"<span style='color:#555'>({_label(r)})</span></h3>")
        meta = [f"{r['n_insiders']} insider(s)", f"{_money(r['total_value'])} total",
                f"buys {r.get('window_start', '?')} to {r.get('latest_tx', '?')}",
                f"latest filing {r.get('latest_filed', '?')}"]
        if c.get("adv20_usd") is not None:
            meta += [f"ADV ${c['adv20_usd'] / 1e6:.1f}M", f"{_pct(c.get('dist_52w_high'))} vs 52-wk high",
                     f"63-day {_pct(c.get('ret_63d'))}"]
        meta += [f"{k}: {v}" for k, v in r.get("stats", [])]
        out.append("<div style='color:#333'>" + " | ".join(e(m) for m in meta) + "</div>")
        if r.get("flags"):
            out.append(f"<div style='color:#a00'>Flags: {e(', '.join(r['flags']))}</div>")
        rows = ""
        for b in r.get("buyers") or []:
            usd_s, pct_s = _holdings(b)
            rows += (f"<tr><td>{e(b['name'])}</td><td>{e(b['title'])}</td><td>{e(_when(b))}</td>"
                     f"<td>{e(b['filed'])}</td>"
                     f"<td align='right'><b>{_money(b['value'])}</b></td>"
                     f"<td align='right'>{e(usd_s)}</td><td align='right'>{e(pct_s)}</td></tr>")
        if rows:
            out.append("<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;margin-top:6px'>"
                       "<tr style='background:#eee'><th>Insider</th><th>Position</th><th>Bought</th><th>Filed</th>"
                       "<th>$ bought</th><th>Holdings after ($)</th><th>Holdings increase</th></tr>" + rows + "</table>")
        bd = score_breakdown(r)
        if bd:
            out.append("<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;margin-top:8px'>"
                       "<tr style='background:#eee'><th>Score factor</th><th>What triggered it</th><th>Pts</th>"
                       "<th>Evidence basis</th></tr>"
                       + "".join(f"<tr><td>{e(f)}</td><td>{e(d)}</td><td align='right'><b>{v:+.0f}</b></td>"
                                 f"<td>{e(bs)}</td></tr>" for f, d, v, bs in bd) + "</table>")
        out.append(f"<div><a href='{e(link)}'>All Form 4 filings on SEC.gov</a></div>")
    out.append("</div>")
    return "".join(out)


REPORT_CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#14171a;--mute:#5b6570;--line:#e3e6ea;--a:#0a7d3b;--b:#1456c8;--c:#6b7280;--red:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#1a1f26;--ink:#e8ebef;--mute:#9aa4af;--line:#2b323b;--a:#3ecf7a;--b:#6ea2ff;--c:#9aa4af;--red:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 32px}
h1{font-size:1.9rem;margin:6px 0 4px}
.sub{color:var(--mute);font-size:.9rem;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px 28px;margin:20px 0}
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.tk{font-size:2rem;font-weight:700}
.iss{color:var(--mute);font-size:1.1rem}
.badge{border-radius:999px;padding:3px 11px;font-weight:700;font-size:.85rem;color:#fff}
.ta{background:var(--a)}.tb{background:var(--b)}.tc{background:var(--c)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
.stat{border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.stat b{display:block;font-size:1.05rem}.stat span{color:var(--mute);font-size:.78rem;text-transform:uppercase;letter-spacing:.03em}
.flags{color:var(--red);font-weight:600;margin:6px 0}
table.bt{width:100%;border-collapse:collapse;margin-top:6px;font-size:.98rem}
table.bt th{text-align:left;color:var(--mute);font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;border-bottom:2px solid var(--line);padding:8px 10px}
table.bt td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
table.bt td.n,table.bt th.n{text-align:right;white-space:nowrap}
.role{color:var(--mute);font-size:.88rem}
.btn{display:inline-block;margin-top:8px;padding:9px 14px;border-radius:10px;background:var(--b);color:#fff;text-decoration:none;font-weight:600}
details{margin:16px 0;color:var(--mute);font-size:.9rem}summary{cursor:pointer;font-weight:600;color:var(--ink)}
footer{color:var(--mute);font-size:.8rem;margin:20px 0 30px}
a{color:var(--b)}
ul.rep{list-style:none;padding:0;margin:0}
ul.rep li{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:10px 0}
ul.rep a{display:block;padding:12px 14px;text-decoration:none;color:var(--ink)}
ul.rep small{color:var(--mute);display:block}
"""

REPORT_HELP = (
    "<details><summary>How to read this</summary>"
    "<p><b>Tier / score:</b> the scanner's rating of how strong the buying pattern is. Higher means more insiders, "
    "more senior roles, bigger purchases compared with what they already own, and a stock that trades enough to act on.</p>"
    "<p><b>Insiders:</b> officers and directors of the company. Only purchases they made with their own money in the "
    "open market are counted.</p>"
    "<p><b>Avg daily $ volume:</b> roughly how many dollars of the stock change hands per day. Bigger means easier "
    "to buy and sell.</p>"
    "<p><b>Holdings after / increase:</b> estimated dollar value of what that person owns after the purchase, and how "
    "much the purchase added to their prior holdings in percent.</p>"
    "<p><b>Score breakdown:</b> the points each factor added, what triggered it, and the research it is based on. "
    "The weights are priors from the literature, not fitted to our own results yet.</p>"
    "<p><b>vs 52-week high:</b> how far the price is below its highest price of the past year.</p></details>"
)


RESEARCH_NOTE = (
    "<details open><summary>About this rule</summary>"
    "<p>An alert fires when four or more different officers or directors have bought with their own money "
    "(open market, not under a 10b5-1 plan, not automatic or dividend-reinvestment buys) within the 15 trading "
    "sessions before the entry open, and the stock trades at least $3M a day. The score adds one point for each of four "
    "conditions: no CEO or CFO among the buyers, the Nasdaq lagging the S&amp;P 500 over 63 sessions, the stock down "
    "15 or more ATR over 12 months, and the stock down 50% or more from its 12-month high. A question mark means that "
    "condition could not be checked.</p>"
    "<p><b>Status:</b> these are leads from the 2006-2020 development years. The one-time test on 2021-2025 "
    "(research log Entry 93) failed, so this is not a proven edge. Equal one-point weights are a placeholder, not fitted. "
    "ATR is the stock's average daily price range over 14 sessions.</p></details>")


def _ny_time(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return now


def _report_base_url() -> str:
    base = os.environ.get("REPORT_BASE_URL", "").strip()
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if "/" in repo:
            owner, name = repo.split("/", 1)
            base = f"https://{owner.lower()}.github.io/{name}/"
    return base if (not base or base.endswith("/")) else base + "/"


def _page(title: str, body: str) -> str:
    e = _html.escape
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{e(title)}</title><style>{REPORT_CSS}</style></head>"
            f"<body><div class='wrap'>{body}</div></body></html>")


def report_page(new, heading, now=None) -> str:
    """Full, phone-friendly HTML page for a batch of signals (what the alert links to)."""
    e = _html.escape
    ny = _ny_time(now)
    out = [f"<h1>{e(heading)}</h1><div class='sub'>{ny:%a %b %d, %Y %I:%M %p} Eastern - "
           f"<a href='index.html'>all reports</a></div>"]
    for r in new:
        c = r.get("context") or {}
        tier = str(r.get("tier", ""))
        badge = {"A": "ta", "B": "tb"}.get(tier, "tc")
        link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r['issuer_cik']}&type=4"
        stats = [("Insiders buying", str(r["n_insiders"])), ("Total bought", _money(r["total_value"])),
                 ("Buy dates", f"{r.get('window_start', '?')} to {r.get('latest_tx', '?')}"),
                 ("Latest filing", str(r.get("latest_filed", "?")))]
        if c.get("adv20_usd") is not None:
            stats += [("Avg daily $ volume", f"${c['adv20_usd'] / 1e6:.1f}M"),
                      ("Vs 52-week high", _pct(c.get("dist_52w_high"))), ("63-day move", _pct(c.get("ret_63d")))]
        if c.get("last") is not None and not r.get("rule"):
            stats.insert(2, ("Price", f"${c['last']:.2f}"))
        stats += r.get("stats", [])
        out.append("<div class='card'><div class='head'>"
                   f"<span class='tk'>{e(str(r['ticker']))}</span>"
                   f"<span class='badge {badge}'>{e(_label(r))}</span>"
                   f"<span class='iss'>{e(str(r.get('issuer', '')))}</span></div>")
        if r.get("flags"):
            out.append(f"<div class='flags'>Flags: {e(', '.join(r['flags']))}</div>")
        out.append("<div class='stats'>" + "".join(
            f"<div class='stat'><span>{e(k)}</span><b>{e(str(v))}</b></div>" for k, v in stats) + "</div>")
        rows = ""
        for b in r.get("buyers") or []:
            usd_s, pct_s = _holdings(b)
            rows += (f"<tr><td><b>{e(str(b['name']))}</b><div class='role'>{e(str(b['title']))}</div></td>"
                     f"<td>{e(_when(b))}</td><td>{e(str(b['filed']))}</td>"
                     f"<td class='n'><b>{e(_money(b['value']))}</b></td>"
                     f"<td class='n'>{e(usd_s)}</td><td class='n'>{e(pct_s)}</td></tr>")
        if rows:
            out.append("<table class='bt'><tr><th>Insider</th><th>Bought</th><th>Filed</th>"
                       "<th class='n'>$ bought</th><th class='n'>Holdings after ($)</th>"
                       "<th class='n'>Holdings increase</th></tr>" + rows + "</table>")
        bd = score_breakdown(r)
        if bd:
            out.append("<table class='bt'><tr><th>Score factor</th><th>What triggered it</th><th class='n'>Pts</th>"
                       "<th>Evidence basis</th></tr>"
                       + "".join(f"<tr><td>{e(f)}</td><td>{e(d)}</td><td class='n'><b>{v:+.0f}</b></td>"
                                 f"<td class='role'>{e(bs)}</td></tr>" for f, d, v, bs in bd) + "</table>")
        out.append(f"<a class='btn' href='{e(link)}'>All Form 4 filings on SEC.gov</a></div>")
    out.append(REPORT_HELP)
    if any(r.get("rule") == "research" for r in new):
        out.append(RESEARCH_NOTE)
    out.append("<footer>Research leads from public SEC Form 4 filings, not investment advice. "
               "Always check the filing yourself.</footer>")
    return _page(heading, "".join(out))


def index_page(items) -> str:
    e = _html.escape
    lis = "".join(
        f"<li><a href='reports/{e(i['file'])}'><b>{e(i['title'])}</b>"
        f"<small>{e(i['when'])} - {e(i['tickers'])}</small></a></li>" for i in items)
    body = ("<h1>Insider scanner reports</h1><div class='sub'>Newest first</div>"
            + (f"<ul class='rep'>{lis}</ul>" if lis else "<p>No reports yet.</p>"))
    return _page("Insider scanner reports", body)


def _git_publish(paths, msg) -> None:
    """In GitHub Actions only (PUBLISH_PUSH=1): commit and push the report files right away so the
    link in the alert goes live within a minute or two."""
    if os.environ.get("PUBLISH_PUSH") != "1":
        return
    import subprocess
    try:
        def run(*a):
            return subprocess.run(a, check=True, capture_output=True, text=True, timeout=90)
        run("git", "config", "user.name", "insider-scanner-bot")
        run("git", "config", "user.email", "insider-scanner-bot@users.noreply.github.com")
        run("git", "add", *paths)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode:
            run("git", "commit", "-m", msg)
            run("git", "push")
    except Exception as ex:
        print(f"report publish (git) failed: {ex}", file=sys.stderr)


def _wait_until_live(url, timeout=300, every=8) -> bool:
    """Poll until the report URL answers 200 so the alert never arrives before its page exists."""
    import requests
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(url, timeout=15).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


def publish_report(new, heading, name_hint="", docs_dir=None, now=None):
    """Write the report page + index into docs/ and return its public URL (None if no base URL)."""
    base = _report_base_url()
    if not base or not new:
        return None
    try:
        now = now or dt.datetime.now(dt.timezone.utc)
        docs = Path(docs_dir) if docs_dir else Path(__file__).resolve().parent / "docs"
        (docs / "reports").mkdir(parents=True, exist_ok=True)
        ny = _ny_time(now)
        top = max(new, key=lambda r: r["score"])["ticker"]
        fname = f"{ny:%Y%m%d-%H%M%S}-{re.sub('[^A-Za-z0-9]', '', name_hint or str(top))}.html"
        (docs / "reports" / fname).write_text(report_page(new, heading, now), encoding="utf-8")
        mpath = docs / "reports.json"
        items = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else []
        items.insert(0, {"file": fname, "title": heading, "when": f"{ny:%a %b %d %I:%M %p} ET",
                         "tickers": ", ".join(str(r["ticker"]) for r in new[:8])})
        items = items[:200]
        mpath.write_text(json.dumps(items), encoding="utf-8")
        (docs / "index.html").write_text(index_page(items), encoding="utf-8")
        (docs / ".nojekyll").touch()
        _git_publish([str(docs)], f"report: {heading}")
        url = f"{base}reports/{fname}"
        if os.environ.get("PUBLISH_PUSH") == "1":
            print("waiting for the report page to go live...")
            if not _wait_until_live(url):
                print("report page not live after 5 minutes; sending the alert anyway", file=sys.stderr)
        return url
    except Exception as ex:
        print(f"report publish failed: {ex}", file=sys.stderr)
        return None


def send_gmail(subject, body, html_body=None) -> bool:
    """Email via Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD -> ALERT_EMAIL). Returns True if sent."""
    user, pw = os.environ.get("GMAIL_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not (user and pw):
        return False
    m = EmailMessage()
    m["Subject"], m["From"] = subject, user
    m["To"] = os.environ.get("ALERT_EMAIL", user).strip() or user
    m.set_content(body)
    if html_body:
        m.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as sm:
        sm.login(user, pw)
        sm.send_message(m)
    return True


def notify(title: str, body: str, priority: str = "default", html_body: str | None = None,
           push_body: str | None = None, url: str | None = None, channels=None) -> list:
    """Push via ntfy (NTFY_TOPIC), Pushover, and/or email via Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD).
    Never raises. Returns the channels that worked."""
    sent = []
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic and (channels is None or "ntfy" in channels):
        try:
            import requests
            headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority}
            if url:
                headers["Click"] = url
            to_addr = os.environ.get("ALERT_EMAIL", "").strip()
            if to_addr and not (os.environ.get("GMAIL_USER", "").strip() and os.environ.get("GMAIL_APP_PASSWORD", "").strip()):
                headers["X-Email"] = to_addr      # ntfy also forwards the alert to this email address
            r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=20, headers=headers)
            r.raise_for_status()
            sent.append("ntfy+email" if "X-Email" in headers else "ntfy")
        except Exception as e:
            print(f"ntfy failed: {e}", file=sys.stderr)
    po_tok, po_usr = os.environ.get("PUSHOVER_TOKEN", "").strip(), os.environ.get("PUSHOVER_USER", "").strip()
    if po_tok and po_usr and (channels is None or "pushover" in channels):
        try:
            import requests
            po = {"token": po_tok, "user": po_usr, "title": title[:240],
                  "message": (push_body or body)[:1000], "priority": 1 if priority == "high" else 0}
            if url:
                po.update({"url": url, "url_title": "Open full report"})
            r = requests.post("https://api.pushover.net/1/messages.json", timeout=20, data=po)
            r.raise_for_status()
            sent.append("pushover")
        except Exception as e:
            print(f"pushover failed: {e}", file=sys.stderr)
    try:
        if url:
            body = f"{body}\n\nFull report: {url}"
            if html_body:
                html_body += f"<p><a href='{_html.escape(url)}'>Open the full report</a></p>"
        if (channels is None or "email" in channels) and send_gmail(title, body, html_body):
            sent.append("email")
    except Exception as e:
        print(f"email failed: {e}", file=sys.stderr)
    if not sent:
        print("(no alert channel configured or all failed)", file=sys.stderr)
    return sent


def should_alert_failure(con, key, hours=None, now=None) -> bool:
    """True at most once per `hours` per command, so a 30-minute schedule does not buzz
    your phone all night during an SEC outage."""
    hours = CFG["failure_alert_hours"] if hours is None else hours
    now = now or dt.datetime.now(dt.timezone.utc)
    row = con.execute("SELECT value FROM meta WHERE key=?", (f"fail_alert_{key}",)).fetchone()
    if row and now - dt.datetime.fromisoformat(row["value"]) < dt.timedelta(hours=hours):
        return False
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"fail_alert_{key}", now.isoformat()))
    con.commit()
    return True


def alert_new(new, **delivery):
    """One alert for a batch of new signals: full detail by email, compact by push."""
    top = max(r["score"] for r in new)
    best = max(new, key=lambda r: r["score"])
    if all(r.get("rule") == "research" for r in new):
        title = (f"Insider cluster {best['ticker']}: score {top} of 4" if len(new) == 1 else
                 f"Insider clusters: {len(new)} new, top {best['ticker']} (score {top} of 4)")
        priority = "high" if top >= RULE["high_priority_score"] else "default"
    else:
        title = f"Insider buys: {len(new)} new signal(s), top {best['ticker']} ({top:.0f})"
        priority = "high" if top >= 60 else "default"
    url = publish_report(new, title)
    return notify(title, format_alert(new), priority,
                  html_body=email_html(new, title), push_body=push_text(new), url=url, **delivery)


def cmd_notify_test(args, con):
    names = [("Doe Jane", "CFO", "Chief Financial Officer"), ("Roe Richard", "DIRECTOR", "Director"),
             ("Poe Ann", "DIRECTOR", "Director"), ("Lee Sam", "OFFICER", "EVP, Operations")]
    rows = [{"accession": f"T-{i}", "owner_cik": str(i), "owner_name": n, "role": ro, "title": ti, "tx_date": "2026-11-04",
             "filed_date": "2026-11-05", "filed_at": "2026-11-05T10:00:00-05:00", "shares": 10000.0, "price": 10.0 + i,
             "value": 100000.0 + i, "post_shares": 60000.0, "ticker": "TEST", "issuer_name": "Test Corp"}
            for i, (n, ro, ti) in enumerate(names, 1)]
    ev = {"entry": dt.date(2026, 11, 6), "window_start": "2026-10-15", "completed_at": filed_datetime(rows[-1]),
          "owners": {r["owner_cik"]: [r] for r in rows}, "counted": rows, "accession": "T-4"}
    feats = {"adv15": 12_500_000.0, "last": 11.0, "atr": 0.5, "fall_atr": -17.2, "drawdown": 0.61, "lead63": -0.031}
    rsample = [build_research_result(ev, feats, "TEST", "Test Corp", "1")]
    url = publish_report(rsample, "Insider scanner test (sample data)", name_hint="TEST")
    print("report link:", url or "none (no GITHUB_REPOSITORY / REPORT_BASE_URL)")
    sent = notify("Insider scanner test (sample data)", format_alert(rsample), "default",
                  html_body=email_html(rsample, "Insider scanner test (sample data)"), push_body=push_text(rsample),
                  url=url)
    print("sent via:", sent or "NOTHING (check NTFY_TOPIC / PUSHOVER_* / GMAIL_* settings)")


def append_signal_log(new, path):
    if not path or not new:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps({"detected_at": now, **r}) + "\n")


def restore_signals(con, path) -> int:
    """If the DB was rebuilt (cache lost) re-create the signals table from the committed log."""
    if not path or not Path(path).exists():
        return 0
    if con.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]:
        return 0
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO signals(detected_at,issuer_cik,ticker,latest_accession,latest_filed_date,score,tier,payload)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (r.get("detected_at"), r["issuer_cik"], r["ticker"], r["latest_accession"], r["latest_filed"],
             r["score"], r["tier"], json.dumps({k: v for k, v in r.items() if k != "detected_at"})))
        n += cur.rowcount
    con.commit()
    return n


def print_results(results):
    if not results:
        print("No new signals above threshold.")
        return
    for r in results:
        print(signal_block(r))
        print()


def write_csv(results, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"signals_{dt.datetime.now():%Y%m%d_%H%M}.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tier", "score", "ticker", "issuer", "n_insiders", "tight_cluster", "lead_role",
                    "lead_owner", "lead_title", "total_value", "holdings_increase", "buys_from", "latest_tx",
                    "latest_filed", "flags", "adv20_usd", "dist_52w_high", "ret_63d", "points", "score_breakdown", "buyers"])
        for r in results:
            c = r["context"] or {}
            w.writerow([r["tier"], r["score"], r["ticker"], r["issuer"], r["n_insiders"], r["tight_cluster"],
                        r["lead_role"], r["lead_owner"], r["lead_title"], r["total_value"],
                        r["holdings_increase"], r.get("window_start"), r["latest_tx"], r["latest_filed"],
                        ";".join(r["flags"]), c.get("adv20_usd"), c.get("dist_52w_high"), c.get("ret_63d"),
                        json.dumps(r["points"]), breakdown_line(r),
                        "; ".join(f"{b['name']} ({b['title']}) {_money(b['value'])} on {_when(b)}"
                                  for b in r.get("buyers") or [])])
    return p


# ==========================================================================
# RESEARCH RULE: the cluster rule and 0-4 score from the insider-buying-research study
# (repo kidcharlema9ne/insider-buying-research: D-057, D-064, D-065, D-066 in docs/DECISION_LOG.md;
#  Entries 36, 37, 41, 66, 67 in docs/SHARED_LOG.md). The sealed-year test (Entry 93) FAILED, so this is
#  a lead the owner wants to watch live, not a proven edge. Alerts say so in the report footer.
# ==========================================================================
RULE = {
    "min_buyers": 4,                 # distinct officers/directors (D-057)
    "window_sessions": 15,           # completed sessions before the entry open
    "adv_floor_usd": 3_000_000,      # average daily dollar volume over those 15 sessions
    "atr_bars": 14,
    "hold_sessions": 21,             # price-only hold, entry session = day one (also the repeat-event lockout, D-065)
    "nasdaq_lag_cut": -0.0195,       # Nasdaq (ONEQ) 63-session move minus SPY's at or below this (Entry 41 cut)
    "fall_atr": -15.0,               # 252-session close change in ATR units at or below this (Entry 67)
    "drawdown": 0.50,                # down at least 50% from the highest close of the prior 252 sessions (Entry 66)
    "high_priority_score": 3,        # Pushover high priority at this score or above
}
RULE_ROLES = ("CEO", "CFO", "OFFICER", "DIRECTOR")      # 10% owners and "other" holders do not count
NYSE_HOLIDAYS = {dt.date(*d) for d in [
    (2025, 1, 1), (2025, 1, 9), (2025, 1, 20), (2025, 2, 17), (2025, 4, 18), (2025, 5, 26), (2025, 6, 19),
    (2025, 7, 4), (2025, 9, 1), (2025, 11, 27), (2025, 12, 25),
    (2026, 1, 1), (2026, 1, 19), (2026, 2, 16), (2026, 4, 3), (2026, 5, 25), (2026, 6, 19),
    (2026, 7, 3), (2026, 9, 7), (2026, 11, 26), (2026, 12, 25),
    (2027, 1, 1), (2027, 1, 18), (2027, 2, 15), (2027, 3, 26), (2027, 5, 31), (2027, 6, 18),
    (2027, 7, 5), (2027, 9, 6), (2027, 11, 25), (2027, 12, 24)]}

RULE_FACTORS = {   # key -> (plain-words name, evidence basis shown in the report)
    "no_ceo_cfo": ("No CEO and no CFO among the buyers",
                   "Development years 2006-2020: +0.12 ATR vs SPY, range -0.13 to +0.37 (Entry 67); weakest of the four"),
    "nasdaq_lag": ("Nasdaq lagging the S&P 500 over 63 sessions (by 1.95 points or more)",
                   "Development: +0.50 ATR, range +0.11 to +0.93 (Entry 67); a one-month effect with no known mechanism (Entry 37)"),
    "deep_fall": ("Stock down 15+ ATR over the past 12 months",
                  "Development: +0.60 ATR alone (Entry 67); survivorship and costs unresolved (Entries 65, 70)"),
    "drawdown": ("Stock down 50%+ from its 12-month high",
                 "Development: +0.47 ATR alone, a step at 50% (Entry 66); adds an unproven +0.33 on top of the 15-ATR fall (Entry 67)"),
}
ET_NAME = "America/New_York"


def _et():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(ET_NAME)
    except Exception:
        return dt.timezone(dt.timedelta(hours=-5))


def is_session(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def next_session(d: dt.date) -> dt.date:
    """First trading session strictly after d."""
    d += dt.timedelta(days=1)
    while not is_session(d):
        d += dt.timedelta(days=1)
    return d


def sessions_before(entry: dt.date, n: int):
    """The n trading sessions completed before `entry`, oldest first."""
    out, d = [], entry
    while len(out) < n:
        d -= dt.timedelta(days=1)
        if is_session(d):
            out.append(d)
    return out[::-1]


def sessions_between(a: dt.date, b: dt.date) -> int:
    """Number of sessions d with a <= d < b."""
    n, d = 0, a
    while d < b:
        n += is_session(d)
        d += dt.timedelta(days=1)
    return n


def filed_datetime(r) -> dt.datetime:
    """Filing time in Eastern. A date-only stamp counts as filed at the end of that day."""
    s = (r["filed_at"] or r["filed_date"] or "").strip()
    et = _et()
    if len(s) <= 10:
        return dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(23, 59, 59), tzinfo=et)
    x = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return x.replace(tzinfo=et) if x.tzinfo is None else x.astimezone(et)


def entry_session(filed: dt.datetime) -> dt.date:
    """Next regular open at or after the filing time (9:30 ET)."""
    d = filed.date()
    if is_session(d) and filed.time() < dt.time(9, 30):
        return d
    return next_session(d)


def _rowkey(r):
    return (r["accession"], r["owner_cik"], r["tx_date"])


def routine_rows(rows):
    """D-064 (a): three or more different buyers on one date at one price (within a cent) look plan-like.
    Returns the set of row keys to leave out of the count."""
    flagged, by_date = set(), {}
    for r in rows:
        by_date.setdefault(r["tx_date"], []).append(r)
    for rs in by_date.values():
        rs = sorted(rs, key=lambda r: r["price"])
        i = 0
        while i < len(rs):
            grp, j = [rs[i]], i + 1
            while j < len(rs) and rs[j]["price"] - rs[i]["price"] <= 0.01 + 1e-9:
                grp.append(rs[j])
                j += 1
            if len({family_key(g["owner_name"], g["owner_cik"]) for g in grp}) >= 3:
                flagged.update(_rowkey(g) for g in grp)
            i = j
    return flagged


def issuer_is_routine(con, issuer_cik, filing_date: dt.date) -> bool:
    """D-064 (b): the issuer already showed the same-date same-price pattern in 2 of the 3 calendar months
    before the filing month."""
    hits, y, m = 0, filing_date.year, filing_date.month
    for _ in range(3):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM purchases WHERE issuer_cik=? AND substr(tx_date,1,7)=?", (issuer_cik, f"{y}-{m:02d}"))]
        hits += bool(routine_rows(rows))
    return hits >= 2


def research_event(con, issuer_cik, today=None):
    """-> (event or None, reason). The event is the first filing that brings the count of distinct officers
    and directors with a purchase inside the 15 sessions before entry to four, counting only filings already
    public at that moment (D-057)."""
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=60)).isoformat()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM purchases WHERE issuer_cik=? AND plan10b5=0 AND tx_date>=? ORDER BY filed_at",
        (issuer_cik, since))]
    if not rows:
        return None, "no purchases"
    rows = collapse_rows(rows)
    flagged = routine_rows(rows)
    cand = [r for r in rows if r["role"] in RULE_ROLES and not ENTITY_RE.search(r["owner_name"] or "")
            and _rowkey(r) not in flagged]
    best = 0
    for t in sorted({filed_datetime(r) for r in cand}):
        entry = entry_session(t)
        lo = sessions_before(entry, RULE["window_sessions"])[0].isoformat()
        counted = [r for r in cand if filed_datetime(r) <= t and lo <= r["tx_date"] < entry.isoformat()]
        owners: dict = {}
        for r in counted:
            owners.setdefault(family_key(r["owner_name"], r["owner_cik"]), []).append(r)
        best = max(best, len(owners))
        if len(owners) >= RULE["min_buyers"]:
            if issuer_is_routine(con, issuer_cik, t.date()):
                return None, "routine issuer (D-064 b)"
            done = [r for r in counted if filed_datetime(r) == t]
            return {"entry": entry, "window_start": lo, "completed_at": t, "owners": owners, "counted": counted,
                    "accession": max(r["accession"] for r in done), "routine_left_out": len(flagged)}, None
    left = len(flagged)
    return None, (f"only {best} distinct officers/directors in the window (needs 4)"
                  + (f"; {left} plan-like purchase(s) left out (D-064)" if left else "")) if cand else \
        "no officer/director purchases that count (10% owners, funds, plan or automatic buys do not)"


def in_prior_hold(con, issuer_cik, entry: dt.date, accession: str) -> bool:
    """D-065: after an event, ignore the issuer until that event's 21-session hold has ended."""
    for row in con.execute("SELECT latest_accession, payload FROM signals WHERE issuer_cik=?", (issuer_cik,)):
        if row["latest_accession"] == accession:
            continue
        try:
            p = json.loads(row["payload"])
        except ValueError:
            continue
        if p.get("rule") != "research" or not p.get("entry_date"):
            continue
        prev = dt.date.fromisoformat(p["entry_date"])
        if prev <= entry and sessions_between(prev, entry) < RULE["hold_sessions"]:
            return True
    return False


# ---- prices -------------------------------------------------------------
def fetch_bars(ticker: str, start: dt.date, end: dt.date):
    """-> [(date, open, high, low, close, volume)] oldest first; [] when yfinance is unavailable or fails."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        return [(i.date(), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), float(r["Volume"]))
                for i, r in h.iterrows() if math.isfinite(float(r["Close"]))]
    except Exception:
        return []


def _close_on_or_before(bars, d, back=3):
    """Close on date d, or on one of up to `back` sessions earlier (as in the study's feature code)."""
    idx = {b[0]: b[4] for b in bars}
    day = d
    for _ in range(back + 1):
        if day in idx:
            return idx[day]
        day -= dt.timedelta(days=1)
    return None


def research_features(stock, spy, oneq, entry: dt.date):
    """Everything the score needs, using only sessions strictly before `entry`. Missing pieces are None."""
    out = {"adv15": None, "last": None, "atr": None, "fall_atr": None, "drawdown": None, "lead63": None}
    sb = [b for b in stock if b[0] < entry]
    if sb:
        out["last"] = sb[-1][4]
    n = RULE["window_sessions"]
    if len(sb) >= n:
        out["adv15"] = statistics.mean(b[4] * b[5] for b in sb[-n:])
    k = RULE["atr_bars"]
    if len(sb) >= k + 1:
        trs = [max(sb[i][2] - sb[i][3], abs(sb[i][2] - sb[i - 1][4]), abs(sb[i][3] - sb[i - 1][4]))
               for i in range(len(sb) - k, len(sb))]
        atr = sum(trs) / k
        if atr > 0:
            out["atr"] = atr
            if len(sb) >= 253:
                out["fall_atr"] = (sb[-1][4] - sb[-1 - 252][4]) / atr
    if len(sb) >= 200:
        hi = max(b[4] for b in sb[-252:])
        out["drawdown"] = 1 - sb[-1][4] / hi
    sp = [b for b in spy if b[0] < entry]
    if len(sp) >= 64 and oneq:
        d_last, d_ref = sp[-1][0], sp[-1 - 63][0]
        o_last, o_ref = _close_on_or_before(oneq, d_last, 0), _close_on_or_before(oneq, d_ref)
        if o_last and o_ref:
            out["lead63"] = (o_last / o_ref - 1) - (sp[-1][4] / sp[-1 - 63][4] - 1)
    return out


def _bars(cache, bars_fn, ticker, today):
    """Price history for one scan: each ticker (SPY and ONEQ included) is downloaded once per scan."""
    if ticker not in cache:
        cache[ticker] = bars_fn(ticker, today - dt.timedelta(days=460), today + dt.timedelta(days=1))
    return cache[ticker]


# ---- scoring ------------------------------------------------------------
def score_research(event, feats):
    """-> (points {factor: 1/0/None}, score, how many factors could be checked). None = could not check."""
    f = feats or {}
    roles = {r["role"] for r in event["counted"]}
    pts = {"no_ceo_cfo": 0 if roles & {"CEO", "CFO"} else 1}
    pts["nasdaq_lag"] = None if f.get("lead63") is None else int(f["lead63"] <= RULE["nasdaq_lag_cut"])
    pts["deep_fall"] = None if f.get("fall_atr") is None else int(f["fall_atr"] <= RULE["fall_atr"])
    pts["drawdown"] = None if f.get("drawdown") is None else int(f["drawdown"] >= RULE["drawdown"])
    known = [v for v in pts.values() if v is not None]
    return pts, sum(known), len(known)


def _research_detail(key, r):
    c = r.get("context") or {}
    p = r["points"].get(key)
    if p is None:
        return "Could not be checked (price data unavailable or under a year of history)"
    if key == "no_ceo_cfo":
        return "Buyers include a CEO or CFO" if not p else "No CEO or CFO among the buyers"
    if key == "nasdaq_lag":
        return f"Nasdaq minus S&P 500 over 63 sessions: {c['lead63'] * 100:+.2f} points"
    if key == "deep_fall":
        return f"12-month change: {c['fall_atr']:+.1f} ATR (trigger: -15 or lower)"
    return f"{c['drawdown']:.0%} below the 12-month closing high (trigger: 50%)"


def build_research_result(event, feats, ticker, issuer, issuer_cik, flags=()):
    pts, score, checked = score_research(event, feats)
    owners = event["owners"]
    buyers = build_buyers(owners)
    rows = event["counted"]
    lead_rows = max(owners.values(), key=lambda rs: (ROLE_PTS[rs[0]["role"]], sum(x["value"] for x in rs)))
    f = feats or {}
    ctx = {k: f.get(k) for k in ("last", "adv15", "atr", "fall_atr", "drawdown", "lead63")}
    entry = event["entry"]
    last_day = entry
    for _ in range(RULE["hold_sessions"] - 1):
        last_day = next_session(last_day)
    stats = [("Planned entry", f"{entry:%a %b %d} open (next open after the filing that made four)"),
             ("21-session hold", f"entry day is day one; day 21 is {last_day:%a %b %d}")]
    if f.get("adv15") is not None:
        stats.append(("Avg daily $ volume (15 sessions)", f"${f['adv15'] / 1e6:.1f}M"))
    if f.get("last") is not None:
        stats.append(("Last close", f"${f['last']:.2f}"))
    return {
        "rule": "research", "issuer_cik": issuer_cik, "ticker": ticker, "issuer": issuer,
        "score": score, "score_max": 4, "checked": checked, "tier": "R", "points": pts,
        "n_insiders": len(owners), "tight_cluster": False, "lead_role": lead_rows[0]["role"],
        "lead_owner": lead_rows[0]["owner_name"], "lead_title": lead_rows[0]["title"],
        "total_value": round(sum(r["value"] for r in rows)), "holdings_increase": None,
        "window_start": min(r["tx_date"] for r in rows), "latest_tx": max(r["tx_date"] for r in rows),
        "latest_filed": event["completed_at"].date().isoformat(), "latest_accession": event["accession"],
        "entry_date": entry.isoformat(), "flags": list(flags), "context": ctx, "buyers": buyers, "stats": stats,
        "routine_left_out": event.get("routine_left_out", 0),
    }


def _research_value(key, r) -> str:
    """Short measured value for the push line, e.g. ' (-17.2)'. Empty when the factor could not be checked."""
    c = r.get("context") or {}
    v = {"nasdaq_lag": ("lead63", lambda x: f"{x * 100:+.1f} pts"), "deep_fall": ("fall_atr", lambda x: f"{x:+.1f} ATR"),
         "drawdown": ("drawdown", lambda x: f"-{x:.0%}")}.get(key)
    return f" ({v[1](c[v[0]])})" if v and c.get(v[0]) is not None else ""


def research_lines(r):
    """Plain-words factor lines used by the push message and the text alert."""
    out = []
    for key, (name, _) in RULE_FACTORS.items():
        p = r["points"].get(key)
        out.append(f"{'+1' if p else ('?' if p is None else ' 0')}  {name}")
    return out


def research_headline(r):
    s = f"Score {r['score']} of {r.get('score_max', 4)}"
    if r.get("checked", 4) < 4:
        s += f" ({4 - r['checked']} could not be checked)"
    return s


def run_research(con, lookback_days, today=None, use_prices=True, edgar=None, recovered=(), bars_fn=None):
    """Scan the database for clusters that meet the research rule. -> results sorted by score."""
    today = today or dt.date.today()
    bars_fn = bars_fn or fetch_bars
    since = (today - dt.timedelta(days=lookback_days)).isoformat()
    roles = ",".join("'%s'" % x for x in RULE_ROLES)
    ciks = [r["issuer_cik"] for r in con.execute(
        f"""SELECT DISTINCT issuer_cik FROM purchases
            WHERE filed_date>=? AND plan10b5=0 AND role IN ({roles})
              AND UPPER(COALESCE(ticker,'')) NOT IN ('', 'NONE', 'N/A', 'NA')""", (since,))]
    results, cache = [], {}
    for cik in dict.fromkeys([*ciks, *sorted(recovered)]):
        gap_failed = bool(edgar) and gapfill_issuer(edgar, con, cik, today) < 0
        event, why = research_event(con, cik, today)
        if not event:
            tk = con.execute("SELECT ticker FROM purchases WHERE issuer_cik=? LIMIT 1", (cik,)).fetchone()
            print(f"  no event {tk['ticker'] if tk else cik}: {why}", file=sys.stderr)
            continue
        if event["completed_at"].date().isoformat() < since:
            continue                              # the fourth buyer filed before this scan's look-back: not new
        if in_prior_hold(con, cik, event["entry"], event["accession"]):
            print(f"  skip {cik}: still inside an earlier event's 21-session hold (D-065)", file=sys.stderr)
            continue
        lead = next(iter(event["owners"].values()))[0]
        ticker, issuer = lead["ticker"], lead["issuer_name"]
        flags = []
        feats = None
        if use_prices:
            feats = research_features(_bars(cache, bars_fn, ticker, today), _bars(cache, bars_fn, "SPY", today),
                                      _bars(cache, bars_fn, "ONEQ", today), event["entry"])
            if feats["adv15"] is None:
                flags.append("liquidity_unverified")
            elif feats["adv15"] < RULE["adv_floor_usd"]:
                print(f"  skip {ticker}: average daily dollar volume ${feats['adv15'] / 1e6:.1f}M is under the "
                      f"$3M floor", file=sys.stderr)
                continue
        else:
            flags.append("prices_not_checked")
        if gap_failed:
            flags.append("HISTORY_GAP")
        results.append(build_research_result(event, feats, ticker, issuer, cik, flags))
    return sorted(results, key=lambda r: (-r["score"], r["ticker"]))


RULE_SHORT = {
    "no_ceo_cfo": "No CEO or CFO among buyers",
    "nasdaq_lag": "Nasdaq lagging S&P 500 (63 days)",
    "deep_fall": "Down 15+ ATR over 12 months",
    "drawdown": "Down 50%+ from 12-month high",
}


def configured_channels():
    credentials = {
        "ntfy": ("NTFY_TOPIC",),
        "pushover": ("PUSHOVER_TOKEN", "PUSHOVER_USER"),
        "email": ("GMAIL_USER", "GMAIL_APP_PASSWORD"),
    }
    return [channel for channel, names in credentials.items()
            if all(os.environ.get(name, "").strip() for name in names)]


def deliver_pending_alerts(con):
    for row in con.execute("SELECT * FROM alert_outbox ORDER BY id").fetchall():
        channels = json.loads(row["channels"])
        sent = alert_new(json.loads(row["payload"]), channels=channels)
        accepted = {"ntfy" if channel == "ntfy+email" else channel for channel in sent}
        remaining = [channel for channel in channels if channel not in accepted]
        if remaining:
            con.execute("UPDATE alert_outbox SET channels=? WHERE id=?",
                        (json.dumps(remaining), row["id"]))
        else:
            con.execute("DELETE FROM alert_outbox WHERE id=?", (row["id"],))
        con.commit()


def cmd_scan(args, con):
    edgar = Edgar(args.user_agent)
    restore_signals(con, args.signals_log)
    items, seen = [], set()
    today = dt.date.today()
    if args.source in ("atom", "both"):
        items += discover_atom(edgar, con, args.max_pages)
    if args.source in ("daily", "both"):
        days = [dt.date.fromisoformat(args.date)] if args.date else [
            today - dt.timedelta(days=k) for k in range(args.daily_days)]
        for day in days:
            items += discover_daily(edgar, con, day)
    items.extend(tuple(row) for row in con.execute(
        "SELECT accession, filed_at, url FROM filing_retries WHERE accession NOT IN (SELECT accession FROM filings)"))
    items = [x for x in items if not (x[0] in seen or seen.add(x[0]))]
    print(f"{len(items)} new Form 4 filings to parse", file=sys.stderr)
    recovered = set()
    n = ingest(edgar, con, items, recovered=recovered)
    print(f"{n} open-market purchase rows stored", file=sys.stderr)
    research = args.rule == "research"
    if research:
        results = run_research(con, args.lookback_days, use_prices=not args.no_prices, edgar=edgar,
                               recovered=recovered)
    else:
        results = run_scoring(con, args.lookback_days, use_prices=not args.no_prices, edgar=edgar,
                              recovered=recovered)
    min_score = -1 if research else args.min_score        # the research rule alerts on every qualifying cluster
    channels = configured_channels() if not (args.no_alert or args.fresh) else []
    new = log_signals(con, results, min_score, channels=channels)
    if args.fresh:
        # One-off "first full run": report every current signal, even ones already alerted before.
        new = [r for r in results if r["score"] >= min_score]
        print(f"FRESH RUN: reporting all {len(new)} current signals (dedupe bypassed)", file=sys.stderr)
    print_results(new)
    if new:
        print(f"\nCSV: {write_csv(new, Path(args.home) / 'out')}")
        if not args.fresh:
            append_signal_log(new, args.signals_log)
        if args.fresh and not args.no_alert:
            alert_new(new)
    if not args.no_alert:
        deliver_pending_alerts(con)


def cmd_report(args, con):
    rows = con.execute("SELECT payload FROM signals WHERE detected_at>=? ORDER BY score DESC",
                       ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)).isoformat(),)).fetchall()
    print_results([json.loads(r["payload"]) for r in rows])


HORIZONS = (5, 21, 63, 126, 252)


def compute_outcomes(con, today=None, history=fetch_history):
    """Forward returns vs SPY. Entry = first close strictly after the filing date."""
    today = today or dt.date.today()
    spy_cache = {}
    for s in con.execute("SELECT id, ticker, latest_filed_date FROM signals").fetchall():
        filed = _d(s["latest_filed_date"])
        h = history(s["ticker"], filed, min(today, filed + dt.timedelta(days=400)) + dt.timedelta(days=1))
        if "SPY" not in spy_cache:
            spy_cache["SPY"] = history("SPY", filed - dt.timedelta(days=5), today + dt.timedelta(days=1))
        spy = {d: c for d, c, _ in spy_cache["SPY"]}
        h = [(d, c) for d, c, _ in h if d > filed]
        if not h:
            continue
        entry_d, entry_c = h[0]
        for hz in HORIZONS:
            if len(h) <= hz:
                continue
            d_end, c_end = h[hz]
            spy_start, spy_end = spy.get(entry_d), spy.get(d_end)
            spy_ret = (spy_end / spy_start - 1) if spy_start and spy_end else None
            con.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?)",
                        (s["id"], hz, c_end / entry_c - 1, spy_ret))
    con.commit()


def track_rows(con):
    out = []
    for tier in ("A", "B", "C"):
        for hz in HORIZONS:
            rows = con.execute(
                """SELECT o.ret, o.spy_ret FROM outcomes o JOIN signals s ON s.id=o.signal_id
                   WHERE s.tier=? AND o.horizon=? AND o.spy_ret IS NOT NULL""", (tier, hz)).fetchall()
            ex = [r["ret"] - r["spy_ret"] for r in rows]
            if ex:
                out.append((tier, hz, len(ex), statistics.mean(ex), statistics.median(ex),
                            sum(e > 0 for e in ex) / len(ex)))
    return out


def research_track_rows(con):
    """Forward return minus SPY for signals from the research rule, grouped by their 0-4 score."""
    out = []
    for hz in HORIZONS:
        by: dict = {}
        for r in con.execute(
                """SELECT s.payload p, o.ret, o.spy_ret FROM outcomes o JOIN signals s ON s.id=o.signal_id
                   WHERE o.horizon=? AND o.spy_ret IS NOT NULL""", (hz,)).fetchall():
            p = json.loads(r["p"])
            if p.get("rule") == "research":
                by.setdefault(p["score"], []).append(r["ret"] - r["spy_ret"])
        for sc in sorted(by):
            out.append((sc, hz, len(by[sc]), statistics.mean(by[sc]), statistics.median(by[sc]),
                        sum(e > 0 for e in by[sc]) / len(by[sc])))
    return out


def track_text(con) -> str:
    lines = [f"{'Tier':4} {'Horizon':>7} {'N':>4} {'MeanExc':>8} {'MedExc':>8} {'Win%':>6}"]
    for tier, hz, n, mean, med, win in track_rows(con):
        lines.append(f"{tier:4} {hz:>5}d {n:>4} {mean:>+8.1%} {med:>+8.1%} {win:>6.0%}")
    rr = research_track_rows(con)
    if rr:
        lines += ["", "Research rule, by score (0-4):", f"{'Score':5} {'Horizon':>7} {'N':>4} {'MeanExc':>8} {'MedExc':>8} {'Win%':>6}"]
        lines += [f"{sc:<5} {hz:>5}d {n:>4} {mean:>+8.1%} {med:>+8.1%} {win:>6.0%}" for sc, hz, n, mean, med, win in rr]
    return "\n".join(lines)


def cmd_track(args, con):
    compute_outcomes(con)
    print(track_text(con))


def _safe(fn, p):
    try:
        return bool(fn(p))
    except Exception:
        return False


FACTORS = {
    "3+ insiders buying": lambda p: p["n_insiders"] >= 3,
    "buys within 2 days of each other": lambda p: p.get("tight_cluster"),
    "CFO or CEO is lead buyer": lambda p: p["lead_role"] in ("CFO", "CEO"),
    "first buy in 12 months (verified)": lambda p: p["points"].get("first_buy") == FIRST_PURCHASE_PTS,
    "holdings up 10%+ (lead buyer)": lambda p: p["points"].get("rel_size", 0) >= 6,
    "30%+ below 52-week high": lambda p: p["context"]["dist_52w_high"] <= -0.30,
}


def factor_rows(con, horizons=(21, 63)):
    """Which features go with better 21/63-day returns vs SPY? (needs forward returns computed)."""
    out = []
    for hz in horizons:
        data = con.execute(
            """SELECT s.payload p, o.ret - o.spy_ret ex FROM outcomes o JOIN signals s ON s.id=o.signal_id
               WHERE o.spy_ret IS NOT NULL AND o.horizon=?""", (hz,)).fetchall()
        parsed = [(json.loads(r["p"]), r["ex"]) for r in data]
        for name, fn in FACTORS.items():
            yes = [ex for p, ex in parsed if _safe(fn, p)]
            no = [ex for p, ex in parsed if not _safe(fn, p)]
            if yes or no:
                out.append((name, hz, len(yes), statistics.mean(yes) if yes else None,
                            len(no), statistics.mean(no) if no else None))
    return out


def factor_text(con) -> str:
    rows = factor_rows(con)
    if not rows:
        return "No finished forward returns yet (signals need to be at least 21 trading days old)."
    lines = [f"{'Factor':36} {'Hz':>4} {'With (N)':>14} {'Without (N)':>14}"]
    for name, hz, ny, my, nn, mn in rows:
        f = lambda m, n: "n/a" if m is None else f"{m:+.1%} ({n})"            # noqa: E731
        lines.append(f"{name:36} {hz:>3}d {f(my, ny):>14} {f(mn, nn):>14}")
    lines.append("Average return minus SPY. Treat any cell with N under about 30 as noise.")
    return "\n".join(lines)


def build_digest(con, days):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    results = [json.loads(r["payload"]) for r in con.execute(
        "SELECT payload FROM signals WHERE detected_at>=? ORDER BY score DESC", (since,)).fetchall()]
    n_all = con.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]
    title = f"Insider scanner report: {len(results)} signal(s) in the last {days} day(s)"
    text = "\n".join([title, "", format_alert(results, limit=60000) if results else "No new signals in this period.",
                      "", f"SCORECARD (all {n_all} logged signals; excess return vs SPY)", track_text(con),
                      "", "WHICH FACTORS ARE PAYING", factor_text(con)])
    e = _html.escape
    html_body = ((email_html(results, title) if results else f"<h2>{e(title)}</h2><p>No new signals in this period.</p>")
                 + f"<h3>Scorecard (all {n_all} logged signals; excess return vs SPY)</h3><pre>{e(track_text(con))}</pre>"
                 + f"<h3>Which factors are paying</h3><pre>{e(factor_text(con))}</pre>")
    return title, text, html_body


def cmd_digest(args, con):
    restore_signals(con, args.signals_log)
    try:
        compute_outcomes(con)
    except Exception as e:
        print(f"could not refresh forward returns: {e}", file=sys.stderr)
    title, text, html_body = build_digest(con, args.days)
    if args.print:
        print(text)
    try:
        ok = send_gmail(title, text, html_body)
    except Exception as e:
        print(f"email failed: {e}", file=sys.stderr)
        ok = False
    print("Digest emailed" if ok else "Digest not emailed (set GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_EMAIL)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=str(DEFAULT_HOME))
    ap.add_argument("--signals-log", default=os.environ.get("SIGNALS_LOG", ""),
                    help="JSONL file of every signal (committed to git so the DB can be rebuilt)")
    ap.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", ""))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--source", choices=("atom", "daily", "both"), default="both")
    s.add_argument("--daily-days", type=int, default=4, help="how many recent daily indexes to scan")
    s.add_argument("--no-alert", action="store_true")
    s.add_argument("--date")
    s.add_argument("--max-pages", type=int, default=10)
    s.add_argument("--lookback-days", type=int, default=3)
    s.add_argument("--min-score", type=float, default=CFG["alert_min_score"],
                   help="legacy rule only; the research rule alerts on every qualifying cluster")
    s.add_argument("--rule", choices=("research", "legacy"), default=os.environ.get("ALERT_RULE", "research"),
                   help="research = four officers/directors in 15 sessions with the 0-4 score (default); "
                        "legacy = the original tier A/B/C scorer")
    s.add_argument("--no-prices", action="store_true")
    s.add_argument("--fresh", action="store_true",
                   help="one-off: report ALL current signals, ignoring the already-alerted dedupe")
    b = sub.add_parser("backfill")
    b.add_argument("--quarters", type=int, default=14)
    sub.add_parser("track")
    d = sub.add_parser("digest")
    d.add_argument("--days", type=int, default=1)
    d.add_argument("--print", action="store_true", help="also print the report")
    sub.add_parser("notify-test")
    r = sub.add_parser("report")
    r.add_argument("--days", type=int, default=14)
    args = ap.parse_args(argv)
    con = connect(Path(args.home) / "insider.db")
    fn = {"scan": cmd_scan, "backfill": cmd_backfill, "track": cmd_track, "report": cmd_report,
          "digest": cmd_digest, "notify-test": cmd_notify_test}[args.cmd]
    try:
        if args.cmd == "track":
            restore_signals(con, args.signals_log)
        fn(args, con)
    except Exception:
        if args.cmd in ("scan", "track", "backfill", "digest") and should_alert_failure(con, args.cmd):
            notify(f"Insider scanner {args.cmd} FAILED", traceback.format_exc()[-1500:], "high")
        raise


if __name__ == "__main__":
    main()

