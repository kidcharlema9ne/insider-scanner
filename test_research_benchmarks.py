import unittest
from decimal import Decimal

from research_benchmarks import benchmark_outcomes, select_market_benchmark


class BenchmarksTest(unittest.TestCase):
    def test_market_mapping_requires_verified_nasdaq_membership(self):
        self.assertEqual(select_market_benchmark({"exchange": "XNAS", "sp500_member": True}), "SPY")
        self.assertEqual(select_market_benchmark({"exchange": "XNAS", "sp500_member": False}), "ONEQ")
        self.assertIsNone(select_market_benchmark({"exchange": "XNAS"}))
        self.assertEqual(select_market_benchmark({"exchange": "XASE"}), "IWM")

    def test_exact_date_and_percentage_excess(self):
        stock = {"next_open_date": "2026-03-02", "horizons": {
            "11": {"status": "ok", "end_date": "2026-03-16", "next_open": {"end_return_percent": "10"}},
            "21": {"status": "ok", "end_date": "2026-03-30", "next_open": {"end_return_percent": "12"}},
        }}
        prices = {"SPY": {"2026-03-02": {"open": 100}, "2026-03-16": {"close": 104}}}
        result = benchmark_outcomes(stock, {"exchange": "XNYS"}, prices)
        eleven = result["market"]["horizons"]["11"]
        self.assertEqual(Decimal(eleven["benchmark_return_percent"]), Decimal(4))
        self.assertEqual(Decimal(eleven["stock_excess_percentage_points"]), Decimal(6))
        self.assertEqual(result["market"]["horizons"]["21"]["status"], "missing_or_invalid_benchmark_end")
        self.assertEqual(result["sector"]["status"], "missing_point_in_time_classification")
