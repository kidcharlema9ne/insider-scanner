"""Percent-fall profile of the deep-fall groups (POST HOC, asked by Michael 8 Nov 2026; follow-up to Entry 50).

Question: stocks down 12+ ATR over 6 to 9 months had a large 21-session excess over SPY (Entry 49). What PERCENT declines were they?
Entry 50 derived percent = D*a/(1+D*a) (a = ATR / price); this script MEASURES it on the same events.

Cohort: Entry 28 development events (entries <= 2020-12-31, D-068) with the 21-session return and the look-back feature, exactly as
`decline_buckets.load` builds it (Entry 36 features run 42499472150, 9-month features from Entry 49 run 42508173058, returns run 42490748366).
No 2021-2025 return is read; the 2026 pilot is not used. No new returns or features are computed.

Menu (declared before the run): windows 6m (126 sessions) and 9m (189 sessions); groups by fall D in entry-ATR units:
  cumulative  D >= 10, >= 12, >= 15, >= 20     bands  10-12, 12-15, 15-20, 20+      (8 groups per window, 16 cells)
Per cell: n, entry weeks, separate entry spells (gap > 42 calendar days); PERCENT fall = -pctW*100 (close before entry vs close W sessions
earlier): mean, 10/25/50/75/90th percentile, share down more than 35% and more than 50%; ATR as % of entry open (quartiles);
the Entry 50 formula's predicted percent fall per event (D*a/(1+D*a), a = atr / entry_open) beside the measured one (mean and mean absolute
gap); 21-session excess over same-window SPY in ATR (stock and SPY legs, D-053) and in percent (excess_atr * atr/entry_open, the
Entry 36 definition); median and share beating SPY. Also, for D >= 12 only: percent-fall bands (<35, 35-50, 50-65, 65+) with excess.
No chance test is run: nothing here is a new hypothesis; it describes groups already found in Entry 49. Cautions from Entry 49 stand
(survivorship, costs, few separate spells, headline chosen after seeing the grid).

Usage:  python decline_percent_profile.py scan DECLINE_FOLDER F189_FOLDER RETURNS_FOLDER   |   --selftest
"""
import statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decline_buckets as db
import factor_decline as fd
from factor_regime import spells

WINDOWS = ((126, '6m'), (189, '9m'))
GROUPS = [('>=10', 10, None), ('>=12', 12, None), ('>=15', 15, None), ('>=20', 20, None),
          ('10-12', 10, 12), ('12-15', 12, 15), ('15-20', 15, 20), ('20+', 20, None)]
BANDS = [('<35%', None, 35), ('35-50%', 35, 50), ('50-65%', 50, 65), ('65%+', 65, None)]


def quant(v, p):
    s = sorted(v)
    if not s:
        return float('nan')
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def enrich(r, W):
    d = r.get(f'raw{W}')
    p = r.get(f'pct{W}')
    if d is None or p is None or not r.get('entry_open') or not r.get('atr'):
        return None
    D = -d
    a = r['atr'] / r['entry_open']
    return {'D': D, 'pct': -100.0 * p, 'a': a, 'pred': 100.0 * D * a / (1 + D * a) if D > 0 else float('nan'),
            'ex': r['excess_atr'], 'st': r['stock_atr'], 'sp': r['spy_atr'], 'expct': 100.0 * r['excess_atr'] * a, 'entry': r['entry'],
            'week': fd.week_of(r)}


def in_group(x, lo, hi):
    return x >= lo and (hi is None or x < hi)


