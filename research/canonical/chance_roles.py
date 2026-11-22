"""Step 2E: chance test on the buyer-role result (clusters with neither a CEO nor a CFO among the buyers).
Imports the canonical selector (ChatGPT's code unchanged) plus add_roles (new, self-checked). Read-only.
Permutations keep each calendar week's trades together: outcomes are shuffled only among trades of the SAME week,
so the market backdrop of a week cannot create the result."""
import datetime, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from cluster_selector import load_cohort, add_roles

SEED, B = 20261107, 10000
c = add_roles(load_cohort(sys.argv[1], 'current.zip')); L = c.liquid
y = np.array([t['excess_atr'] for t in L]); st = np.array([t['stock_atr'] for t in L]); sp = np.array([t['spy_atr'] for t in L])
iso = [datetime.date.fromisoformat(t['entry']).isocalendar() for t in L]
wk = np.array([a[0]*100 + a[1] for a in iso]); weeks = sorted(set(wk)); N = len(L)
ceo = np.array([t['ceo'] for t in L]); cfo = np.array([t['cfo'] for t in L]); npd = np.array([t['n_pure_directors'] for t in L])
print(f"SELF-CHECK n={N} mean excess {y.mean():+.4f} (expect +0.5257); CEO {ceo.sum()} (expect 47) CFO {cfo.sum()} (expect 32) neither {(~ceo&~cfo).sum()} (expect 36)")
assert N == 91 and ceo.sum() == 47 and (~ceo & ~cfo).sum() == 36
rng = np.random.default_rng(SEED)
idx_by_week = [np.where(wk == w)[0] for w in weeks]
def shuffle_within_week(v):
    out = v.copy()
    for ix in idx_by_week: out[ix] = v[rng.permutation(ix)]
    return out
cap = lambda a: np.clip(a, -5, 5)
groups = {'neither CEO nor CFO': ~ceo & ~cfo, 'no CEO': ~ceo, 'CEO': ceo, 'CFO': cfo, 'no CFO': ~cfo,
          'CEO and CFO': ceo & cfo, 'CEO, no CFO': ceo & ~cfo, 'CFO, no CEO': ~ceo & cfo}
def edge(v, g): return v[g].mean() - v[~g].mean()

print("\nTEST 1 (the one pre-stated question): do clusters with neither a CEO nor a CFO beat the rest, beyond what their weeks explain?")
g = groups['neither CEO nor CFO']
for lab, fn in (('mean', lambda v: v), ('capped +-5 mean', cap)):
    obs = edge(fn(y), g); sims = np.array([edge(fn(shuffle_within_week(y)), g) for _ in range(B)])
    simsall = np.array([edge(fn(rng.permutation(y)), g) for _ in range(B)])
    print(f"  {lab:<16} group minus rest = {obs:+.3f}   chance (same-week shuffle) {np.mean(sims>=obs):.3%}   chance (shuffle all) {np.mean(simsall>=obs):.3%}")
medobs = np.median(y[g]) - np.median(y[~g]); ms = np.array([np.median(shuffle_within_week(y)[g]) - np.median(shuffle_within_week(y)[~g]) for _ in range(2000)])
print(f"  median           group minus rest = {medobs:+.3f}   chance (same-week shuffle, 2000) {np.mean(ms>=medobs):.3%}")

print("\nTEST 2 (honest family: every role split looked at so far, best one counts): chance that the BEST of the 8 groups below")
print("looks this good (largest 'group minus rest', groups of >= 8 trades), shuffling within weeks:")
names = [k for k, m in groups.items() if m.sum() >= 8]
obs_all = {k: edge(y, groups[k]) for k in names}; best = max(obs_all.values()); bn = max(obs_all, key=obs_all.get)
sims = np.array([max(edge(yy, groups[k]) for k in names) for yy in (shuffle_within_week(y) for _ in range(B))])
print(f"  observed best: {bn} = {best:+.3f};  chance of a best-of-{len(names)} at least that large: {np.mean(sims>=best):.3%}")
print("  all groups:", "; ".join(f"{k} n={groups[k].sum()} {obs_all[k]:+.2f}" for k in names))

print("\nROBUSTNESS of 'neither CEO nor CFO' minus rest (excess, ATR):")
def rob(label, keep):
    gg, yy = g[keep], y[keep]
    print(f"  {label:<44} n_group={gg.sum():>2} n_rest={(~gg).sum():>2}  group {yy[gg].mean():+.3f}  rest {yy[~gg].mean():+.3f}  diff {edge(yy, gg):+.3f}  medians {np.median(yy[gg]):+.3f} / {np.median(yy[~gg]):+.3f}")
rob('all 91', np.ones(N, bool))
order = np.argsort(-y)
for k in (1, 3, 5): rob(f'without the overall top {k} trades', ~np.isin(np.arange(N), order[:k]))
rob('without ISO week 202622', wk != 202622)
hot = np.isin(wk, [202620, 202621, 202622, 202623, 202625])
rob('only the 5 hottest weeks (20-23, 25)', hot); rob('all other weeks', ~hot)
print("\nTOP 10 trades by excess, with role cell:")
for r, i in enumerate(order[:10], 1):
    cell = 'neither' if (~ceo[i] and ~cfo[i]) else ('CEO+CFO' if ceo[i] and cfo[i] else 'CEO only' if ceo[i] else 'CFO only')
    print(f"  {r:>2} {L[i]['entry']} {L[i]['ticker']:<6} excess {y[i]:+6.2f}  {cell:<9} pure directors among buyers: {npd[i]}")
tot = y.sum()
print("Share of total gain by cell:", "; ".join(f"{k} {y[groups[k]].sum()/tot:.0%} of gain from {groups[k].mean():.0%} of trades" for k in ('neither CEO nor CFO', 'CEO', 'CFO, no CEO')))

print("\nDIRECTOR IDEA (descriptive; second question): number of PURE directors (director, not an officer) among the buyers")
for k in sorted(set(npd)):
    m = npd == k
    print(f"  {k} pure directors: n={m.sum():>2} excess {y[m].mean():+.3f} median {np.median(y[m]):+.3f} capped {cap(y[m]).mean():+.3f} stock {st[m].mean():+.3f} SPY {sp[m].mean():+.3f}")
def rho(v, x):
    rv = np.argsort(np.argsort(v)); rx = np.argsort(np.argsort(x)); return np.corrcoef(rv, rx)[0, 1]
r0 = rho(y, npd); sr = np.array([rho(shuffle_within_week(y), npd) for _ in range(B)])
print(f"  Spearman rank correlation of excess with pure-director count: {r0:+.3f}; chance (same-week shuffle, two-sided) {np.mean(np.abs(sr)>=abs(r0)):.3f}")
print(f"\nQUESTIONS ASKED ON THIS COHORT SO FAR: earlier families (Entry 5: 714 slices, Entry 6: 5 cut-offs, Entry 9: 5 stats + 12 selector variants), Entry 10: CEO split, this run: Test 1, Test 2 (8 groups), director count (1).")
