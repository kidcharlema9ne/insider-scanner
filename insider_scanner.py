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
    "min_value_usd": 25_000,      # ignore token buys
    "min_price": 2.0,             # no sub-$2 stocks
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
IPO_WEAK = re.compile(r"underwrit|follow-?on offering|secondary offering|private placement|"
                      r"registered direct|offering price", re.I)


def parse_form4(raw: str, accession: str, filed_at: str):
    """Return a list of aggregated open-market-purchase dicts from one filing."""
    xml = extract_xml(raw)
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    if _t(root, "documentType") not in (None, "4"):
        return []
    issuer = root.find("issuer")
    if issuer is None:
        return []
    issuer_cik = (_t(issuer, "issuerCik") or "").lstrip("0")
    ticker = (_t(issuer, "issuerTradingSymbol") or "").upper()
    issuer_name = _t(issuer, "issuerName") or ""

    # owners: use first as primary identity, OR the relationship flags (joint filers)
    owners = root.findall("reportingOwner")
    if not owners:
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
        if doc_is_ipo or IPO_WEAK.search(fn_text):
            continue                  # IPO / directed-share / placement purchase, not open-market
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
        ok, n = 1, len(items)
    except Exception as e:                      # never let a gap-fill failure kill the scan
        print(f"  gap-fill failed for CIK {issuer_cik}: {e}", file=sys.stderr)
        ok, n = 0, -1
    con.execute("INSERT OR REPLACE INTO gapfill VALUES (?,?,?,?)",
                (issuer_cik, today.isoformat(), ok, max(n, 0)))
    con.commit()
    return n