def describe(rs):
    n = len(rs)
    if n == 0:
        return 'n=0'
    pc = [r['pct'] for r in rs]
    at = [100 * r['a'] for r in rs]
    gap = [abs(r['pred'] - r['pct']) for r in rs]
    ex = [r['ex'] for r in rs]
    ds = sorted(r['entry'] for r in rs)
    line1 = (f'n={n:4d} w={len({r["week"] for r in rs}):3d} sp={len(spells(ds)):2d} | percent fall: mean {statistics.fmean(pc):.1f}%, '
             f'p10 {quant(pc, .1):.0f} p25 {quant(pc, .25):.0f} median {quant(pc, .5):.0f} p75 {quant(pc, .75):.0f} p90 {quant(pc, .9):.0f}; '
             f'down >35%: {sum(p > 35 for p in pc) / n:.0%}, >50%: {sum(p > 50 for p in pc) / n:.0%}')
    line2 = (f'      ATR as % of entry open: p25 {quant(at, .25):.1f} median {quant(at, .5):.1f} p75 {quant(at, .75):.1f} | Entry 50 formula: mean predicted '
             f'{statistics.fmean(r["pred"] for r in rs):.1f}% vs measured {statistics.fmean(pc):.1f}%, mean abs gap {statistics.fmean(gap):.1f} pts')
    line3 = (f'      21-session excess over SPY {statistics.fmean(ex):+.3f} ATR (stock {statistics.fmean(r["st"] for r in rs):+.3f}, SPY '
             f'{statistics.fmean(r["sp"] for r in rs):+.3f}) = {statistics.fmean(r["expct"] for r in rs):+.2f}% of price; median {statistics.median(ex):+.3f} ATR, '
             f'beat SPY {sum(e > 0 for e in ex) / n:.0%}')
    return '\n'.join((line1, line2, line3))


def scan(decl, f189, ret):
    dev, mism = db.load(decl, f189, ret)
    print(f'development n={len(dev)} excess {statistics.fmean(r["excess_atr"] for r in dev):+.3f} (Entry 28: +0.154); reproduction differences {mism}')
    for W, lab in WINDOWS:
        rows = [x for x in (enrich(r, W) for r in dev) if x is not None]
        print(f'\n=== {lab} look-back ({W} sessions): events with the measure n={len(rows)}, all-event excess {statistics.fmean(r["ex"] for r in rows):+.3f} ATR ===')
        for name, lo, hi in GROUPS:
            g = [r for r in rows if in_group(r['D'], lo, hi)]
            print(f'\n-- fell {name} ATR --\n{describe(g)}')
        print(f'\n-- {lab}: events down >= 12 ATR split by measured percent fall (excess in ATR and percent) --')
        g12 = [r for r in rows if r['D'] >= 12]
        for name, lo, hi in BANDS:
            g = [r for r in g12 if (lo is None or r['pct'] >= lo) and (hi is None or r['pct'] < hi)]
            if g:
                ex = [r['ex'] for r in g]
                print(f'  {name:7s} n={len(g):4d} spells={len(spells(sorted(r["entry"] for r in g))):2d} excess {statistics.fmean(ex):+.3f} ATR '
                      f'({statistics.fmean(r["expct"] for r in g):+.2f}% of price) median {statistics.median(ex):+.3f} beat SPY {sum(e > 0 for e in ex) / len(ex):.0%}')
            else:
                print(f'  {name:7s} n=0')
    print('\nStatus: descriptive, post hoc; returns code PROVISIONAL as in Entry 28; no costs; survivorship exposure as in Entries 38/40/44.')


def selftest():
    import random
    rng = random.Random(3)
    rows = []
    for k in range(400):
        a = 0.03 + 0.08 * rng.random()
        D = 30 * rng.random()
        start = 20.0
        end = start / (1 + D * a)            # ATR measured at the post-fall price: start = end*(1 + D*a)
        atr = a * 10.0
        rows.append({'raw126': -D, 'pct126': end / start - 1, 'raw189': -D, 'pct189': end / start - 1, 'atr': atr, 'entry_open': 10.0,
                     'excess_atr': 0.1, 'stock_atr': 0.2, 'spy_atr': 0.1, 'entry': f'2010-0{1 + k % 9}-0{1 + k % 7}', 'sym': 'X', 'cik': str(k)})
    x = enrich(rows[0], 126)
    assert abs(x['pred'] - x['pct']) < 1e-6, (x['pred'], x['pct'])      # the formula is exact when a = ATR / post-fall price
    assert enrich({**rows[0], 'pct126': None}, 126) is None
    assert quant([1, 2, 3, 4, 5], .5) == 3 and quant([1, 2, 3, 4], .5) == 2.5
    assert in_group(12, 12, None) and not in_group(11.9, 12, None) and in_group(14.9, 12, 15) and not in_group(15, 12, 15)
    print(describe([e for e in (enrich(r, 126) for r in rows) if e and e['D'] >= 12][:50]).split('\n')[0][:60])
    print('decline_percent_profile self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    elif len(sys.argv) == 5 and sys.argv[1] == 'scan':
        scan(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
