"""Cost realism for the 12-month-fall lead (C8 fell-most fifth, raw252). Uses ONLY fields already in the committed Entry 28 returns
and Entry 36 decline-feature files (entry price, ATR, 21-session stock/SPY legs in ATR units, 252-session percent change), joined through
factor_decline.load, so the D-068 guard (development entries and the 2026 pilot) applies. No archive read, no new returns.

WHAT THIS CANNOT DO: there are no bid/ask quotes in the repo or the archive, so no cost here is measured. Every cost is an ASSUMED
percent-of-price round-trip number (spread plus slippage, both legs) converted into ATR units; the point is how much the answer
depends on the assumption, and where the lead breaks.

DECLARED BEFORE RUNNING (so nothing here is chosen after looking). Group: the fell-most fifth of raw252 (cut points recomputed on the
subset, as Entry 42), run for (i) development entries >= 2011-01-01 (Entry 42/44 subset, expect n=175, +0.565) and (ii) all
development years (Entry 36, expect n=255, +0.593). 'Rest' = the other four fifths of the same subset.
 A. Tradability profile, fell-most fifth vs rest: entry price (quartiles; share under $2, $5, $10, $20), ATR as % of entry price
    (quartiles), 252-session percent change (quartiles; share down more than 50%).
 B. Flat assumed round-trip cost c in {0.5%, 1%, 2%, 3%, 5%} of price: cost in ATR for a trade = c / (ATR/entry price); mean cost in ATR
    and mean net excess = mean excess - mean cost, for the fifth and for the rest.
 C. Break-even flat round-trip cost: the c at which the fifth's mean net excess is zero, c* = mean(excess) / mean(1 / atr_pct).
 D. Price-tiered assumed cost (ASSUMPTION, not measured): price >= $20 0.5%; $10-20 1%; $5-10 2%; < $5 4%; plus the same table doubled.
    Report stock leg, SPY leg, excess, cost, net (all ATR units; cost applies to the stock leg only), share of trades with net > 0,
    mean net without the 5 best trades, and the net by price band.
 E. The Entry 2 assumption (0.10 to 0.30 ATR round trip, unverified): net excess at 0.10 / 0.20 / 0.30 ATR flat, for reference.
Status: exploratory diagnostics of an exploratory lead. Nothing here is a tested result.
"""
import statistics, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from factor_decline import load, quintile_line, mean, week_of  # noqa: E402

M = 'raw252'
FLAT = (0.005, 0.01, 0.02, 0.03, 0.05)
BANDS = (('>=20', 20, 1e9, 0.005), ('10-20', 10, 20, 0.01), ('5-10', 5, 10, 0.02), ('<5', 0, 5, 0.04))


def atr_pct(r):
    return r['atr'] / r['entry_open']


def tier(r):
    p = r['entry_open']
    for name, lo, hi, c in BANDS:
        if lo <= p < hi:
            return name, c
    return BANDS[-1][0], BANDS[-1][3]


def quart(v):
    q = statistics.quantiles(sorted(v), n=4, method='inclusive')
    return f'{min(v):.2f} | {q[0]:.2f} | {q[1]:.2f} | {q[2]:.2f} | {max(v):.2f}'


def share(v, f):
    return sum(f(x) for x in v) / len(v)


def profile(name, rs):
    pr = [r['entry_open'] for r in rs]
    ap = [atr_pct(r) for r in rs]
    ch = [r['pct252'] for r in rs if 'pct252' in r]
    print(f'{name}: n={len(rs)}')
    print(f'  entry price (min|q1|median|q3|max): {quart(pr)}; share < $2 {share(pr, lambda x: x < 2):.1%}, < $5 {share(pr, lambda x: x < 5):.1%}, '
          f'< $10 {share(pr, lambda x: x < 10):.1%}, < $20 {share(pr, lambda x: x < 20):.1%}')
    print(f'  ATR % of price (min|q1|median|q3|max): {quart(ap)}')
    print(f'  252-session % change (n={len(ch)}) (min|q1|median|q3|max): {quart(ch)}; share down > 50% {share(ch, lambda x: x < -0.5):.1%}')


