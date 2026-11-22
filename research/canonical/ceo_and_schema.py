"""Step 2D: (a) is a CEO among the four buyers? (b) dump the filing schema so the ownership-size analysis can be
written against real field names. Imports the canonical selector (ChatGPT's code unchanged). Read-only."""
import datetime, re, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from cluster_selector import load_cohort

SEED, B = 20261107, 10000
c = load_cohort(sys.argv[1], 'current.zip'); lt = c.lt
CFO_RE = re.compile(r'\b(?:CFO|chief financial officer)\b', re.I)          # same pattern as wider.py
CEO_RE = re.compile(r'\b(?:CEO|chief executive officer)\b', re.I)          # new
where = {id(row): (key, i, n, cfo) for (key, i), (row, cfo, n) in lt.short.items()}
cal = lt.calendar

def buyers_for(row):
    key, i, n, cfo = where[id(row)]
    start, entry = cal[max(0, i-15)], cal[i]
    return [r for j, rs in lt.by_security[key].items() if j <= i for r in rs
            if any(start <= d < entry for d in r['transaction_dates'])]

# self-check: rebuilt buyer sets must reproduce the selector's own buyer count and CFO flag for all 137
bad = 0
for t in c.all_trades:
    key, i, n, cfo = where[id(t['row'])]
    bs = buyers_for(t['row'])
    ncount = len({r['owners'][0]['cik'] for r in bs})
    cfo2 = any('Officer' in r['owners'][0]['relationship'].split(',') and CFO_RE.search(r['owners'][0]['title'] or '') for r in bs)
    bad += (ncount != n) or (cfo2 != cfo)
print(f"SELF-CHECK rebuilt buyer sets match selector on {len(c.all_trades)-bad} of {len(c.all_trades)} trades (expect all)")
assert bad == 0

for t in c.liquid:
    bs = buyers_for(t['row'])
    t['ceo'] = any('Officer' in r['owners'][0]['relationship'].split(',') and CEO_RE.search(r['owners'][0]['title'] or '') for r in bs)
    t['n_buyers'] = len({r['owners'][0]['cik'] for r in bs})
    t['n_titleless'] = sum(1 for cik in {r['owners'][0]['cik'] for r in bs}
                           if not [r for r in bs if r['owners'][0]['cik'] == cik][0]['owners'][0]['title'])
L = c.liquid
y = np.array([t['excess_atr'] for t in L]); st = np.array([t['stock_atr'] for t in L]); sp = np.array([t['spy_atr'] for t in L])
wk = np.array([int(f"{datetime.date.fromisoformat(t['entry']).isocalendar()[0]}{datetime.date.fromisoformat(t['entry']).isocalendar()[1]:02d}") for t in L])
weeks = sorted(set(wk)); by_week = {w: np.where(wk == w)[0] for w in weeks}
ceo = np.array([t['ceo'] for t in L]); cfo = np.array([t['cfo'] for t in L])
print(f"COHORT n={len(L)} | CEO among buyers: {ceo.sum()} | CFO among buyers: {cfo.sum()} | both: {(ceo&cfo).sum()} | neither: {(~ceo&~cfo).sum()}")
print(f"buyers with no title on file (could be a CEO we cannot see): mean per trade {np.mean([t['n_titleless'] for t in L]):.2f}; trades with >=1 untitled buyer: {sum(t['n_titleless']>0 for t in L)}")

def row(name, m):
    k = int(m.sum())
    if k == 0: print(f"{name:<34}n=0"); return
    print(f"{name:<34}n={k:>3} dates={len({L[i]['entry'] for i in np.where(m)[0]}):>3} weeks={len(set(wk[m])):>2} stock={st[m].mean():+.3f} SPY={sp[m].mean():+.3f} "
          f"excess={y[m].mean():+.3f} median={np.median(y[m]):+.3f} capped5={np.clip(y[m],-5,5).mean():+.3f} beat_SPY={int((y[m]>0).sum())}")

def diff(name, a, b):
    rng = np.random.default_rng(SEED); out = []
    for _ in range(B):
        pick = rng.choice(len(weeks), len(weeks), replace=True)
        idx = np.concatenate([by_week[weeks[p]] for p in pick])
        ia, ib = idx[a[idx]], idx[~a[idx]] if False else idx[b[idx]]
        if len(ia) < 3 or len(ib) < 3: continue
        out.append((y[ia].mean()-y[ib].mean(), np.median(y[ia])-np.median(y[ib]),
                    np.clip(y[ia],-5,5).mean()-np.clip(y[ib],-5,5).mean()))
    o = np.array(out)
    for j, lab in enumerate(('mean', 'median', 'capped5 mean')):
        obs = [y[a].mean()-y[b].mean(), np.median(y[a])-np.median(y[b]), np.clip(y[a],-5,5).mean()-np.clip(y[b],-5,5).mean()][j]
        print(f"  {name} difference in {lab:<13}{obs:+.3f}  95% range {np.percentile(o[:,j],2.5):+.3f} to {np.percentile(o[:,j],97.5):+.3f}  P(<=0)={np.mean(o[:,j]<=0):.3f}")

print("\nQUESTION 1: does having a CEO among the four buyers matter? (excess over SPY, ATR; SPY beside stock)")
row("all liquid", np.ones(len(L), bool)); row("CEO among buyers", ceo); row("no identified CEO", ~ceo)
diff("CEO minus no-CEO", ceo, ~ceo)
print("\nCEO x CFO cells:"); row("CEO and CFO", ceo & cfo); row("CEO, no CFO", ceo & ~cfo); row("CFO, no CEO", ~ceo & cfo); row("neither", ~ceo & ~cfo)
print("\nQUESTIONS ASKED IN THIS RUN: 1 (CEO vs no CEO) plus the 4-cell split shown for context.")

print("\n=== SCHEMA DUMP (one liquid trade) for the ownership-size analysis ===")
r0 = L[0]['row']
def short_repr(v):
    s = json.dumps(v, default=str); return s if len(s) <= 110 else s[:107] + '...'
for k in sorted(r0): print(f"row.{k}: {short_repr(r0[k])}")
for k in sorted(r0['owners'][0]): print(f"owner.{k}: {short_repr(r0['owners'][0][k])}")
for k in sorted(r0.get('entry_features', {})): print(f"entry_features.{k}: {short_repr(r0['entry_features'][k])}")
keys = set()
for t in L: keys |= set(t['row'])
print("ALL ROW KEYS:", sorted(keys))
for k in sorted(keys):
    if re.search(r'own|hold|after|follow|shares|value|trans|ratio|signif', k, re.I):
        nz = sum(1 for t in L if t['row'].get(k) not in (None, [], {}, ''))
        print(f"FIELD {k}: non-empty on {nz} of {len(L)} liquid trades")
