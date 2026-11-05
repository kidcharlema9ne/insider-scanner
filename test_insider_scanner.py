import datetime as dt
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import os

import insider_scanner as S

# Tests must never see real alert credentials (GitHub Actions injects them as env vars).
for _k in ("NTFY_TOPIC", "PUSHOVER_TOKEN", "PUSHOVER_USER", "GMAIL_USER", "GMAIL_APP_PASSWORD", "ALERT_EMAIL"):
    os.environ.pop(_k, None)


def form4(owner_cik="0001111111", owner="Jane Doe", title="Chief Financial Officer",
          director=0, officer=1, ten=0, rows=None, plan="0", footnote=None):
    rows = rows if rows is not None else [("P", "A", 10000, 5.00, "2026-11-03", 60000)]
    tx = ""
    for code, ad, sh, px, d, post in rows:
        fn = '<footnoteId id="F1"/>' if footnote else ""
        tx += f"""<nonDerivativeTransaction><securityTitle><value>Common</value></securityTitle>
        <transactionDate><value>{d}</value></transactionDate>
        <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>{sh}</value></transactionShares>
        <transactionPricePerShare><value>{px}</value>{fn}</transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts>
        <postTransactionAmounts><sharesOwnedFollowingTransaction><value>{post}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
        </nonDerivativeTransaction>"""
    fns = f'<footnotes><footnote id="F1">{footnote}</footnote></footnotes>' if footnote else ""
    return f"""<SEC-DOCUMENT>junk<XML><?xml version="1.0"?><ownershipDocument><documentType>4</documentType>
    <aff10b5One>{plan}</aff10b5One>
    <issuer><issuerCik>0000999999</issuerCik><issuerName>ACME Corp</issuerName><issuerTradingSymbol>acme</issuerTradingSymbol></issuer>
    <reportingOwner><reportingOwnerId><rptOwnerCik>{owner_cik}</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>{director}</isDirector><isOfficer>{officer}</isOfficer><isTenPercentOwner>{ten}</isTenPercentOwner>
    <officerTitle>{title}</officerTitle></reportingOwnerRelationship></reportingOwner>
    <nonDerivativeTable>{tx}</nonDerivativeTable>{fns}</ownershipDocument></XML></SEC-DOCUMENT>"""


def db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(S.SCHEMA)
    return con


def add(con, acc, owner, role, tx, filed=None, value=50000, post=None, plan=0, shares=10000, cik="999999"):
    con.execute("INSERT INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (acc, cik, "ACME", "ACME Corp", owner, owner, role, "", tx, filed or tx, filed or tx,
                 shares, value / shares, value, post, plan, "live"))


class ParseTests(unittest.TestCase):
    def test_only_open_market_purchases(self):
        rows = S.parse_form4(form4(rows=[("P", "A", 1000, 5, "2026-11-03", 5000),
                                         ("A", "A", 9999, 0, "2026-11-03", 9999),
                                         ("S", "D", 500, 6, "2026-11-03", 4500),
                                         ("M", "A", 100, 1, "2026-11-03", 100)]),
                             "0000000000-26-000001", "2026-11-04T10:00:00-05:00")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["ticker"], r["role"], r["shares"], r["value"]), ("ACME", "CFO", 1000, 5000))
        self.assertEqual(r["filed_date"], "2026-11-04")

    def test_multiple_lines_aggregate_vwap(self):
        rows = S.parse_form4(form4(rows=[("P", "A", 1000, 4, "2026-11-03", 1000),
                                         ("P", "A", 1000, 6, "2026-11-03", 2000)]), "a", "2026-11-04T00:00:00")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["price"], 5.0)
        self.assertEqual(rows[0]["shares"], 2000)

    def test_10b5_1_checkbox_and_footnote(self):
        self.assertEqual(S.parse_form4(form4(plan="1"), "a", "2026-11-04T00:00:00")[0]["plan10b5"], 1)
        r = S.parse_form4(form4(footnote="Purchase made pursuant to a Rule 10b5-1 trading plan"), "a", "2026-11-04T00:00:00")
        self.assertEqual(r[0]["plan10b5"], 1)
        r = S.parse_form4(form4(footnote="This purchase was not made under a 10b5-1 plan"), "a", "2026-11-04T00:00:00")
        self.assertEqual(r[0]["plan10b5"], 0)

    def test_roles(self):
        self.assertEqual(S.classify_role(0, 1, 0, "President and CEO"), "CEO")
        self.assertEqual(S.classify_role(0, 1, 0, "SVP, Chief Financial Officer"), "CFO")
        self.assertEqual(S.classify_role(1, 0, 0, ""), "DIRECTOR")
        self.assertEqual(S.classify_role(0, 0, 1, ""), "10%OWNER")

    def test_garbage_is_safe(self):
        self.assertEqual(S.parse_form4("not xml at all", "a", "2026-01-01T00:00:00"), [])
        self.assertEqual(S.parse_form4("<ownershipDocument><broken></ownershipDocument>", "a", "2026-01-01T00:00:00"), [])


