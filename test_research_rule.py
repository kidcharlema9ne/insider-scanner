"""Offline tests for the research-rule alert path (four officers/directors in 15 sessions + the 0-4 score).
Run: python -m unittest test_research_rule"""
import datetime as dt
import json
import unittest

import insider_scanner as S
from test_insider_scanner import add, db

D = dt.date


def four_buyers(c, filed="2026-11-10", tx=("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"),
                roles=("DIRECTOR", "DIRECTOR", "OFFICER", "DIRECTOR")):
    for i, (t, role) in enumerate(zip(tx, roles), 1):
        c.execute("INSERT INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (f"A{i}", "999999", "ACME", "ACME Corp", f"10{i}", f"Person{i} X", role, "", t, filed, filed,
                   1000.0 + i * 37, 40.0 + i * 0.5, (1000.0 + i * 37) * (40.0 + i * 0.5), 9000.0, 0, "live"))


def bars(n=300, start_price=100.0, end_price=100.0, vol=1_000_000, end=D(2026, 11, 9), spread=1.0):
    """n daily bars ending on `end` (weekdays only), straight line from start_price to end_price."""
    days, d = [], end
    while len(days) < n:
        if D.weekday(d) < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    days.reverse()
    out = []
    for i, day in enumerate(days):
        c = start_price + (end_price - start_price) * i / (n - 1)
        out.append((day, c, c + spread / 2, c - spread / 2, c, float(vol)))
    return out


class CalendarTests(unittest.TestCase):
    def test_entry_is_next_open_after_filing(self):
        et = S._et()
        # Tuesday 10 Nov 2026 filed at 5:01 pm -> Wednesday open; filed 8:00 am -> same day open
        self.assertEqual(S.entry_session(dt.datetime(2026, 11, 10, 17, 1, tzinfo=et)), D(2026, 11, 11))
        self.assertEqual(S.entry_session(dt.datetime(2026, 11, 10, 8, 0, tzinfo=et)), D(2026, 11, 10))
        self.assertEqual(S.entry_session(dt.datetime(2026, 11, 10, 9, 45, tzinfo=et)), D(2026, 11, 11))
        # Friday after the close -> Monday; Wednesday before Thanksgiving -> Friday
        self.assertEqual(S.entry_session(dt.datetime(2026, 11, 13, 16, 30, tzinfo=et)), D(2026, 11, 16))
        self.assertEqual(S.entry_session(dt.datetime(2026, 11, 25, 16, 30, tzinfo=et)), D(2026, 11, 27))

    def test_fifteen_sessions_back(self):
        w = S.sessions_before(D(2026, 11, 11), 15)
        self.assertEqual(len(w), 15)
        self.assertEqual(w[-1], D(2026, 11, 10))
        self.assertEqual(w[0], D(2026, 10, 21))       # 15 weekdays, no holiday in that stretch

    def test_date_only_filing_counts_as_end_of_day(self):
        class R(dict):
            pass
        r = R(filed_at="2026-11-10", filed_date="2026-11-10")
        self.assertEqual(S.entry_session(S.filed_datetime(r)), D(2026, 11, 11))


