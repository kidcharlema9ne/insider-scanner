"""Dump every trade of the Entry 8 pilot cohort (ChatGPT's recovered selector, run unchanged through cluster_selector).
Read-only. Usage: python dump_old_trades.py WORKDIR OUT.json"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cluster_selector import load_cohort, FLOOR

c = load_cohort(sys.argv[1], 'current.zip')
keep = ('entry', 'ticker', 'issuer_cik', 'adv', 'atr14', 'entry_open', 'stock_atr', 'spy_atr', 'excess_atr')
rows = [{**{k: t[k] for k in keep}, 'liquid': t['adv'] >= FLOOR} for t in c.all_trades]
assert len(rows) == 137 and sum(r['liquid'] for r in rows) == 91
json.dump(rows, open(sys.argv[2], 'w'))
print(f'dumped {len(rows)} trades ({sum(r["liquid"] for r in rows)} liquid) to {sys.argv[2]}')
