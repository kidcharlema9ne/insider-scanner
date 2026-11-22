import unittest
from datetime import date,timedelta
from decimal import Decimal
from price_outcomes import atr14,compare_disclosure
class TestOutcomes(unittest.TestCase):
    def test_both_baselines_and_horizons(self):
        bars=[]
        start=date(2026,1,1)
        for i in range(100):
            day=start+timedelta(days=i)
            bars.append({"date":day.isoformat(),"open":50+i//10,"high":53+i//10,"low":48+i//10,"close":51+i//10})
        result=compare_disclosure(bars,bars[20]["date"])
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["next_open_date"],bars[21]["date"])
        self.assertEqual(result["horizons"]["64"]["status"],"ok")
        self.assertNotEqual(result["horizons"]["11"]["next_open"]["end_return_percent"],result["horizons"]["11"]["filing_close_reference"]["end_return_percent"])
    def test_d051_ignores_transaction_date_and_uses_next_session(self):
        # Friday filing, Monday next bar; no acceptance timestamp required.
        start=date(2026,1,1)
        bars=[]
        for i in range(125):
            day=start+timedelta(days=i)
            if day.weekday()<5:
                bars.append({"date":day.isoformat(),"open":100,"high":102,"low":98,"close":101})
        filing=next(b["date"] for b in bars if date.fromisoformat(b["date"]).weekday()==4 and b["date"]>"2026-02-01")
        result=compare_disclosure(bars,filing)
        self.assertEqual(result["status"],"ok")
        self.assertEqual(date.fromisoformat(result["next_open_date"]).weekday(),0)
        self.assertGreater(result["next_open_date"],filing)

    def test_insufficient_history(self):
        bars=[{"date":f"2026-01-{i:02}","open":1,"high":2,"low":0.5,"close":1} for i in range(1,8)]
        self.assertEqual(compare_disclosure(bars,"2026-01-03")["status"],"missing_or_invalid_entry_atr")
    def test_calendar_prevents_entry_shift_and_flags_forward_gaps(self):
        start = date(2026, 1, 1)
        days = [(start + timedelta(days=i)).isoformat() for i in range(230)]
        bars = [{"date": day, "open": 100, "high": 103, "low": 99, "close": 101} for day in days]
        filing = days[19]
        self.assertEqual(compare_disclosure(bars[:20] + bars[21:], filing, sessions=days)["status"],
                         "missing_entry_session")
        result = compare_disclosure(bars[:35] + bars[36:], filing, sessions=days)
        self.assertEqual(result["horizons"]["11"]["status"], "ok")
        self.assertEqual(result["horizons"]["21"]["status"], "missing_forward_session")
        self.assertEqual(result["horizons"]["6m"]["status"], "missing_forward_session")
        result = compare_disclosure(bars, filing, sessions=days)
        self.assertEqual(result["horizons"]["6m"]["end_date"], "2026-07-21")
        self.assertEqual(Decimal(result["atr14"]), Decimal(4))
        self.assertEqual(Decimal(result["horizons"]["6m"]["next_open"]["end_return_atr"]), Decimal("0.25"))

    def test_non_session_filing_date_has_no_close_reference(self):
        start = date(2026, 1, 1)
        days = [(start + timedelta(days=i)).isoformat() for i in range(40) if i != 19]
        bars = [{"date": day, "open": 100, "high": 103, "low": 99, "close": 101} for day in days]
        result = compare_disclosure(bars, "2026-01-20", sessions=days)
        self.assertEqual(result["next_open_date"], "2026-01-21")
        self.assertNotIn("filing_close_reference", result["horizons"]["11"])

if __name__=="__main__":unittest.main()
