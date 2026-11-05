"""Tests for: buyer detail in alerts, 14-day cluster window, Gmail/Pushover content,
failure-alert throttling, and the digest report. Run: python test_new_features.py"""
import datetime as dt
import os
import tempfile
import unittest
import unittest.mock as m
from pathlib import Path

import insider_scanner as S
from test_insider_scanner import add, db

NO_CHANNELS = {"NTFY_TOPIC": "", "ALERT_EMAIL": "", "PUSHOVER_TOKEN": "", "PUSHOVER_USER": "",
               "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}


def cluster_db():
    c = db()
    add(c, "1", "Doe Jane", "CFO", "2026-11-03", filed="2026-11-05", value=50000, shares=10000, post=60000)
    c.execute("UPDATE purchases SET title='Chief Financial Officer' WHERE accession='1'")
    add(c, "2", "Roe Richard", "DIRECTOR", "2026-11-04", filed="2026-11-05", value=100000, shares=20000, post=120000)
    return c


class BuyerDetailTests(unittest.TestCase):
    def test_buyers_have_name_position_dollars_dates_holdings(self):
        r = S.score_issuer(cluster_db(), "999999")
        self.assertEqual(len(r["buyers"]), 2)
        jane = r["buyers"][0]
        self.assertEqual((jane["name"], jane["title"], jane["value"], jane["shares"]),
                         ("Doe Jane", "Chief Financial Officer", 50000, 10000))
        self.assertEqual((jane["first_tx"], jane["filed"], jane["holdings_after"]),
                         ("2026-11-03", "2026-11-05", 60000))
        self.assertEqual(r["buyers"][1]["title"], "Director")          # falls back to role when no title
        self.assertEqual(r["window_start"], "2026-11-03")

    def test_text_alert_lists_each_buyer_with_dates(self):
        t = S.format_alert([S.score_issuer(cluster_db(), "999999")])
        for s in ("Doe Jane", "Chief Financial Officer", "$50,000", "2026-11-03", "Roe Richard", "$100,000",
                  "holds 120,000 sh after", "Buys dated 2026-11-03 to 2026-11-04"):
            self.assertIn(s, t)

    def test_old_logged_signals_without_buyers_still_format(self):
        old = {"tier": "A", "score": 70, "ticker": "UPBD", "n_insiders": 6, "lead_role": "CFO",
               "lead_owner": "Khouri Halim", "total_value": 1290672, "latest_filed": "2026-11-04",
               "flags": [], "context": {"last": 24.14, "adv20_usd": 25424893, "dist_52w_high": 0.0, "ret_63d": 0.237},
               "issuer_cik": "933036", "latest_tx": "2026-11-03"}
        self.assertIn("UPBD", S.format_alert([old]))
        self.assertIn("UPBD", S.email_html([old], "x"))
        self.assertIn("UPBD", S.push_text([old]))

    def test_email_html_has_table_and_escapes(self):
        h = S.email_html([S.score_issuer(cluster_db(), "999999")], "Test <heading>")
        self.assertIn("<table", h)
        self.assertIn("Roe Richard", h)
        self.assertIn("&lt;heading&gt;", h)

    def test_push_text_fits_pushover_limit(self):
        r = S.score_issuer(cluster_db(), "999999")
        self.assertLessEqual(len(S.push_text([dict(r, ticker=f"T{i}") for i in range(8)])), 1000)
        self.assertIn("Doe Jane", S.push_text([r]))

    def test_multi_day_buyer_shows_range_and_latest_holdings(self):
        c = db()
        add(c, "1", "Doe Jane", "CFO", "2026-11-02", value=30000, shares=6000, post=12000)
        add(c, "2", "Doe Jane", "CFO", "2026-11-04", value=40000, shares=8000, post=20000)
        b = S.score_issuer(c, "999999")["buyers"][0]
        self.assertEqual((b["first_tx"], b["last_tx"], b["value"], b["holdings_after"]),
                         ("2026-11-02", "2026-11-04", 70000, 20000))
        self.assertIn("2026-11-02 to 2026-11-04", S.buyer_lines({"buyers": [b]})[0])

    def test_csv_has_buyer_column(self):
        r = S.score_issuer(cluster_db(), "999999")
        with tempfile.TemporaryDirectory() as d:
            txt = S.write_csv([r], Path(d)).read_text()
        self.assertIn("Doe Jane (Chief Financial Officer) $50,000 on 2026-11-03", txt)


class ClusterWindowTests(unittest.TestCase):
    def test_default_window_is_14_days(self):
        self.assertEqual(S.CFG["cluster_window_days"], 14)

    def test_buy_20_days_earlier_is_not_in_cluster(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-10-14")
        add(c, "2", "o2", "DIRECTOR", "2026-11-03")
        self.assertEqual(S.score_issuer(c, "999999")["n_insiders"], 1)

    def test_buy_10_days_earlier_is_in_cluster_but_not_tight(self):
        c = db()
        add(c, "1", "o1", "CFO", "2026-10-24")
        add(c, "2", "o2", "DIRECTOR", "2026-11-03")
        r = S.score_issuer(c, "999999")
        self.assertEqual(r["n_insiders"], 2)
        self.assertFalse(r["tight_cluster"])


class DeliveryTests(unittest.TestCase):
    def test_pushover_and_gmail_get_rich_content(self):
        r = S.score_issuer(cluster_db(), "999999")
        env = dict(NO_CHANNELS, PUSHOVER_TOKEN="tok", PUSHOVER_USER="usr")
        with m.patch.dict(os.environ, env), m.patch("requests.post") as post, \
                m.patch.object(S, "send_gmail", return_value=True) as mail:
            post.return_value.raise_for_status = lambda: None
            sent = S.alert_new([r])
        self.assertEqual(sent, ["pushover", "email"])
        self.assertIn("Doe Jane", post.call_args[1]["data"]["message"])
        self.assertLessEqual(len(post.call_args[1]["data"]["message"]), 1000)
        subject, body, html_body = mail.call_args[0]
        self.assertIn("Roe Richard", body)
        self.assertIn("<table", html_body)

    def test_gmail_message_is_multipart_html(self):
        env = dict(NO_CHANNELS, GMAIL_USER="me@gmail.com", GMAIL_APP_PASSWORD="pw", ALERT_EMAIL="me@gmail.com")
        with m.patch.dict(os.environ, env), m.patch("smtplib.SMTP_SSL") as smtp:
            self.assertTrue(S.send_gmail("Subj", "plain body", "<b>html</b>"))
        msg = smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "me@gmail.com")
        self.assertEqual({p.get_content_type() for p in msg.iter_parts()}, {"text/plain", "text/html"})

    def test_gmail_not_configured_returns_false(self):
        with m.patch.dict(os.environ, NO_CHANNELS):
            self.assertFalse(S.send_gmail("s", "b"))

    def test_failure_alert_is_throttled(self):
        c = db()
        t0 = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)
        self.assertTrue(S.should_alert_failure(c, "scan", now=t0))
        self.assertFalse(S.should_alert_failure(c, "scan", now=t0 + dt.timedelta(minutes=30)))
        self.assertTrue(S.should_alert_failure(c, "track", now=t0 + dt.timedelta(minutes=30)))   # separate key
        self.assertTrue(S.should_alert_failure(c, "scan", now=t0 + dt.timedelta(hours=7)))


