"""Survivorship check for the 12-month-fall lead (C8, Entry 36). Counts and diagnostics only; returns come from
the committed Entry 28 files via factor_decline.load, so the D-068 guard (development years and 2026 pilot) applies.

DECLARED BEFORE RUNNING (so nothing here is chosen after looking):
 A. Census of refined events with no price series: by entry year, by ticker category and by archive status,
    plus the most frequent unmatched tickers in the development years (to see which are my matching errors).
 B. Break-even: the worst-hit fifth by raw 252-session change (Q1, from Entry 36 data) has some mean; if m events
    were missing from it with average excess X (ATR), what would its mean be?  Grid: m in {0, equal-rate, double-rate},
    X in {0,-1,-2,-3,-5}.  Equal-rate m = n * p/(1-p), p = share of refined events with a usable ticker but no series.
 C. Q1 breadth: median, share with excess > 0, mean without the 5 best, trimmed mean (10% each tail),
    count and mean by year, distinct issuers, mean with one event per issuer (earliest).
Status: exploratory diagnostics of an exploratory lead. Nothing here is a tested result.

ADDED 8 Nov 2026 (Entry 43), DECLARED BEFORE RUNNING: optional 5th argument `start` (e.g. 2011-01-01) restricts to
development entries >= start; cut points of M are recomputed on that subset (as Entry 42), so Q1 = the subset's fell-most fifth.
 D. Year-matched break-even for that fifth: expected missing events per entry year y = n_y * p_y/(1-p_y), with p_y the census
    no-price share of usable-ticker refined events in year y (Entry 38 census, restricted to the start-year onward).
    Grid X in {0,-1,-2,-3,-5} ATR for the missing events at 1x and 2x the year-matched count, plus the number of missing
    events (at each X) needed to pull the fifth to (i) the subset all-event mean and (ii) zero.
 E. Same grid when the missing events are assumed to be fell-most-fifth names only (the census rate applied to the fifth's
    own years is a floor; 'concentrated' scenario = the whole expected missing count of the subset, all in this fifth).
"""
import json, statistics, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from factor_decline import load, quintile_line, mean, week_of  # noqa: E402

M = 'raw252'


def census(events, year_files):
    from archive_coverage_audit import normalize_ticker
    refined = [e for e in events if e['set'] == 'refined']
    tcat = Counter()
    for e in refined:
        sym, cat = normalize_ticker(e['ticker'])
        e['sym'], e['tcat'] = sym, cat
        tcat[(e['entry'][:4], cat)] += 1
    status = Counter()
    nop = []
    for fn in year_files:
        d = json.loads(Path(fn).read_text())
        for r in d['results']:
            if r['set'] != 'refined':
                continue
            status[(d['year'], r['status'])] += 1
            if r['status'] == 'no_price':
                nop.append(r)
    return refined, tcat, status, nop


def print_census(refined, tcat, status, nop):
    years = sorted({e['entry'][:4] for e in refined})
    cats = sorted({c for _, c in tcat})
    sts = sorted({s for _, s in status})
    print('\n=== A. Census of refined events ===')
    print('year  total | ticker category: ' + ' '.join(cats) + ' | archive status (usable ticker): ' + ' '.join(sts))
    tot = Counter()
    for y in years:
        n = sum(v for (yy, _), v in tcat.items() if yy == y)
        row = f'{y}  {n:5d} | ' + ' '.join(f'{tcat[(y, c)]:4d}' for c in cats) + ' | ' + ' '.join(f'{status[(int(y), s)]:4d}' for s in sts)
        print(row)
        tot['n'] += n
        tot['nop'] += status[(int(y), 'no_price')]
        tot['usable'] += sum(status[(int(y), s)] for s in sts)
    p = tot['nop'] / tot['usable'] if tot['usable'] else float('nan')
    print(f"all years: refined events {tot['n']}; with usable ticker {tot['usable']}; no price series {tot['nop']} ({p:.1%} of usable)")
    dev = [r for r in nop if r['entry'] <= '2020-12-31']
    print(f'no-price events in development years (<=2020): {len(dev)}; most frequent symbols: {Counter(r["sym"] for r in dev).most_common(25)}')
    return p


def breakeven(q1, p):
    n, mu = len(q1), mean(q1)
    eq = round(n * p / (1 - p))
    print(f'\n=== B. Break-even for the worst-hit fifth: n={n}, mean {mu:+.3f} ATR; missing-rate p={p:.3f} ===')
    print('missing m | mean if the missing events averaged X = 0 / -1 / -2 / -3 / -5 ATR')
    for label, m in (('0', 0), (f'equal-rate {eq}', eq), (f'double-rate {2 * eq}', 2 * eq)):
        print(f'{label:>16} | ' + ' / '.join(f'{(n * mu + m * x) / (n + m):+.3f}' for x in (0, -1, -2, -3, -5)))
    base = 0.154
    print('events that would need to be missing, each at X, to pull the fifth down to the all-event +0.154:')
    print('  ' + ', '.join(f'X={x}: {n * (mu - base) / (base - x):.0f}' for x in (-1, -2, -3, -5, -8)))


def year_rates(status):
    out = {}
    for (y, st), v in status.items():
        d = out.setdefault(str(y), [0, 0])
        d[0] += v
        if st == 'no_price':
            d[1] += v
    return {y: (nop / tot if tot else 0.0) for y, (tot, nop) in out.items()}, out


