import unittest
from scanner_alerts import build_alert
EVENT={"accession":"0000000000-26-000001","filing_datetime":"2026-11-06T16:15:00","issuer_name":"Example Inc","ticker":"EXM","purchase_dollars":"100000"}
class TestAlerts(unittest.TestCase):
    def test_missing_price_does_not_block(self):
        a=build_alert(EVENT)
        self.assertIn("unavailable",a["message"])
        self.assertEqual(a["priority"],0)
    def test_stale_bar_is_labeled(self):
        a=build_alert(EVENT,{"date":"2026-11-03","close":"12.34","atr14":"0.5"})
        self.assertIn("2026-11-03",a["message"])
        self.assertIn("NOT a live quote",a["message"])
    def test_missing_price_date_rejected(self):
        with self.assertRaises(ValueError):
            build_alert(EVENT,{"close":12.34})
if __name__=="__main__":unittest.main()