class DiscoveryTests(unittest.TestCase):
    def test_atom(self):
        atom = """<feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>4 - ACME CORP (0000999999) (Issuer)</title>
        <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/999999/000111111126000123/0001111111-26-000123-index.htm"/>
        <updated>2026-11-05T09:30:00-05:00</updated></entry>
        <entry><title>4 - DOE JANE (0001111111) (Reporting)</title>
        <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1111111/000111111126000123/0001111111-26-000123-index.htm"/>
        <updated>2026-11-05T09:30:00-05:00</updated></entry>
        <entry><title>4/A - AMENDED (0000000001) (Issuer)</title>
        <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1/000000000126000009/0000000001-26-000009-index.htm"/>
        <updated>2026-11-05T09:31:00-05:00</updated></entry></feed>"""
        items = S.parse_atom(atom)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0][2].endswith("0001111111-26-000123.txt"))

    def test_daily_index(self):
        idx = ("Form Type   Company Name                  CIK     Date Filed  File Name\n" + "-" * 90 + "\n"
               "4           ACME CORP                     999999  20261105    edgar/data/999999/0001111111-26-000123.txt\n"
               "4           DOE JANE                      1111111 20261105    edgar/data/1111111/0001111111-26-000123.txt\n"
               "424B2       SOME BANK                     5       20261105    edgar/data/5/0000000005-26-000001.txt\n"
               "4/A         AMENDED                       7       20261105    edgar/data/7/0000000007-26-000002.txt\n")
        items = S.parse_daily_index(idx)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "2026-11-05")