def ingest(edgar, con, items, verbose=True):
    n_new = 0
    for i, (acc, filed_at, url) in enumerate(items, 1):
        r = edgar.get(url)
        rows = parse_form4(r.text, acc, filed_at) if r is not None else []
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
           WHERE filed_date>=? AND plan10b5=0 AND value>=? AND price>=?
             AND UPPER(COALESCE(ticker,'')) NOT IN ('', 'NONE', 'N/A', 'NA')""",
        (since, CFG["min_value_usd"], CFG["min_price"]))]


def run_scoring(con, lookback_days, today=None, use_prices=True, edgar=None):
    today = today or dt.date.today()
    results = []
    for cik in candidates(con, lookback_days, today):
        gap_failed = bool(edgar) and gapfill_issuer(edgar, con, cik, today) < 0
        px = price_features(
            con.execute("SELECT ticker FROM purchases WHERE issuer_cik=? LIMIT 1", (cik,)).fetchone()["ticker"],
            today) if use_prices else None
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
        if px and px["last"] < CFG["min_price"]:
            continue
        results.append(res)
    return sorted(results, key=lambda r: -r["score"])


def log_signals(con, results, min_score):
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
        lines.append(f"{r['tier']}{r['score']:.0f} {r['ticker']} {r['n_insiders']} insider(s) ${r['total_value']:,}"
                     + (f" ADV${c['adv20_usd'] / 1e6:.1f}M" if c.get("adv20_usd") is not None else ""))
        for b in (r.get("buyers") or [])[:4]:
            lines.append(f" {b['name']} ({b['title']}) {_money(b['value'])} {_when(b)}")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def email_html(new, heading) -> str:
    e = _html.escape
    out = [f"<div style='font-family:Arial,sans-serif;font-size:14px'><h2>{e(heading)}</h2>"]
    for r in new:
        c = r.get("context") or {}
        link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r['issuer_cik']}&type=4"
        out.append(f"<h3 style='margin-bottom:2px'>{e(r['ticker'])} - {e(r.get('issuer', ''))} "
                   f"<span style='color:#555'>(Tier {r['tier']}, score {r['score']:.0f})</span></h3>")
        meta = [f"{r['n_insiders']} insider(s)", f"{_money(r['total_value'])} total",
                f"buys {r.get('window_start', '?')} to {r.get('latest_tx', '?')}",
                f"latest filing {r.get('latest_filed', '?')}"]
        if c.get("adv20_usd") is not None:
            meta += [f"ADV ${c['adv20_usd'] / 1e6:.1f}M", f"{_pct(c.get('dist_52w_high'))} vs 52-wk high",
                     f"63-day {_pct(c.get('ret_63d'))}"]
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
        if c.get("last") is not None:
            stats.insert(2, ("Price", f"${c['last']:.2f}"))
        out.append("<div class='card'><div class='head'>"
                   f"<span class='tk'>{e(str(r['ticker']))}</span>"
                   f"<span class='badge {badge}'>Tier {e(tier)} - score {r['score']:.0f}</span>"
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
           push_body: str | None = None, url: str | None = None) -> list:
    """Push via ntfy (NTFY_TOPIC), Pushover, and/or email via Gmail SMTP (GMAIL_USER + GMAIL_APP_PASSWORD).
    Never raises. Returns the channels that worked."""
    sent = []
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
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
    if po_tok and po_usr:
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
        if send_gmail(title, body, html_body):
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


def alert_new(new):
    """One alert for a batch of new signals: full detail by email, compact by push."""
    top = max(r["score"] for r in new)
    title = f"Insider buys: {len(new)} new signal(s), top {max(new, key=lambda r: r['score'])['ticker']} ({top:.0f})"
    url = publish_report(new, title)
    return notify(title, format_alert(new), "high" if top >= 60 else "default",
                  html_body=email_html(new, title), push_body=push_text(new), url=url)


def cmd_notify_test(args, con):
    sample = [{"tier": "A", "score": 72, "ticker": "TEST", "issuer": "Test Corp", "issuer_cik": "1",
               "n_insiders": 2, "lead_role": "CFO", "lead_owner": "Doe Jane", "total_value": 150000,
               "flags": [], "context": {}, "window_start": "2026-11-03", "latest_tx": "2026-11-04",
               "latest_filed": "2026-11-05",
               "buyers": [{"name": "Doe Jane", "role": "CFO", "title": "Chief Financial Officer",
                           "first_tx": "2026-11-03", "last_tx": "2026-11-03", "filed": "2026-11-05",
                           "value": 50000, "holdings_after_usd": 300000, "pct_increase": 0.2},
                          {"name": "Roe Richard", "role": "DIRECTOR", "title": "Director",
                           "first_tx": "2026-11-04", "last_tx": "2026-11-04", "filed": "2026-11-05",
                           "value": 100000, "holdings_after_usd": 600000, "pct_increase": 0.2}],
               "points": {"role": 20, "cluster": 14, "first_buy": 12}, "n_insiders": 2, "tight_cluster": False,
               "holdings_increase": 0.2}]
    url = publish_report(sample, "Insider scanner test (sample data)", name_hint="TEST")
    print("report link:", url or "none (no GITHUB_REPOSITORY / REPORT_BASE_URL)")
    sent = notify("Insider scanner test (sample data)", format_alert(sample), "default",
                  html_body=email_html(sample, "Insider scanner test (sample data)"), push_body=push_text(sample),
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
    items = [x for x in items if not (x[0] in seen or seen.add(x[0]))]
    print(f"{len(items)} new Form 4 filings to parse", file=sys.stderr)
    n = ingest(edgar, con, items)
    print(f"{n} open-market purchase rows stored", file=sys.stderr)
    results = run_scoring(con, args.lookback_days, use_prices=not args.no_prices, edgar=edgar)
    new = log_signals(con, results, args.min_score)
    if args.fresh:
        # One-off "first full run": report every current signal, even ones already alerted before.
        new = [r for r in results if r["score"] >= args.min_score]
        print(f"FRESH RUN: reporting all {len(new)} current signals (dedupe bypassed)", file=sys.stderr)
    print_results(new)
    if new:
        print(f"\nCSV: {write_csv(new, Path(args.home) / 'out')}")
        if not args.fresh:
            append_signal_log(new, args.signals_log)
        if not args.no_alert:
            alert_new(new)


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


def track_text(con) -> str:
    lines = [f"{'Tier':4} {'Horizon':>7} {'N':>4} {'MeanExc':>8} {'MedExc':>8} {'Win%':>6}"]
    for tier, hz, n, mean, med, win in track_rows(con):
        lines.append(f"{tier:4} {hz:>5}d {n:>4} {mean:>+8.1%} {med:>+8.1%} {win:>6.0%}")
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
    s.add_argument("--min-score", type=float, default=CFG["alert_min_score"])
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