def concentrated(q1, sub, rates, start):
    n, mu = len(q1), mean(q1)
    ny = Counter(r['entry'][:4] for r in sub)
    mt = sum(c * rates.get(y, 0) / (1 - rates.get(y, 0)) for y, c in ny.items())
    print(f'\n=== E. Concentrated scenario: all {mt:.0f} expected missing events of the subset (entry >= {start}) are fell-most names ===')
    print('mean if they averaged X = 0 / -1 / -2 / -3 / -5 ATR: ' + ' / '.join(f'{(n * mu + mt * x) / (n + mt):+.3f}' for x in (0, -1, -2, -3, -5)))


def breakeven_year(q1, rates, base, start):
    n, mu = len(q1), mean(q1)
    ny = Counter(r['entry'][:4] for r in q1)
    m1 = sum(c * rates.get(y, 0) / (1 - rates.get(y, 0)) for y, c in ny.items())
    print(f'\n=== D. Year-matched break-even, fell-most fifth from {start}: n={n}, mean {mu:+.3f} ATR; subset all-event mean {base:+.3f} ===')
    print('year: n in fifth / census no-price share / expected missing: ' + ', '.join(
        f"{y} {c}/{rates.get(y, 0):.1%}/{c * rates.get(y, 0) / (1 - rates.get(y, 0)):.1f}" for y, c in sorted(ny.items())))
    print(f'expected missing (1x) {m1:.1f}; 2x {2 * m1:.1f}')
    print('missing m | mean if the missing events averaged X = 0 / -1 / -2 / -3 / -5 ATR')
    for label, m in (('1x', m1), ('2x', 2 * m1)):
        print(f'{label + " " + format(m, ".0f"):>16} | ' + ' / '.join(f'{(n * mu + m * x) / (n + m):+.3f}' for x in (0, -1, -2, -3, -5)))
    for tag, tgt in (('subset all-event mean', base), ('zero', 0.0)):
        print(f'missing events needed (each at X) to pull the fifth to {tag} ({tgt:+.3f}): ' + ', '.join(
            f'X={x}: {n * (mu - tgt) / (tgt - x):.0f}' for x in (-1, -2, -3, -5, -8)))
    print(f'  (compare with expected missing {m1:.1f}; share of fifth: needed/n)')
    return m1


def trimmed(v, k=0.1):
    v = sorted(v)
    c = int(len(v) * k)
    return statistics.fmean(v[c:len(v) - c])


def breadth(q1):
    v = [r['excess_atr'] for r in q1]
    top5 = sorted(v)[:-5]
    print(f'\n=== C. Q1 breadth: n={len(v)}, {len({week_of(r) for r in q1})} weeks ===')
    print(f'mean {statistics.fmean(v):+.3f}; median {statistics.median(v):+.3f}; share excess>0 {sum(x > 0 for x in v) / len(v):.1%}; '
          f'mean without 5 best {statistics.fmean(top5):+.3f}; 10%-trimmed {trimmed(v):+.3f}; best {max(v):+.2f}, worst {min(v):+.2f}')
    by = {}
    for r in q1:
        by.setdefault(r['entry'][:4], []).append(r)
    print('by year: ' + ', '.join(f'{y} {len(rs)}/{mean(rs):+.2f}' for y, rs in sorted(by.items())))
    first = {}
    for r in sorted(q1, key=lambda r: r['entry']):
        first.setdefault(r['cik'], r)
    per = Counter(r['cik'] for r in q1)
    print(f'distinct issuers {len(first)}; events from issuers with 2+ events {sum(v for v in per.values() if v > 1)}; '
          f'mean with earliest event per issuer {mean(list(first.values())):+.3f} (n={len(first)})')


def run(events_json, year_dir, features, returns, start=None):
    import numpy as np
    refined, tcat, status, nop = census(json.loads(Path(events_json).read_text()), sorted(Path(year_dir).glob('year_*.json')))
    p = print_census(refined, tcat, status, nop)
    rows = load(features, returns)
    dev = sorted([r for r in rows if r['entry'] <= '2020-12-31'], key=week_of)
    sub = [r for r in dev if M in r]
    cuts = np.quantile([r[M] for r in sub], [.2, .4, .6, .8])
    q1 = quintile_line(sub, M, cuts)[0]
    print(f'\nQ1 of {M} in development years: n={len(q1)} (Entry 36: n=255, +0.593); cut points {np.round(cuts, 2).tolist()}')
    breakeven(q1, p)
    breadth(q1)
    if start:
        rates, _ = year_rates(status)
        sub2 = [r for r in sub if r['entry'] >= start]
        cuts2 = np.quantile([r[M] for r in sub2], [.2, .4, .6, .8])
        q2 = quintile_line(sub2, M, cuts2)[0]
        base = mean(sub2)
        print(f'\nSUBSET entry >= {start}: {len(sub2)} events, all-event mean {base:+.3f}; Q1 of {M} n={len(q2)} '
              f'(Entry 42: 872 events, n=175, +0.565); cut points {np.round(cuts2, 2).tolist()}')
        breakeven_year(q2, rates, base, start)
        concentrated(q2, sub2, rates, start)
        breadth(q2)


def selftest():
    rows = [{'excess_atr': float(i % 7) - 2, 'cik': str(i % 5), 'entry': f'2010-0{1 + i % 9}-01'} for i in range(60)]
    assert abs(trimmed([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) - 5.5) < 1e-9
    breakeven(rows, 0.165)
    breadth(rows)
    concentrated(rows, rows, {'2010': 0.2}, '2010-01-01')
    breakeven_year(rows, {'2010': 0.2, '2011': 0.1, '2012': 0.1, '2013': 0.1, '2014': 0.1, '2015': 0.1}, 0.0, '2010-01-01')
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        selftest()
    else:
        run(*sys.argv[1:6])
