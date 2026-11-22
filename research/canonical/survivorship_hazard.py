"""C26a: how big is the survivorship risk for the deep-fall lead (D1)?  Hazard, imputation, break-even hazard, dose-response.

Development years only (entries <= 2020-12-31; D-068 via assert_allowed). Returns are the Entry 28 results (run 42490748366),
features the Entry 36 decline features (run 42499472150), census the Entry 38 census (run 42488283630 year files). No 2021+ return is read.
Exploratory diagnostics of an exploratory lead; nothing here is a tested result.

DECLARED BEFORE RUNNING:
 Cohorts. D1 = raw252 <= the 20th percentile of raw252 over COMPLETE development trades (Entry 36: cut -15.32, n=255, +0.593).
   The cut is applied to every row with a feature, complete or incomplete. 'Subset' = entries >= 2011-01-01 with the cut recomputed on
   that subset's complete trades (Entries 42/44: n=175, +0.565).
 A. In-archive hazard at 21 sessions. Status 'incomplete' = the stock's series ended before session 21 (the Entry 28 code values it at the
    last close; the lead tables so far use COMPLETE trades only, see factor_decline.load). Report incomplete / (complete + incomplete) for all
    development events, for D1, for non-D1, 2006-10 vs 2011-20, by year; mean excess of the incomplete rows as valued; D1 mean with them added.
 B. Imputed terminal loss. For incomplete D1 rows replace the last-close value by a terminal return of -30% (NYSE/Amex) and -55% (Nasdaq) of the
    entry open (Shumway 1997; Shumway and Warther 1999), and -100% as a bound: stock_atr = -p * entry_open / atr; excess = stock_atr - spy_atr.
 C. Unobserved hazard grid. D1 plus m = h * n extra events (events missing from the archive that would have been in D1 and wiped out), each with
    excess x = -p * mean(entry_open/atr over D1) - mean(spy_atr over D1), for h in 0, 1, 2, 3, 5, 8, 10 % and p in 30%, 55%; and the h
    that pulls D1 to the all-event mean and to zero. Run for the full development D1 and for the 2011+ subset.
 D. Dose-response. D1 mean excess and D1 minus non-D1 gap by entry year against the census no-price share of that year (Entry 38); Spearman over
    years with at least 8 D1 events; 2006-10 vs 2011-20. Survivorship bias predicts a positive link (more missing -> more flattering). Years are
    few and market regime is confounded: weak evidence either way.
"""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_decline import mean, week_of, rank_avg  # noqa: E402
from refined_baseline import DEV_END, assert_allowed  # noqa: E402

M = 'raw252'
P_TERMINAL = (0.30, 0.55)
H_GRID = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10)