def flat_table(name, rs, base):
    ex = [r['excess_atr'] for r in rs]
    inv = [1 / atr_pct(r) for r in rs]
    print(f'  {name} (n={len(rs)}, mean excess {statistics.fmean(ex):+.3f} ATR):')
    for c in FLAT:
        cost = statistics.fmean([c * i for i in inv])
        print(f'    flat {c:.1%} round trip: mean cost {cost:.3f} ATR; mean net {statistics.fmean(ex) - cost:+.3f}')
    cstar = statistics.fmean(ex) / statistics.fmean(inv)
    print(f'    break-even flat round trip c* = {cstar:.2%} of price')
    for a in (0.10, 0.20, 0.30):
        print(f'    Entry 2 flat {a:.2f} ATR: net {statistics.fmean(ex) - a:+.3f}')


def tiered(name, rs, mult):
    rows = []
    for r in rs:
        b, c = tier(r)
        cost = mult * c / atr_pct(r)
        s = r['stock_atr']
        p = r['spy_atr']
        rows.append((r, b, cost, s, p, r['excess_atr'] - cost))
    net = [x[5] for x in rows]
    best5 = sorted(net)[:-5]
    print(f'  {name} tiered x{mult:g}: stock leg {statistics.fmean([x[3] for x in rows]):+.3f}, SPY leg {statistics.fmean([x[4] for x in rows]):+.3f}, '
          f'excess {statistics.fmean([x[0]["excess_atr"] for x in rows]):+.3f}, cost {statistics.fmean([x[2] for x in rows]):.3f}, '
          f'NET {statistics.fmean(net):+.3f}; net>0 {share(net, lambda v: v > 0):.1%}; net without 5 best {statistics.fmean(best5):+.3f}; '
          f'median net {statistics.median(net):+.3f}')
    by = {}
    for x in rows:
        by.setdefault(x[1], []).append(x)
    print('    by price band (n / mean excess / mean cost / mean net): ' + '; '.join(
        f"{b} {len(v)}/{statistics.fmean([y[0]['excess_atr'] for y in v]):+.2f}/{statistics.fmean([y[2] for y in v]):.2f}/{statistics.fmean([y[5] for y in v]):+.2f}"
        for b, v in sorted(by.items(), key=lambda kv: -len(kv[1]))))
    return net


def group(label, dev, start):
    import numpy as np
    sub = [r for r in dev if M in r and r['entry'] >= start]
    cuts = np.quantile([r[M] for r in sub], [.2, .4, .6, .8])
    fifths = quintile_line(sub, M, cuts)
    q1 = fifths[0]
    rest = [r for f in fifths[1:] for r in f]
    print(f'\n##### {label}: entries >= {start}; {len(sub)} events; fell-most fifth n={len(q1)}, {len({week_of(r) for r in q1})} weeks, '
          f'mean excess {mean(q1):+.3f}; cut points {np.round(cuts, 2).tolist()}')
    print('\n=== A. Tradability profile ===')
    profile('fell-most fifth', q1)
    profile('other four fifths', rest)
    print('\n=== B, C, E. Flat assumed costs ===')
    flat_table('fell-most fifth', q1, None)
    flat_table('other four fifths', rest, None)
    print('\n=== D. Price-tiered assumed cost (0.5% / 1% / 2% / 4% by price band) ===')
    for mult in (1, 2):
        tiered('fell-most fifth', q1, mult)
        tiered('other four fifths', rest, mult)


def run(features, returns):
    rows = load(features, returns)
    dev = [r for r in rows if r['entry'] <= '2020-12-31']
    group('(i) 2011-2020 subset (Entry 42/44)', dev, '2011-01-01')
    group('(ii) all development years (Entry 36)', dev, '2006-01-01')


def selftest():
    rs = [{'entry': f'2012-0{1 + i % 9}-01', 'atr': 0.5 + (i % 5) * 0.1, 'entry_open': 3 + (i * 7) % 40, 'excess_atr': float(i % 7) - 2,
           'stock_atr': 1.0, 'spy_atr': 0.4, 'pct252': -0.6 + (i % 10) / 10, 'cik': str(i)} for i in range(60)]
    profile('t', rs)
    flat_table('t', rs, None)
    tiered('t', rs, 1)
    assert tier({'entry_open': 25})[1] == 0.005 and tier({'entry_open': 4})[1] == 0.04
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        selftest()
    else:
        run(*sys.argv[1:3])