class ClusterRuleTests(unittest.TestCase):
    def test_four_officers_directors_fire_and_entry_is_next_open(self):
        c = db()
        four_buyers(c)
        ev, why = S.research_event(c, "999999", D(2026, 11, 10))
        self.assertIsNone(why)
        self.assertEqual(len(ev["owners"]), 4)
        self.assertEqual(ev["entry"], D(2026, 11, 11))      # date-only filing 10 Nov -> next open 11 Nov
        self.assertEqual(ev["window_start"], "2026-10-21")

    def test_three_is_not_enough(self):
        c = db()
        four_buyers(c)
        c.execute("DELETE FROM purchases WHERE accession='A4'")
        ev, why = S.research_event(c, "999999", D(2026, 11, 10))
        self.assertIsNone(ev)

    def test_ten_percent_owner_does_not_count(self):
        c = db()
        four_buyers(c, roles=("DIRECTOR", "DIRECTOR", "OFFICER", "10%OWNER"))
        self.assertIsNone(S.research_event(c, "999999", D(2026, 11, 10))[0])

    def test_old_purchase_filed_late_does_not_count(self):
        c = db()
        four_buyers(c, tx=("2026-09-01", "2026-11-03", "2026-11-04", "2026-11-05"))   # first buy far outside 15 sessions
        self.assertIsNone(S.research_event(c, "999999", D(2026, 11, 10))[0])

    def test_plan_buys_excluded(self):
        c = db()
        four_buyers(c)
        c.execute("UPDATE purchases SET plan10b5=1 WHERE accession='A2'")
        self.assertIsNone(S.research_event(c, "999999", D(2026, 11, 10))[0])

    def test_fund_entities_do_not_count(self):
        c = db()
        four_buyers(c)
        c.execute("UPDATE purchases SET owner_name='Acme Capital Partners LP' WHERE accession='A2'")
        self.assertIsNone(S.research_event(c, "999999", D(2026, 11, 10))[0])

    def test_filing_that_makes_four_is_the_event(self):
        """Three buyers filed earlier; the fourth filing (later) is the completing filing and sets the entry."""
        c = db()
        four_buyers(c)
        c.execute("UPDATE purchases SET filed_date='2026-11-06', filed_at='2026-11-06' WHERE accession IN ('A1','A2','A3')")
        c.execute("UPDATE purchases SET filed_date='2026-11-10', filed_at='2026-11-10T11:00:00-05:00' WHERE accession='A4'")
        ev, _ = S.research_event(c, "999999", D(2026, 11, 10))
        self.assertEqual(ev["accession"], "A4")
        self.assertEqual(ev["entry"], D(2026, 11, 11))
        self.assertEqual(ev["completed_at"].date(), D(2026, 11, 10))

    def test_same_date_same_price_trio_is_routine_and_left_out(self):
        c = db()
        four_buyers(c)
        for acc in ("A1", "A2", "A3"):
            c.execute("UPDATE purchases SET tx_date='2026-11-03', price=40.0, value=shares*40.0 WHERE accession=?", (acc,))
        # three plan-like buyers are dropped; only one buyer remains -> no event
        self.assertIsNone(S.research_event(c, "999999", D(2026, 11, 10))[0])

    def test_issuer_that_does_this_every_month_is_routine(self):
        c = db()
        four_buyers(c)
        for month, base in (("2026-09", 20), ("2026-10", 10)):
            for i in range(3):
                c.execute("INSERT INTO purchases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (f"H{month}{i}", "999999", "ACME", "ACME Corp", f"9{i}", f"Hist {i}", "DIRECTOR", "",
                           f"{month}-05", f"{month}-06", f"{month}-06", 100.0, 30.0, 3000.0, 1000.0, 0, "bulk"))
        ev, why = S.research_event(c, "999999", D(2026, 11, 10))
        self.assertIsNone(ev)
        self.assertIn("routine", why)

    def test_repeat_event_blocked_until_hold_ends(self):
        c = db()
        prior = {"rule": "research", "entry_date": "2026-10-20"}
        c.execute("INSERT INTO signals(detected_at,issuer_cik,ticker,latest_accession,latest_filed_date,score,tier,payload)"
                  " VALUES ('x','999999','ACME','OLD','2026-10-19',2,'R',?)", (json.dumps(prior),))
        self.assertTrue(S.in_prior_hold(c, "999999", D(2026, 11, 11), "NEW"))     # 16 sessions later: still holding
        self.assertFalse(S.in_prior_hold(c, "999999", D(2026, 11, 25), "NEW"))    # 24 sessions later: hold over
        self.assertFalse(S.in_prior_hold(c, "999999", D(2026, 11, 11), "OLD"))    # the same event is not its own repeat


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.c = db()
        four_buyers(self.c)
        self.ev, _ = S.research_event(self.c, "999999", D(2026, 11, 10))

    def feats(self, stock, spy, oneq):
        return S.research_features(stock, spy, oneq, self.ev["entry"])

    def test_all_four_points(self):
        # stock falls from 400 to 100 over ~300 sessions with a tight 1-point range: big ATR fall, >50% drawdown
        stock = bars(start_price=400, end_price=100, spread=1.0)
        spy = bars(start_price=100, end_price=120)
        oneq = bars(start_price=100, end_price=105)       # Nasdaq lags SPY by far more than 1.95 points
        f = self.feats(stock, spy, oneq)
        self.assertLess(f["fall_atr"], -15)
        self.assertGreater(f["drawdown"], 0.5)
        self.assertLess(f["lead63"], -0.0195)
        pts, score, checked = S.score_research(self.ev, f)
        self.assertEqual((score, checked), (4, 4))
        self.assertEqual(pts, {"no_ceo_cfo": 1, "nasdaq_lag": 1, "deep_fall": 1, "drawdown": 1})

    def test_ceo_removes_the_no_ceo_cfo_point(self):
        c = db()
        four_buyers(c, roles=("DIRECTOR", "CEO", "OFFICER", "DIRECTOR"))
        ev, _ = S.research_event(c, "999999", D(2026, 11, 10))
        pts, _, _ = S.score_research(ev, {"lead63": 0.0, "fall_atr": 0.0, "drawdown": 0.0})
        self.assertEqual(pts["no_ceo_cfo"], 0)

    def test_flat_stock_scores_only_the_no_ceo_cfo_point(self):
        stock, spy, oneq = bars(), bars(), bars()
        pts, score, checked = S.score_research(self.ev, self.feats(stock, spy, oneq))
        self.assertEqual((score, checked), (1, 4))
        self.assertEqual(pts["nasdaq_lag"], 0)

    def test_fall_boundary_is_in_atr_units_not_percent(self):
        # a 30% fall in a quiet stock is far more than 15 ATR; the same fall in a wild stock is not
        quiet = self.feats(bars(start_price=100, end_price=70, spread=0.5), bars(), bars())
        wild = self.feats(bars(start_price=100, end_price=70, spread=12.0), bars(), bars())
        self.assertLess(quiet["fall_atr"], -15)
        self.assertGreater(wild["fall_atr"], -15)
        self.assertLess(quiet["drawdown"], 0.5)           # 30% down is not a 50% drawdown

    def test_missing_price_data_is_not_scored_and_says_so(self):
        pts, score, checked = S.score_research(self.ev, S.research_features([], [], [], self.ev["entry"]))
        self.assertEqual(pts["deep_fall"], None)
        self.assertEqual((score, checked), (1, 1))
        r = S.build_research_result(self.ev, None, "ACME", "ACME Corp", "999999", ["prices_not_checked"])
        self.assertIn("3 could not be checked", S.research_headline(r))

    def test_short_history_cannot_judge_twelve_month_factors(self):
        f = self.feats(bars(n=120), bars(), bars())
        self.assertIsNone(f["fall_atr"])
        self.assertIsNone(f["drawdown"])
        self.assertIsNotNone(f["adv15"])

    def test_features_use_only_sessions_before_entry(self):
        stock = bars(end=D(2026, 11, 9))
        extra = stock + [(D(2026, 11, 11), 1.0, 1.0, 1.0, 1.0, 1e9)]      # entry-day bar must be ignored
        self.assertEqual(self.feats(extra, bars(), bars())["last"], stock[-1][4])


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.c = db()
        four_buyers(self.c)

    def fake_bars(self, ticker, start, end):
        if ticker == "SPY":
            return bars(start_price=100, end_price=120)
        if ticker == "ONEQ":
            return bars(start_price=100, end_price=105)
        return bars(start_price=400, end_price=100, spread=1.0, vol=500_000)      # $50M a day, fell hard

    def test_scan_produces_scored_result_and_push_text(self):
        res = S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=self.fake_bars)
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual((r["score"], r["rule"], r["n_insiders"]), (4, "research", 4))
        text = S.push_text(res)
        self.assertLessEqual(len(text), 1000)
        self.assertIn("score 4 of 4".lower(), text.lower())
        self.assertIn("Entry Wed Nov 11 open", text)
        for letter_code in ("R1", "D1", "N)", "T20"):
            self.assertNotIn(letter_code, text)                     # plain words only, no shorthand labels
        self.assertIn("Down 50%+ from 12-month high", text)

    def test_thin_stock_is_dropped_by_the_dollar_volume_floor(self):
        thin = lambda t, s, e: bars(vol=1_000) if t not in ("SPY", "ONEQ") else bars()   # noqa: E731
        self.assertEqual(S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=thin), [])

    def test_unverifiable_liquidity_still_alerts_with_a_flag(self):
        none = lambda t, s, e: []                                    # noqa: E731
        res = S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=none)
        self.assertEqual(len(res), 1)
        self.assertIn("liquidity_unverified", res[0]["flags"])
        self.assertEqual(res[0]["checked"], 1)

    def test_old_event_outside_lookback_is_not_new(self):
        self.assertEqual(S.run_research(self.c, 3, today=D(2026, 11, 20), bars_fn=self.fake_bars), [])

    def test_logged_once_then_deduped_and_priority_follows_score(self):
        res = S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=self.fake_bars)
        self.assertEqual(len(S.log_signals(self.c, res, -1)), 1)
        self.assertEqual(len(S.log_signals(self.c, res, -1)), 0)          # same filing: no second alert
        sent = {}
        import unittest.mock as m
        with m.patch.object(S, "publish_report", return_value=None), \
                m.patch.object(S, "notify", side_effect=lambda t, b, p, **k: sent.update(t=t, p=p, push=k["push_body"]) or ["pushover"]):
            S.alert_new(res)
            self.assertEqual(sent["p"], "high")
            self.assertEqual(sent["t"], "Insider cluster ACME: score 4 of 4")
            low = [dict(res[0], score=1)]
            S.alert_new(low)
            self.assertEqual(sent["p"], "default")

    def test_report_page_and_email_render_for_research_results(self):
        res = S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=self.fake_bars)
        page = S.report_page(res, "t")
        self.assertIn("Score 4 of 4", page)
        self.assertIn("About this rule", page)
        self.assertIn("Entry 93", page)
        self.assertIn("Score 4 of 4", S.email_html(res, "t"))
        self.assertIn("Stock down 15+ ATR", S.format_alert(res))
        S.write_csv(res, __import__("pathlib").Path(__import__("tempfile").mkdtemp()))

    def test_research_signal_survives_the_log_and_restore_round_trip(self):
        import tempfile
        res = S.run_research(self.c, 3, today=D(2026, 11, 10), bars_fn=self.fake_bars)
        S.log_signals(self.c, res, -1)
        path = tempfile.mkstemp()[1]
        S.append_signal_log(res, path)
        fresh = db()
        self.assertEqual(S.restore_signals(fresh, path), 1)
        self.assertEqual(json.loads(fresh.execute("SELECT payload FROM signals").fetchone()["payload"])["rule"], "research")

    def test_notify_test_command_runs(self):
        import argparse
        S.cmd_notify_test(argparse.Namespace(), self.c)


class ParserTests(unittest.TestCase):
    def test_automatic_plan_purchase_is_not_discretionary(self):
        from test_insider_scanner import form4
        raw = form4(footnote="Purchased through the issuer's automatic dividend reinvestment plan")
        self.assertEqual(S.parse_form4(raw, "0001-26-000001", "2026-11-05T10:00:00-05:00"), [])


if __name__ == "__main__":
    unittest.main()