def load_all(features_folder, returns_folder):
    feats = {}
    for p in sorted(Path(features_folder).glob('decline_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            feats[(r['cik'], r['sym'], r['entry'])] = r
    rows, other = [], Counter()
    for p in sorted(Path(returns_folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            if r['status'] not in ('complete', 'incomplete'):
                other[r['status']] += 1
                continue
            f = feats.get((r['cik'], r['sym'], r['entry']))
            if not f or f['status'] != 'ok':
                other['no_feature'] += 1
                continue
            rows.append({**r, **{k: v for k, v in f.items() if k not in ('status', 'entry', 'sym', 'cik')}})
    print(f'rows joined (complete + incomplete): {len(rows)} ({Counter(r["status"] for r in rows)}); skipped: {dict(other)}')
    return rows


def d1_cut(rows):
    import numpy as np
    comp = [r[M] for r in rows if r['status'] == 'complete' and M in r]
    return float(np.quantile(comp, 0.2))


def share(rows):
    inc = sum(r['status'] == 'incomplete' for r in rows)
    return f'{inc}/{len(rows)} = {inc / len(rows):.2%}' if rows else 'n=0'


def hazard_table(dev, cut):
    d1 = [r for r in dev if M in r and r[M] <= cut]
    rest = [r for r in dev if M in r and r[M] > cut]
    print('\n=== A. In-archive hazard: series ended before session 21 (incomplete) ===')
    print(f'all development events with a feature: {share([r for r in dev if M in r])}')
    print(f'D1: {share(d1)}; non-D1: {share(rest)}')
    e1 = [r for r in dev if M in r and r['entry'] < '2011-01-01']
    e2 = [r for r in dev if M in r and r['entry'] >= '2011-01-01']
    print(f'2006-10: all {share(e1)}; D1 {share([r for r in e1 if r[M] <= cut])}')
    print(f'2011-20: all {share(e2)}; D1 {share([r for r in e2 if r[M] <= cut])}')
    print('D1 by year (incomplete/total): ' + ', '.join(
        f"{y} {sum(r['status'] == 'incomplete' for r in d1 if r['entry'][:4] == y)}/{sum(r['entry'][:4] == y for r in d1)}"
        for y in sorted({r['entry'][:4] for r in d1})))
    inc = [r for r in d1 if r['status'] == 'incomplete']
    comp = [r for r in d1 if r['status'] == 'complete']
    print(f'D1 complete: n={len(comp)}, excess {mean(comp):+.3f}; D1 incomplete (valued at last close): n={len(inc)}, excess {mean(inc):+.3f}'
          if inc else f'D1 complete: n={len(comp)}, excess {mean(comp):+.3f}; D1 incomplete: n=0')
    print(f'D1 complete + incomplete (last close): n={len(d1)}, excess {mean(d1):+.3f}')
    if inc:
        print('D1 incomplete rows: ' + '; '.join(f"{r['sym']} {r['entry']} stock {r['stock_atr']:+.2f} spy {r['spy_atr']:+.2f} ATR, exit {r['exit']}" for r in inc[:12]))
    return d1, comp, inc


def imputed(comp, inc, p):
    """Mean excess of complete + incomplete rows with each incomplete row's stock leg replaced by a terminal return of -p."""
    vals = [r['excess_atr'] for r in comp] + [-p * r['entry_open'] / r['atr'] - r['spy_atr'] for r in inc]
    return sum(vals) / len(vals) if vals else float('nan')


def imputation_table(comp, inc):
    print('\n=== B. D1 mean if the incomplete rows ended at a terminal loss of p of the entry open ===')
    if not inc:
        print('no incomplete D1 rows')
        return
    print(f'as valued (last close): {mean(comp + inc):+.3f}; ' + '; '.join(f'p={p:.0%}: {imputed(comp, inc, p):+.3f}' for p in (*P_TERMINAL, 1.0)))


def grid(label, comp, base_all):
    n, mu = len(comp), mean(comp)
    k = sum(r['entry_open'] / r['atr'] for r in comp) / n
    s = sum(r['spy_atr'] for r in comp) / n
    print(f'\n=== C. Unobserved-hazard grid, {label}: n={n}, mean {mu:+.3f}; entry_open/ATR avg {k:.1f} (so -55% = {-0.55 * k:+.1f} ATR); SPY leg avg {s:+.2f}; all-event mean {base_all:+.3f} ===')
    print('h = extra wiped-out D1 events as a share of n | mean excess at p=30% / p=55%')
    for h in H_GRID:
        m = h * n
        print(f'  h={h:.0%} (m={m:.1f}): ' + ' / '.join(f'{(n * mu + m * (-p * k - s)) / (n + m):+.3f}' for p in P_TERMINAL))
    for tag, tgt in (('the all-event mean', base_all), ('zero', 0.0)):
        out = []
        for p in P_TERMINAL:
            x = -p * k - s
            m = n * (mu - tgt) / (tgt - x)
            out.append(f'p={p:.0%}: m={m:.1f} (h={m / n:.1%})')
        print(f'  to pull D1 to {tag} ({tgt:+.3f}): ' + '; '.join(out))


def spearman(a, b):
    import numpy as np
    if len(a) < 4:
        return float('nan')
    return float(np.corrcoef(rank_avg(a), rank_avg(b))[0, 1])


def dose_response(d1, rest, rates):
    print('\n=== D. Dose-response: D1 excess by entry year vs census no-price share ===')
    ys = sorted({r['entry'][:4] for r in d1 if r['status'] == 'complete'})
    tab = []
    for y in ys:
        a = [r for r in d1 if r['entry'][:4] == y and r['status'] == 'complete']
        b = [r for r in rest if r['entry'][:4] == y and r['status'] == 'complete']
        tab.append((y, len(a), mean(a), mean(a) - mean(b) if b else float('nan'), rates.get(y, float('nan'))))
    print('year | D1 n | D1 excess | D1 minus non-D1 | census no-price share')
    for y, n, m, g, p in tab:
        print(f'{y} | {n:3d} | {m:+.3f} | {g:+.3f} | {p:.1%}')
    use = [t for t in tab if t[1] >= 8 and t[4] == t[4] and t[3] == t[3]]
    print(f'years with >= 8 D1 events: {len(use)}; Spearman(D1 excess, missing share) {spearman([t[2] for t in use], [t[4] for t in use]):+.2f}; '
          f'Spearman(gap, missing share) {spearman([t[3] for t in use], [t[4] for t in use]):+.2f}  (survivorship bias predicts a POSITIVE link)')
    for lab, sel in (('2006-10', lambda y: y < '2011'), ('2011-20', lambda y: y >= '2011')):
        a = [r for r in d1 if sel(r['entry'][:4]) and r['status'] == 'complete']
        ps = [rates[y] for y in ys if sel(y) and y in rates]
        print(f'{lab}: D1 n={len(a)}, excess {mean(a):+.3f}, mean census share ' + (f'{sum(ps) / len(ps):.1%}' if ps else 'n/a'))


def run(events_json, year_dir, features, returns):
    import numpy as np
    from survivorship_check import census, year_rates
    _, _, status, _ = census(json.loads(Path(events_json).read_text()), sorted(Path(year_dir).glob('year_*.json')))
    rates, _ = year_rates(status)
    rows = load_all(features, returns)
    dev = sorted([r for r in rows if r['entry'] <= DEV_END], key=week_of)
    cut = d1_cut(dev)
    d1, comp, inc = hazard_table(dev, cut)
    allc = [r for r in dev if r['status'] == 'complete']
    print(f'\nD1 cut {cut:.2f} ATR; D1 complete n={len(comp)}, {mean(comp):+.3f} (Entry 36: -15.3, 255, +0.593); all complete dev n={len(allc)}, {mean(allc):+.3f} (Entry 28: 1,372, +0.154)')
    imputation_table(comp, inc)
    grid('development 2006-2020', comp, mean(allc))
    sub = [r for r in dev if r['entry'] >= '2011-01-01']
    cut2 = d1_cut(sub)
    comp2 = [r for r in sub if r['status'] == 'complete' and M in r and r[M] <= cut2]
    suball = [r for r in sub if r['status'] == 'complete']
    print(f'\nSUBSET entry >= 2011: cut {cut2:.2f}, D1 complete n={len(comp2)}, {mean(comp2):+.3f} (Entry 44: 175, +0.565); all complete n={len(suball)}, {mean(suball):+.3f}')
    grid('2011-2020 subset', comp2, mean(suball))
    rest = [r for r in dev if M in r and r[M] > cut]
    dose_response(d1, rest, rates)


def selftest():
    mk = lambda e, st, raw, ex, op=10.0, atr=0.7, spy=0.2: dict(entry=e, status=st, raw252=raw, excess_atr=ex, entry_open=op, atr=atr, spy_atr=spy, stock_atr=ex + spy, exit=e, sym='X', cik='1')
    comp = [mk('2012-01-0%d' % (1 + i % 9), 'complete', -20.0, 1.0 + (i % 3)) for i in range(20)]
    inc = [mk('2012-02-01', 'incomplete', -20.0, -1.0)]
    # imputation: -55% of open 10 at ATR 0.7 -> -7.857 ATR stock leg, minus spy 0.2
    x = -0.55 * 10 / 0.7 - 0.2
    want = (sum(r['excess_atr'] for r in comp) + x) / 21
    assert abs(imputed(comp, inc, 0.55) - want) < 1e-9
    assert abs(imputed(comp, [], 0.55) - mean(comp)) < 1e-9
    assert share(comp + inc) == '1/21 = 4.76%'
    # break-even identity: adding m events at x pulls the mean to the target
    n, mu = len(comp), mean(comp)
    k, s = 10 / 0.7, 0.2
    x2 = -0.55 * k - s
    m = n * (mu - 0.0) / (0.0 - x2)
    assert abs((n * mu + m * x2) / (n + m)) < 1e-9
    assert abs(spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) + 1.0) < 1e-9
    d1 = comp + inc
    hazard_table(d1, -15.0)
    imputation_table(comp, inc)
    grid('selftest', comp, 0.1)
    dose_response(d1, [mk('2012-03-01', 'complete', -5.0, 0.0)], {'2012': 0.1})
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        selftest()
    else:
        run(*sys.argv[1:5])
