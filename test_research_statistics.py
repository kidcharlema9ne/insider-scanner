import unittest
from decimal import Decimal
from research_statistics import adjust_false_discovery_rate, chronological_samples, summarize

def item(oid,episode,return_atr,status="ok",role="CFO"):
    return {"opportunity_id":oid,"episode_id":episode,"role":role,
            "horizons":{"21":{"status":status,"next_open":{"end_return_atr":return_atr}}}}

class StatisticsTests(unittest.TestCase):
    def test_disclosure_and_episode_denominators(self):
        rows=[item("a","e1","2"),item("b","e1","-1"),item("c","e2","-3"),
              item("d","e3",None,"insufficient_forward_bars")]
        x=summarize(rows)[0]
        self.assertEqual(x["total_opportunities"],4)
        self.assertEqual(x["valid_opportunities"],3)
        self.assertEqual(x["distinct_valid_episodes"],2)
        self.assertEqual(x["winning_opportunities"],1)
        self.assertEqual(x["winning_episodes"],1)
        self.assertEqual(x["opportunity_win_rate"],str(__import__("decimal").Decimal(1)/3))
        self.assertEqual(x["episode_win_rate"],"0.5")
        self.assertEqual(x["excluded_opportunities"],1)
    def test_missing_outcomes_never_count_as_losses(self):
        x=summarize([item("a","a",None,"insufficient_forward_bars")])[0]
        self.assertEqual(x["valid_opportunities"],0)
        self.assertIsNone(x["opportunity_win_rate"])
    def test_duplicate_opportunity_rejected(self):
        with self.assertRaises(ValueError):
            summarize([item("a","a","1"),item("a","a","2")])
    def test_grouping(self):
        x=summarize([item("a","a","1",role="CFO"),item("b","b","-1",role="CEO")])
        self.assertEqual(len(x),2)
    def test_explicit_episode_memberships_and_unknown_are_distinct(self):
        rows = [dict(item("a", None, "2"), episode_ids=["e1", "e2"]),
                dict(item("b", None, "3"), episode_ids=[])]
        stats = summarize(rows)[0]
        self.assertEqual(stats["valid_opportunities"], 2)
        self.assertEqual(stats["distinct_valid_episodes"], 2)
        self.assertEqual(stats["winning_episodes"], 2)
        self.assertEqual(stats["valid_opportunities_without_episode"], 1)

    def test_chronological_split_purges_overlapping_outcome_paths(self):
        rows = [
            {"next_open_date": "2025-01-02", "horizons": {"21": {"status": "ok", "end_date": "2025-02-01"}}},
            {"next_open_date": "2025-12-15", "horizons": {"21": {"status": "ok", "end_date": "2026-01-15"}}},
            {"next_open_date": "2026-01-02"},
            {},
        ]
        result = chronological_samples(rows, "2026-01-01")
        self.assertEqual(result, dict(zip(("development", "purged", "validation", "undated"),
                                          ([row] for row in rows))))

    def test_false_discovery_rate_preserves_input_order(self):
        self.assertEqual(adjust_false_discovery_rate(["0.04", "0.01", "0.03"]),
                         [Decimal("0.04"), Decimal("0.03"), Decimal("0.04")])
        with self.assertRaises(ValueError):
            adjust_false_discovery_rate(["NaN"])

if __name__=="__main__":unittest.main()
