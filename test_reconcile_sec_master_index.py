import unittest
from reconcile_sec_master_index import parse_master_idx, reconcile

def index(rows):
    return "Description: master\nCIK|Company Name|Form Type|Date Filed|Filename\n" + "\n".join(rows)

class ReconciliationTests(unittest.TestCase):
    def test_filter_and_count(self):
        text = index([
            "100|Alpha|4|2025-11-06|edgar/data/100/0000000100-25-000001.txt",
            "100|Alpha|4/A|2025-11-07|edgar/data/100/0000000100-25-000002.txt",
            "100|Alpha|3|2025-11-08|edgar/data/100/0000000100-25-000003.txt",
            "100|Alpha|4|2025-11-05|edgar/data/100/0000000100-25-000004.txt",
            "100|Alpha|4|2026-11-06|edgar/data/100/0000000100-26-000005.txt",
        ])
        sec, missing, archived, unmatched, months = reconcile({(2025,4): text}, {"0000000100-25-000001", "0000000100-25-000009"})
        self.assertEqual(len(sec), 2)
        self.assertEqual(missing, ["0000000100-25-000002"])
        self.assertEqual(archived, ["0000000100-25-000001"])
        self.assertEqual(unmatched, ["0000000100-25-000009"])
        self.assertEqual(months["2025-11"]["sec"], 2)
    def test_repeated_identical_accession_deduplicated(self):
        row = "100|Alpha|4|2026-02-01|edgar/data/100/0000000100-26-000001.txt"
        rows = parse_master_idx(index([row, row]))
        self.assertEqual(len(rows), 1)

    def test_same_accession_different_cik_paths(self):
        rows = parse_master_idx(index([
            '1003078|MSC INDUSTRIAL DIRECT|4|2025-11-20|edgar/data/1003078/0000950142-25-003039.txt',
            '1008015|JACOBSON MITCHELL|4|2025-11-20|edgar/data/1008015/0000950142-25-003039.txt',
        ]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows['0000950142-25-003039']['additional_index_rows']), 1)

    def test_duplicate_rejected(self):
        row = "100|Alpha|4|2026-02-01|edgar/data/100/0000000100-26-000001.txt"
        with self.assertRaises(ValueError):
            reconcile({(2026,1): index([row]), (2026,2): index([row])}, set())

if __name__ == "__main__":
    unittest.main()