class ScoreTests(unittest.TestCase):
    def test_cluster_beats_single(self):
        a = db()
        add(a, "1", "o1", "CFO", "2026-11-03")
        b = db()
        add(b, "1", "o1", "CFO", "2026-11-03")
        add(b, "2", "o2", "DIRECTOR", "2026-11-04")
        add(b, "3", "o3", "CEO", "2026-11-04")
        sa, sb = S.score_issuer(a, "999999"), S.score_issuer(b, "999999")
        self.assertGreater(sb["score"], sa["score"])
        self.assertEqual(sb["n_insiders"], 3)
        self.assertTrue(sb["tight_cluster"])

    def test_plan_and_small_excluded(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", plan=1)
        add(c, "2", "o2", "CEO", "2026-11-03", value=5000)
        self.assertIsNone(S.score_issuer(c, "999999"))

    def test_role_order(self):
        scores = {}
        for role in ("CFO", "CEO", "DIRECTOR", "10%OWNER"):
            c = db()
            add(c, "1", "o1", role, "2026-11-03")
            scores[role] = S.score_issuer(c, "999999")["score"]
        self.assertGreater(scores["CFO"], scores["CEO"])
        self.assertGreater(scores["CEO"], scores["DIRECTOR"])
        self.assertGreater(scores["DIRECTOR"], scores["10%OWNER"])

    def test_history_unverified_then_verified_first_buy(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03")
        r = S.score_issuer(c, "999999")
        self.assertIn("history_unverified(run backfill)", r["flags"])
        add(c, "0", "zz", "CEO", "2024-01-05", cik="1")   # other issuer gives >365d coverage
        r = S.score_issuer(c, "999999")
        self.assertEqual(r["points"]["first_buy"], S.FIRST_PURCHASE_PTS)

    def test_routine_detected(self):
        c = db()
        for y in (2023, 2024, 2025):
            add(c, f"h{y}", "o1", "DIRECTOR", f"{y}-11-10")
        add(c, "now", "o1", "DIRECTOR", "2026-11-04")
        r = S.score_issuer(c, "999999")
        self.assertIn("routine_unchecked", r["flags"])      # history starts 2023-11-10: not far enough back
        add(c, "old", "zz", "CEO", "2023-10-01", cik="1")    # now coverage reaches Nov 1, 2023
        r = S.score_issuer(c, "999999")
        self.assertIn("ROUTINE_PATTERN", r["flags"])
        self.assertEqual(r["points"]["routine"], S.ROUTINE_PENALTY)

    def test_not_routine_when_months_differ(self):
        c = db()
        for y, m in ((2023, "03"), (2024, "07"), (2025, "11")):
            add(c, f"h{y}", "o1", "DIRECTOR", f"{y}-{m}-10")
        add(c, "now", "o1", "DIRECTOR", "2026-11-04")
        self.assertNotIn("ROUTINE_PATTERN", S.score_issuer(c, "999999")["flags"])

    def test_holdings_increase_points(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", shares=10000, post=15000)  # +200%
        self.assertEqual(S.score_issuer(c, "999999")["points"]["rel_size"], 10)

    def test_price_filters_and_big_adv(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03")
        px = {"last": 10, "adv20": 500e6, "dist_hi": -0.3, "dist_lo": 0.2, "ret63": -0.1}
        self.assertEqual(S.score_issuer(c, "999999", px)["points"]["big_adv"], S.BIG_ADV_PENALTY)

    def test_late_filing_flag(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-10-20", filed="2026-11-04")
        self.assertTrue(any(f.startswith("LATE_FILING") for f in S.score_issuer(c, "999999")["flags"]))


class BulkAndOutcomeTests(unittest.TestCase):
    def test_bulk_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tAFF10B5ONE\n"
                        "0001-25-000001\t05-NOV-2025\t4\t0000999999\tACME\tACME\t0\n"
                        "0001-25-000002\t05-NOV-2025\t4\t0000999999\tACME\tACME\t1\n")
            z.writestr("REPORTINGOWNER.tsv", "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
                        "0001-25-000001\t0001111111\tJane Doe\tOfficer\tChief Financial Officer\n"
                        "0001-25-000002\t0002222222\tJohn\tDirector\t\n")
            z.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tSHRS_OWNED_FOLLOWING_TRANS\n"
                        "0001-25-000001\t03-NOV-2025\tP\t1000\t5\tA\t9000\n"
                        "0001-25-000002\t03-NOV-2025\tP\t1000\t5\tA\t9000\n"
                        "0001-25-000001\t03-NOV-2025\tS\t1000\t5\tD\t8000\n")
        buf.seek(0)
        c = db()
        self.assertEqual(S.load_bulk_zip(c, buf), 2)
        r = c.execute("SELECT role, plan10b5, tx_date FROM purchases ORDER BY accession").fetchall()
        self.assertEqual([(x["role"], x["plan10b5"], x["tx_date"]) for x in r],
                         [("CFO", 0, "2025-11-03"), ("DIRECTOR", 1, "2025-11-03")])

    def test_outcomes_with_stub_prices(self):
        c = db()
        c.execute("INSERT INTO signals(detected_at,issuer_cik,ticker,latest_accession,latest_filed_date,score,tier,payload)"
                  " VALUES ('x','1','ACME','a','2026-01-02',70,'A','{}')")
        start = dt.date(2026, 1, 1)

        def stub(tkr, s, e):
            out, price = [], 100.0 if tkr == "ACME" else 50.0
            for i in range(0, 30):
                d = start + dt.timedelta(days=i)
                if d.weekday() < 5:
                    mult = 1.01 ** i if tkr == "ACME" else 1.0
                    out.append((d, price * mult, 1e6))
            return out
        S.compute_outcomes(c, today=dt.date(2026, 2, 1), history=stub)
        rows = c.execute("SELECT horizon, ret, spy_ret FROM outcomes").fetchall()
        self.assertTrue(rows and all(r["ret"] > 0 and abs(r["spy_ret"]) < 1e-9 for r in rows))

    def test_end_to_end_ingest_and_scan(self):
        c = db()

        class FakeEdgar:
            def __init__(self, docs):
                self.docs = docs

            def get(self, url):
                class R:
                    pass
                r = R()
                r.text = self.docs.get(url)
                return r if r.text else None
        docs = {"u1": form4(owner_cik="1", rows=[("P", "A", 10000, 5, "2026-11-03", 12000)]),
                "u2": form4(owner_cik="2", owner="Bob", title="", director=1, officer=0,
                            rows=[("P", "A", 8000, 5, "2026-11-04", 8000)])}
        S.ingest(FakeEdgar(docs), c, [("0000000000-26-000001", "2026-11-04T09:00:00-05:00", "u1"),
                                      ("0000000000-26-000002", "2026-11-05T09:00:00-05:00", "u2")], verbose=False)
        res = S.run_scoring(c, 5, today=dt.date(2026, 11, 5), use_prices=False)
        self.assertEqual(res[0]["n_insiders"], 2)
        new = S.log_signals(c, res, 0)
        self.assertEqual(len(new), 1)
        self.assertEqual(len(S.log_signals(c, res, 0)), 0)   # no duplicate alerts


class IpoAndCollapseTests(unittest.TestCase):
    def test_ipo_footnote_excluded(self):
        raw = form4(footnote="Shares purchased in the Issuer's initial public offering at the IPO price of $15.00.")
        self.assertEqual(S.parse_form4(raw, "a", "2026-11-04T00:00:00"), [])
        raw = form4(footnote="Purchased from the underwriters in the offering.")
        self.assertEqual(S.parse_form4(raw, "a", "2026-11-04T00:00:00"), [])
        raw = form4(footnote="Open market purchase.")
        self.assertEqual(len(S.parse_form4(raw, "a", "2026-11-04T00:00:00")), 1)

    def test_same_lot_reported_by_two_joint_filers_counts_once(self):
        c = db()
        # ASPE pattern: fund + its director each report the identical 1,000,000 sh / $15M lot
        add(c, "1", "orbimed", "DIRECTOR", "2026-11-02", value=15_000_000, shares=1_000_000, post=1_000_000)
        add(c, "2", "thompson", "DIRECTOR", "2026-11-02", value=15_000_000, shares=1_000_000, post=1_000_000)
        r = S.score_issuer(c, "999999")
        self.assertEqual(r["n_insiders"], 1)
        self.assertEqual(r["total_value"], 15_000_000)

    def test_small_identical_lots_by_different_people_are_kept(self):
        c = db()
        add(c, "1", "o1", "DIRECTOR", "2026-11-03", value=50_000, shares=10_000, post=40_000)
        add(c, "2", "o2", "DIRECTOR", "2026-11-03", value=50_000, shares=10_000, post=90_000)
        self.assertEqual(S.score_issuer(c, "999999")["n_insiders"], 2)

    def test_fund_family_is_one_insider(self):
        c = db()
        for acc, name, v in (("1", "ARCH Venture Fund X, L.P.", 20_000_000), ("2", "ARCH Venture Partners XIV, L.P.", 18_000_000)):
            c.execute("INSERT INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (acc, "999999", "ACME", "ACME", "c" + acc, name, "10%OWNER", "", "2026-11-02", "2026-11-04",
                       "2026-11-04", v / 15, 15.0, v, None, 0, "live"))
        self.assertEqual(S.score_issuer(c, "999999")["n_insiders"], 1)
        self.assertEqual(S.family_key("Jane Doe", "123"), "123")

    def test_recent_ipo_skipped_in_scoring(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", filed="2026-11-04")
        orig = S.price_features
        try:
            S.price_features = lambda t, d=None: {"last": 15, "adv20": 9e7, "dist_hi": 0, "dist_lo": 0,
                                                  "ret63": None, "n_days": 3}
            self.assertEqual(S.run_scoring(c, 5, today=dt.date(2026, 11, 5)), [])
            S.price_features = lambda t, d=None: {"last": 15, "adv20": 9e7, "dist_hi": 0, "dist_lo": 0,
                                                  "ret63": None, "n_days": 200}
            self.assertEqual(len(S.run_scoring(c, 5, today=dt.date(2026, 11, 5))), 1)
        finally:
            S.price_features = orig


class TickerFilterTests(unittest.TestCase):
    def test_issuers_without_a_ticker_are_skipped(self):
        c = db()
        for i, tk in enumerate(("NONE", "N/A", "", "ACME")):
            c.execute("INSERT INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"a{i}", f"10{i}", tk, "X", "o", "o", "CFO", "", "2026-11-03", "2026-11-04", "2026-11-04",
                       10000, 5.0, 50000.0, None, 0, "live"))
        self.assertEqual(S.candidates(c, 5, dt.date(2026, 11, 5)), ["103"])


class GapFillTests(unittest.TestCase):
    SUB = {"filings": {"recent": {"form": ["4", "10-Q", "4", "4", "4/A"],
                                  "accessionNumber": ["0000000001-26-000010", "0000000001-26-000011",
                                                      "0000000001-26-000012", "0000000001-25-000001",
                                                      "0000000001-26-000013"],
                                  "filingDate": ["2026-08-01", "2026-08-02", "2026-09-03", "2024-01-01", "2026-09-04"]}}}

    def test_parse_submissions(self):
        out = S.parse_submissions(self.SUB, "2025-10-01")
        self.assertEqual(out, [("0000000001-26-000012", "2026-09-03"), ("0000000001-26-000010", "2026-08-01")])

    def _fake(self, docs, fail=False):
        sub = self.SUB

        class R:
            def __init__(s, text=None, js=None):
                s.text, s._js = text, js

            def json(s):
                return s._js

        class E:
            calls = []

            def get(self_, url, **kw):
                self_.calls.append(url)
                if fail:
                    raise RuntimeError("boom")
                if "submissions" in url:
                    return R(js=sub)
                return R(text=docs.get(url)) if docs.get(url) else None
        return E()

    def test_gapfill_pulls_missing_forms_once(self):
        c = db()
        url = S.ARCHIVE_TXT.format(cik=999999, nodash="000000000126000012", acc="0000000001-26-000012")
        e = self._fake({url: form4(rows=[("P", "A", 1000, 5, "2026-09-01", 5000)])})
        n = S.gapfill_issuer(e, c, "999999", dt.date(2026, 11, 5))
        self.assertEqual(n, 2)                      # two Form 4s missing, one parsed to a purchase
        self.assertEqual(c.execute("SELECT COUNT(*) c FROM purchases").fetchone()["c"], 1)
        calls = len(e.calls)
        self.assertEqual(S.gapfill_issuer(e, c, "999999", dt.date(2026, 11, 6)), 0)   # rechecked only after 30d
        self.assertEqual(len(e.calls), calls)

    def test_gapfill_failure_is_flagged_not_fatal(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", filed="2026-11-04")
        e = self._fake({}, fail=True)
        res = S.run_scoring(c, 5, today=dt.date(2026, 11, 5), use_prices=False, edgar=e)
        self.assertIn("HISTORY_GAP", res[0]["flags"])


class ScanPlumbingTests(unittest.TestCase):
    def test_daily_index_403_is_soft(self):
        class Resp:
            status_code = 403
        e = S.Edgar("Test Bot test@example.com")
        e.s.get = lambda url, timeout=0: Resp()
        self.assertIsNone(e.get("http://x", soft403=True))

    def test_notify_ntfy_and_no_channel(self):
        import os, unittest.mock as m
        with m.patch.dict(os.environ, {"NTFY_TOPIC": "t123", "ALERT_EMAIL": "", "PUSHOVER_TOKEN": "", "PUSHOVER_USER": "",
                                       "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}, clear=False), \
                m.patch("requests.post") as post:
            post.return_value.raise_for_status = lambda: None
            self.assertEqual(S.notify("Title", "body"), ["ntfy"])
            self.assertEqual(post.call_args[0][0], "https://ntfy.sh/t123")
        with m.patch.dict(os.environ, {"NTFY_TOPIC": "", "GMAIL_USER": "", "GMAIL_APP_PASSWORD": "",
                                       "PUSHOVER_TOKEN": "", "PUSHOVER_USER": ""}):
            self.assertEqual(S.notify("T", "b"), [])

    def test_notify_email_via_ntfy_header(self):
        import os, unittest.mock as m
        env = {"NTFY_TOPIC": "t9", "ALERT_EMAIL": "me@example.com", "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}
        with m.patch.dict(os.environ, env), m.patch("requests.post") as post:
            post.return_value.raise_for_status = lambda: None
            self.assertEqual(S.notify("T", "b"), ["ntfy+email"])
            self.assertEqual(post.call_args[1]["headers"]["X-Email"], "me@example.com")

    def test_notify_pushover(self):
        import os, unittest.mock as m
        env = {"NTFY_TOPIC": "", "PUSHOVER_TOKEN": "tok", "PUSHOVER_USER": "usr", "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}
        with m.patch.dict(os.environ, env), m.patch("requests.post") as post:
            post.return_value.raise_for_status = lambda: None
            self.assertEqual(S.notify("T", "b", "high"), ["pushover"])
            self.assertEqual(post.call_args[1]["data"]["priority"], 1)

    def test_notify_failure_never_raises(self):
        import os, unittest.mock as m
        with m.patch.dict(os.environ, {"NTFY_TOPIC": "t", "ALERT_EMAIL": "", "PUSHOVER_TOKEN": "", "PUSHOVER_USER": "",
                                       "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}), \
                m.patch("requests.post", side_effect=OSError("down")):
            self.assertEqual(S.notify("T", "b"), [])

    def test_signal_log_roundtrip(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", filed="2026-11-04")
        res = S.run_scoring(c, 5, today=dt.date(2026, 11, 5), use_prices=False)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data" / "signals.jsonl"
            S.append_signal_log(res, path)
            fresh = db()                                  # simulates a rebuilt database
            self.assertEqual(S.restore_signals(fresh, path), 1)
            self.assertEqual(S.restore_signals(fresh, path), 0)   # idempotent
            self.assertEqual(fresh.execute("SELECT ticker FROM signals").fetchone()["ticker"], "ACME")

    def test_format_alert(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-11-03", filed="2026-11-04")
        txt = S.format_alert(S.run_scoring(c, 5, today=dt.date(2026, 11, 5), use_prices=False))
        self.assertIn("ACME", txt)
        self.assertIn("CFO", txt)

    def test_scan_both_dedupes_and_handles_missing_days(self):
        c = db()
        atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>4 - ACME (0000999999) (Issuer)</title>
        <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/999999/000111111126000123/0001111111-26-000123-index.htm"/>
        <updated>2026-11-05T09:30:00-05:00</updated></entry></feed>"""
        idx = ("4           ACME CORP                     999999  20261105    edgar/data/999999/0001111111-26-000123.txt\n"
               "4           OTHER                         5       20261105    edgar/data/5/0000000005-26-000001.txt\n")

        class R:
            def __init__(s, t): s.text = t

        class E:
            def get(self, url, **kw):
                if "browse-edgar" in url and "start=0" in url:
                    return R(atom)
                if "daily-index" in url and "20261105" in url:
                    return R(idx)
                return None
        e = E()
        items = S.discover_atom(e, c) + S.discover_daily(e, c, dt.date(2026, 11, 5)) + S.discover_daily(e, c, dt.date(2026, 11, 1))
        accs = {i[0] for i in items}
        self.assertEqual(accs, {"0001111111-26-000123", "0000000005-26-000001"})


if __name__ == "__main__":
    unittest.main()
