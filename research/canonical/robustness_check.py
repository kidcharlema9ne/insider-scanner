"""Step 2A: outlier-robust and clustered-by-week checks on the 91 liquid four-plus trades.
Imports the canonical selector (ChatGPT's recovered code, unchanged). Everything here is new, read-only code.
Excess = stock 21-session ATR return minus SPY restated in the stock's ATR (D-053)."""
import datetime, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from cluster_selector import load_cohort

SEED, B = 20261107, 10000
c = load_cohort(sys.argv[1], 'current.zip')
L = c.liquid
y = np.array([t['excess_atr'] for t in L]); stock = np.array([t['stock_atr'] for t in L]); spy = np.array([t['spy_atr'] for t in L])
wk = np.array([datetime.date.fromisoformat(t['entry']).isocalendar()[:2][0]*100 + datetime.date.fromisoformat(t['entry']).isocalendar()[:2][1] for t in L])
weeks = sorted(set(wk)); n = len(y)
print(f"COHORT n={n} entry_dates={len({t['entry'] for t in L})} iso_weeks={len(weeks)} tickers={len({t['ticker'] for t in L})}")
print(f"SELF-CHECK mean excess {y.mean():+.4f} (expect +0.5257); stock {stock.mean():+.4f} SPY {spy.mean():+.4f}")
assert n == 91 and abs(y.mean()-0.5257) < 5e-4

def trimmed(a, p=0.05):
    k = int(round(len(a)*p)); s = np.sort(a); return s[k:len(a)-k].mean()
stats = {
    'mean': lambda a: a.mean(), 'median': np.median,
    'trimmed mean (5% each tail)': trimmed,
    'capped mean (each trade limited to +-5 ATR)': lambda a: np.clip(a, -5, 5).mean(),
    'capped mean (+-3 ATR)': lambda a: np.clip(a, -3, 3).mean(),
}
rng = np.random.default_rng(SEED)
by_week = {w: np.where(wk == w)[0] for w in weeks}
def week_boot(fn):
    out = np.empty(B)
    for b in range(B):
        pick = rng.choice(len(weeks), len(weeks), replace=True)
        idx = np.concatenate([by_week[weeks[p]] for p in pick])
        out[b] = fn(y[idx])
    return out
print(f"\nHEADLINE (excess over SPY, ATR; SPY mean {spy.mean():+.3f} beside stock mean {stock.mean():+.3f}); week-block bootstrap B={B}, seed {SEED}")
print(f"{'statistic':<46}{'value':>8}{'95% low':>9}{'95% high':>9}{'P(<=0)':>8}")
for name, fn in stats.items():
    bs = week_boot(fn)
    print(f"{name:<46}{fn(y):>+8.3f}{np.percentile(bs,2.5):>+9.3f}{np.percentile(bs,97.5):>+9.3f}{(bs<=0).mean():>8.3f}")

print("\nLEAVE-ONE-WEEK-OUT (mean excess after removing each ISO week), worst and best 5:")
lo = sorted(((y[wk != w].mean(), w, int((wk == w).sum()), y[wk == w].sum()) for w in weeks))
for m, w, k, s in lo[:5] + lo[-5:]:
    print(f"  drop week {w}: n_removed={k:>2} week_total={s:+7.2f}  mean_without={m:+.3f}")
print("  weeks with total excess > 0:", sum(y[wk == w].sum() > 0 for w in weeks), "of", len(weeks))
wt = sorted(((y[wk == w].sum(), w) for w in weeks), reverse=True)
tot = y.sum()
print("  top 4 weeks share of total:", ", ".join(f"{w}:{s/tot:.0%}" for s, w in wt[:4]), "| cumulative", f"{sum(s for s,_ in wt[:4])/tot:.0%}")

pos = int((y > 0).sum())
p_sign = sum(math.comb(n, k) for k in range(pos, n+1)) / 2**n
print(f"\nSIGN TEST: {pos} of {n} beat SPY; one-sided P(>= {pos} | coin flip) = {p_sign:.3f}")
print(f"Weeks as units: {sum(y[wk==w].mean() > 0 for w in weeks)} of {len(weeks)} weeks have positive mean excess")

print("\nSELECTOR SENSITIVITY (only the choices exposed as parameters in the recovered select(); sole-owner and")
print("one-filing-per-cluster are hard-coded, so they cannot be varied without editing ChatGPT's code, which we do not do)")
print(f"{'entity-excl':<12}{'strategy':<10}{'same-title':<11}{'events':>7}{'done':>6}{'liquid':>7}{'mean excess':>12}{'median':>8}{'capped5':>9}")
lt = c.lt
def liquid_row(row):
    return float(row['entry_features'].get('average_daily_dollars_15', 0)) >= 3_000_000
variants = 0
for ent in (True, False):
    for strat in ('same', 'previous', 'first'):
        for st in (True, False):
            ev, _ = lt.select(ent, strat, 0, st); variants += 1
            done = [e for e in ev if lt.has(e[2])]
            liq = [e for e in done if liquid_row(e[2])]
            ex = np.array([float(lt.returns(e[2])[2]) for e in liq])
            tag = ' <- canonical' if (ent, strat, st) == (True, 'same', True) else ''
            print(f"{str(ent):<12}{strat:<10}{str(st):<11}{len(ev):>7}{len(done):>6}{len(liq):>7}{ex.mean():>+12.3f}{np.median(ex):>+8.3f}{np.clip(ex,-5,5).mean():>+9.3f}{tag}")
print(f"\nVARIANT COUNT: {variants} selector variants + {len(stats)} summary statistics shown here; earlier family (Entry 5): 12 small + 702 wide slices; Entry 6: 5 cut-offs.")
