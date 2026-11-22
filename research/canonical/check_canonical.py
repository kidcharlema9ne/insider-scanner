"""Reproduction check for the canonical selector + step 3 (top trades behind the +0.53 average).
Imports cluster_selector (which runs ChatGPT's recovered code unchanged). Read-only."""
import sys, statistics as st
sys.path.insert(0, __import__('os').path.dirname(__file__))
from cluster_selector import load_cohort

c = load_cohort(sys.argv[1], 'current.zip')
L = c.liquid
m = lambda xs: sum(xs)/len(xs)
print(f"CHECK completed={len(c.all_trades)} (expect 137)  liquid={len(L)} (expect 91)")
print(f"CHECK liquid stock={m([t['stock_atr'] for t in L]):+.4f} SPY={m([t['spy_atr'] for t in L]):+.4f} "
      f"excess={m([t['excess_atr'] for t in L]):+.4f} median={st.median([t['excess_atr'] for t in L]):+.4f} "
      f"(expect +0.5337 / +0.0080 / +0.5257 / +0.1651)")
assert len(c.all_trades) == 137 and len(L) == 91
assert abs(m([t['excess_atr'] for t in L]) - 0.5257) < 5e-4
print("PASS: canonical selector reproduces the confirmed cohort")

ys = sorted(L, key=lambda t: -t['excess_atr'])
n = len(L); tot = sum(t['excess_atr'] for t in L)
print(f"\nTOP 10 of {n} liquid trades by 21-session excess over SPY (ATR). Total excess = {tot:.2f} ATR; mean {tot/n:+.3f}")
print("rank entry       ticker  issuer_cik  CFO  stock_ATR  SPY_ATR  excess  decline15  SPYreg15  ADV$M  cum_share_of_total")
cum = 0
for r, t in enumerate(ys[:10], 1):
    cum += t['excess_atr']
    print(f"{r:>3}  {t['entry']} {t['ticker']:<7} {t['issuer_cik']:<10} {str(t['cfo'])[0]}   {t['stock_atr']:+8.2f} {t['spy_atr']:+8.2f} {t['excess_atr']:+7.2f} "
          f"{t['decline_15_atr']:+8.2f} {t['spy_regime_15']:+8.2f} {t['adv']/1e6:6.1f}   {cum/tot:6.1%}")
for k in (1, 3, 5, 10):
    rest = ys[k:]
    print(f"mean excess without top {k:>2}: {m([t['excess_atr'] for t in rest]):+.4f}  (n={len(rest)})")
print("bottom 5:", [(t['ticker'], t['entry'], round(t['excess_atr'], 2)) for t in ys[-5:]])
print("distinct tickers:", len({t['ticker'] for t in L}), " distinct entry dates:", len({t['entry'] for t in L}),
      " positive vs SPY:", sum(t['excess_atr'] > 0 for t in L), "of", n)