class DigestAndFactorTests(unittest.TestCase):
    def logged(self):
        c = cluster_db()
        S.log_signals(c, S.run_scoring(c, 5, today=dt.date(2026, 11, 5), use_prices=False), 0)
        return c

    def test_digest_contains_buyers_and_scorecard(self):
        title, text, html_body = S.build_digest(self.logged(), 7)
        self.assertIn("1 signal(s)", title)
        for s in ("Doe Jane", "SCORECARD", "WHICH FACTORS ARE PAYING"):
            self.assertIn(s, text)
        self.assertIn("<table", html_body)

    def test_digest_with_no_signals(self):
        title, text, _ = S.build_digest(db(), 1)
        self.assertIn("0 signal(s)", title)
        self.assertIn("No new signals", text)

    def test_factor_table_with_outcomes(self):
        c = self.logged()
        sid = c.execute("SELECT id FROM signals").fetchone()["id"]
        c.execute("INSERT INTO outcomes VALUES (?,?,?,?)", (sid, 21, 0.10, 0.02))
        row = [r for r in S.factor_rows(c) if r[0] == "CFO or CEO is lead buyer" and r[1] == 21][0]
        self.assertEqual(row[2], 1)
        self.assertAlmostEqual(row[3], 0.08)
        self.assertIn("CFO or CEO is lead buyer", S.factor_text(c))

    def test_factor_text_when_empty(self):
        self.assertIn("No finished forward returns", S.factor_text(db()))

    def test_digest_command_emails(self):
        c = self.logged()

        class A:
            days, signals_log, print = 7, "", False
        with m.patch.object(S, "compute_outcomes"), m.patch.object(S, "send_gmail", return_value=True) as mail:
            S.cmd_digest(A, c)
        self.assertIn("Doe Jane", mail.call_args[0][1])



