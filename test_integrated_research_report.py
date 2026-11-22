import unittest
from datetime import date,timedelta
from integrated_research_dataset import integrate
from research_html_report import render

def bars():
    start=date(2026,1,1)
    return [{"date":(start+timedelta(days=i)).isoformat(),"open":100,"high":103,"low":98,"close":101} for i in range(110)]

def disclosure(accession,ticker="ABC"):
    return {"accession":accession,"issuer_cik":"100","ticker_at_filing":ticker,
            "security_title":"Common Stock","filing_date":"2026-01-25",
            "owners":[{"cik":"12","title":"CFO"}],"aggregate_dollars":"5000",
            "insider_weighted_price":"50","review_flags":[]}

class IntegrationTests(unittest.TestCase):
    def test_join_preserves_unmatched_and_next_open(self):
        d=integrate([disclosure("a"),disclosure("b","UNKNOWN")],
                    {"stable-1":bars()}, {("100","ABC","Common Stock"):"stable-1"})
        self.assertEqual(d["counts"]["priced"],1)
        self.assertEqual(d["counts"]["unpriced"],1)
        self.assertEqual(d["opportunities"][0]["next_open_date"],"2026-01-26")
        self.assertEqual(d["opportunities"][0]["role"],"CFO")
        self.assertEqual(d["opportunities"][1]["outcome_status"],"unmatched_security")
        self.assertIn("Maximum appreciation (ATR)",render(d))
        self.assertIn("missing",render(d).lower())
    def test_duplicate_disclosure_is_rejected(self):
        with self.assertRaises(ValueError):
            integrate([disclosure("a"),disclosure("a")],{})
    def test_report_escapes_untrusted_ticker(self):
        d=integrate([disclosure("a","<script>alert(1)</script>")],{})
        page=render(d)
        self.assertNotIn("<script>",page)
        self.assertIn("&lt;script&gt;",page)
    def test_dated_mapping_excludes_expired_and_ambiguous_listings(self):
        expired = dict(issuer_cik="100", ticker="ABC", security_title="Common Stock",
                       start_date="2020-01-01", end_date="2025-12-31", security_id="expired")
        active = dict(expired, start_date="2026-01-01", end_date=None, security_id="active")
        reused = dict(active, issuer_cik="999", security_id="reused")
        result = integrate([disclosure("a")], {"active": bars()},
                           dated_mappings=[expired, active, reused])["opportunities"][0]
        self.assertEqual(result["security_id"], "active")
        self.assertEqual(result["outcome_status"], "ok")
        result = integrate([disclosure("a")], {"active": bars()},
                           dated_mappings=[active, dict(active, security_id="conflict")])["opportunities"][0]
        self.assertEqual(result["security_match"]["status"], "ambiguous")
        self.assertEqual(result["outcome_status"], "unmatched_security")

    def test_entry_features_do_not_read_entry_or_future_bars(self):
        sample = bars()
        sessions = [bar["date"] for bar in sample]
        record = dict(disclosure("a"), security_id="stable")
        original = integrate([record], {"stable": sample}, sessions=sessions)["opportunities"][0]
        for bar in sample[25:]:
            bar.update(open=200, high=210, low=190, close=205)
        updated = integrate([record], {"stable": sample}, sessions=sessions)["opportunities"][0]
        self.assertNotEqual(original["next_open"], updated["next_open"])
        self.assertEqual(original["entry_features"], updated["entry_features"])
        self.assertEqual(original["entry_features"]["completed_session_count"], 25)
        self.assertNotIn("63", original["entry_features"]["prior_returns"])

if __name__=="__main__":unittest.main()