class ReportPageTests(unittest.TestCase):
    SAMPLE = [{"tier": "A", "score": 72, "ticker": "TST<b>", "issuer": "Test & Co", "issuer_cik": "1",
               "n_insiders": 1, "lead_role": "CFO", "lead_owner": "Doe", "total_value": 50000,
               "flags": ["X"], "context": {}, "window_start": "2026-11-03", "latest_tx": "2026-11-03",
               "latest_filed": "2026-11-05",
               "buyers": [{"name": "Doe <i>", "role": "CFO", "title": "CFO", "first_tx": "2026-11-03",
                           "last_tx": "2026-11-03", "filed": "2026-11-05", "shares": 10000, "avg_price": 5.0,
                           "value": 50000, "holdings_after": 60000}]}]

    def test_page_escapes_and_has_viewport(self):
        h = S.report_page(self.SAMPLE, "Heading <x>")
        self.assertIn("viewport", h)
        self.assertNotIn("<b>", h.split("<body>")[1].split("TST")[1][:6])
        self.assertIn("TST&lt;b&gt;", h)
        self.assertIn("Doe &lt;i&gt;", h)

    def test_publish_writes_files_and_returns_url(self):
        with tempfile.TemporaryDirectory() as d, m.patch.dict(
                os.environ, {"GITHUB_REPOSITORY": "Me/repo", "PUBLISH_PUSH": ""}, clear=False):
            url = S.publish_report(self.SAMPLE, "Title", docs_dir=d)
            self.assertTrue(url.startswith("https://me.github.io/repo/reports/"))
            self.assertTrue((Path(d) / "reports" / url.rsplit("/", 1)[1]).exists())
            self.assertIn("Title", (Path(d) / "index.html").read_text(encoding="utf-8"))

    def test_no_base_url_means_no_link(self):
        with tempfile.TemporaryDirectory() as d, m.patch.dict(
                os.environ, {"GITHUB_REPOSITORY": "", "REPORT_BASE_URL": ""}, clear=False):
            self.assertIsNone(S.publish_report(self.SAMPLE, "Title", docs_dir=d))

    def test_pushover_gets_link(self):
        sent = {}

        class R:
            def raise_for_status(self): pass
        def fake_post(url, **kw):
            sent.update(kw.get("data") or {})
            return R()
        with m.patch.dict(os.environ, {"PUSHOVER_TOKEN": "t", "PUSHOVER_USER": "u"}, clear=False), \
                m.patch("requests.post", fake_post):
            S.notify("T", "b", url="https://x/y.html")
        self.assertEqual(sent.get("url"), "https://x/y.html")


if __name__ == "__main__":
    unittest.main()
