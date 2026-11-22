"""C46 (POST HOC, Michael 9 Nov 2026): which ATR-based fall measures belong in the continuous size - 12-month change, 6-month change, distance below the 12-month high.

Michael: "keep the ATR fall only" (after Entry 91 showed the percent drop adds nothing), then "where are you taking the ATR from ... did you do 3-month and 6-month ATR drops? Let's look at
those." / "Yeah, try it" (the three-layer out-of-era test).  The 3-month fall had no signal on its own (Entry 36: Spearman -0.008, chance 66%), so it is not a layer here.

NEW CODE, PROVISIONAL.  Same engine, cohort, paths, cost (0.10 ATR round trip), 3 ATR stop, 42 sessions, base 1.0U = 0.1% of equity per 1 ATR, MULT 2.0, cap 4.0U, hinge form,
negative slopes set to zero, era split and out-of-era procedure as continuous_sizing.py (C45, Entry 91).  Development entries only (D-068); no sealed entry is read.

DECLARED BEFORE RUNNING:
 A. Layers (each a hinge h(x; k, c) = min(max(x, k), c) - k of the fall depth in entry-ATR units; ATR = mean true range of the 14 sessions BEFORE entry):
      twelve = max(0, -raw252): close 252 sessions before entry to the last close before entry; k in {0,3,5,8,10,12}, c in {15,20,25,30,40}
      six    = max(0, -raw126): same over 126 sessions;                                         k in {0,2,4,6,8,10},  c in {10,15,20,25,30}
      high   = max(0, -hi252): last close below the highest close of the previous 252 sessions; k in {0,3,5,8,10,12}, c in {15,20,25,30,40}
    A missing feature value (coverage 1,329 raw126; 1,291 hi252 of 1,372) counts as zero depth (no add-on); counts of missing values are printed.  All models also carry the
    no-CEO/CFO and Nasdaq-lagging layers.
 B. Models: twelve only (the working choice, the baseline); high only; six only; twelve + six; twelve + high; all three.  k and c per layer chosen on the TRAINING era by smallest
    squared error over the full grid.
 C. Out-of-era tests exactly as C45: fit 2006-2010 -> size 2011-2020, fit 2011-2020 -> size 2006-2010; Pearson and Spearman of predicted layer excess vs realised excess; the $100,000
    portfolio with max drawdown, Sharpe, Sortino, Calmar, CAGR; SPY and flat 1.0U beside every table.
 D. PASS RULE (declared now): a model other than twelve-only EARNS A PLACE only if it beats twelve-only on Sharpe AND Calmar in BOTH out-of-era portfolios AND on Pearson in both eras.
    Otherwise twelve-only stays.  Ties and one-era wins are not a pass.  Six comparisons on one set of events: this is one family, not six confirmations.
 E. Also printed: full-development fit (IN-SAMPLE, labelled) with parameters and add-on tables, and the in-sample portfolio.
Cautions written in advance: post hoc; the three measures are highly correlated; about half the deep-fall trades come from 2008, 2009 and 2020; the eras share those crashes; survivorship
(Entry 65) is not in any number; a grid of about 27,000 fits on one era is easy to overfit, which is what the out-of-era test is for.

Usage:  python continuous_sizing_layers.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER PATH_FOLDER
        python continuous_sizing_layers.py --selftest
"""
import itertools, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import portfolio_sim as ps
import continuous_sizing as cs

LAYERS = {
    'twelve': dict(key='raw252', K=(0, 3, 5, 8, 10, 12), C=(15, 20, 25, 30, 40), label='12-month fall'),
    'six': dict(key='raw126', K=(0, 2, 4, 6, 8, 10), C=(10, 15, 20, 25, 30), label='6-month fall'),
    'high': dict(key='hi252', K=(0, 3, 5, 8, 10, 12), C=(15, 20, 25, 30, 40), label='distance below the 12-month high'),
}
MODELS = [('twelve',), ('high',), ('six',), ('twelve', 'six'), ('twelve', 'high'), ('twelve', 'six', 'high')]
NAMES = {('twelve',): '12-month fall only', ('high',): 'below-12-month-high only', ('six',): '6-month fall only',
         ('twelve', 'six'): '12-month + 6-month', ('twelve', 'high'): '12-month + below-high', ('twelve', 'six', 'high'): 'all three'}


def depth(r, layer):
    v = r.get(LAYERS[layer]['key'])
    return 0.0 if v is None else max(0.0, -v)


def base_cols(rows):
    return np.asarray([[1.0 if r['R1'] else 0.0, 1.0 if r['N'] else 0.0] for r in rows])


def hinge_col(rows, layer, k, c):
    return np.asarray([cs.h(depth(r, layer), k, c) for r in rows])


def fit(train, names):
    y = np.asarray([r['excess_atr'] for r in train])
    B = base_cols(train)
    cols = {nm: {(k, c): hinge_col(train, nm, k, c) for k in LAYERS[nm]['K'] for c in LAYERS[nm]['C'] if c > k} for nm in names}
    best = None
    for combo in itertools.product(*[list(cols[nm].items()) for nm in names]):
        X = np.column_stack([np.ones(len(train)), B] + [col for (_, col) in combo])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        sse = float(np.sum((X @ beta - y) ** 2))
        if best is None or sse < best['sse'] - 1e-12:
            best = {'names': names, 'beta': beta, 'p': {nm: kc for nm, (kc, _) in zip(names, combo)}, 'sse': sse}
    return best


def layer_excess(f, rows):
    B = base_cols(rows)
    cols = [hinge_col(rows, nm, *f['p'][nm]) for nm in f['names']]
    X = np.column_stack([B] + cols)
    return X @ np.maximum(f['beta'][1:], 0.0)


def sizes(f, rows, mult=cs.MULT):
    return [min(cs.CAP, 1.0 + mult * float(v)) for v in layer_excess(f, rows)]


def describe(f):
    b = f['beta']
    s = f'{NAMES[f["names"]]}: intercept {b[0]:+.3f}, no CEO/CFO {b[1]:+.3f}, Nasdaq lagging {b[2]:+.3f}'
    for i, nm in enumerate(f['names']):
        k, c = f['p'][nm]
        s += f'; {LAYERS[nm]["label"]}: starts {k} ATR, flat from {c} ATR, {b[3 + i]:+.3f} ATR per 1 ATR'
    return s


def corr(f, test):
    pred = layer_excess(f, test)
    y = np.asarray([r['excess_atr'] for r in test])
    pe = float(np.corrcoef(pred, y)[0, 1]) if pred.std() > 0 else float('nan')
    rk = lambda v: np.argsort(np.argsort(v, kind='stable'), kind='stable').astype(float)
    sp = float(np.corrcoef(rk(pred), rk(y))[0, 1]) if pred.std() > 0 else float('nan')
    return pe, sp


def with_sizes(trades, rowmap, f, mult=cs.MULT):
    rows = [rowmap[(t['entry'], t['sym'])] for t in trades]
    us = sizes(f, rows, mult) if f else [1.0] * len(trades)
    return [{**t, 'U': u} for t, u in zip(trades, us)]


def scan(events, years, decl, regime, ret, dd_folder, dv_folder, path_folder):
    import drawdown_scan as dd
    import score_scan as ss
    import deepfall_2x2 as d2
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, _ = dd.load_dd(dd_folder, dev0)
    cohort = [r for r in dev if 'dd252' in r]
    for r in cohort:
        d2.flags(r)
        assert r['entry'] <= ps.DEV_END
    sim, spy = ps.load_paths(path_folder)
    trades, miss, _ = ps.build_trades(cohort, sim, ps.load_dv_soft(dv_folder), ps.add_on_u(), 'stop')
    rowmap = {(r['entry'], r['sym']): r for r in cohort}
    report(cohort, trades, rowmap, spy)


def report(cohort, trades, rowmap, spy):
    print(f'cohort {len(cohort)}; missing feature values (counted as zero depth): ' +
          ', '.join(f'{LAYERS[n]["label"]} {sum(r.get(LAYERS[n]["key"]) is None for r in cohort)}' for n in LAYERS))
    print(f'base 1.0U = {ps.BASE_PCT}% of equity per 1 ATR; cost {ps.COST} ATR round trip; 3 ATR stop, 42 sessions; MULT {cs.MULT}, cap {cs.CAP}U')
    eras = {'2006-2010': lambda e: e < cs.ERA_SPLIT, '2011-2020': lambda e: e >= cs.ERA_SPLIT}
    coh = {k: [r for r in cohort if f(r['entry'])] for k, f in eras.items()}
    trd = {k: [t for t in trades if f(t['entry'])] for k, f in eras.items()}
    pairs = [('2006-2010', '2011-2020'), ('2011-2020', '2006-2010')]
    verdict = {}
    for a, b in pairs:
        print(f'\n=== OUT OF ERA: fit on {a} (n={len(coh[a])}), size and test on {b} (n={len(coh[b])}) ===')
        fits = {m: fit(coh[a], m) for m in MODELS}
        for m in MODELS:
            print('  fit  ' + describe(fits[m]))
        print('  prediction quality on the test era (layer excess vs realised excess, ATR):')
        for m in MODELS:
            pe, sp = corr(fits[m], coh[b])
            verdict[(a, m, 'pear')] = pe
            print(f'    {NAMES[m]:26s} Pearson {pe:+.3f}  Spearman {sp:+.3f}')
        print(f'  portfolio on {b} ($100,000, 3 ATR stop, 42 sessions, 0.10 ATR; SPY same dates beside):')
        st, bs, n = cs.run_port(with_sizes(trd[b], rowmap, None), spy, flat=True)
        print(ps.fmt_stats('FLAT 1.0U', st, f'  trades {n}'))
        for m in MODELS:
            tt = with_sizes(trd[b], rowmap, fits[m])
            st, bs, n = cs.run_port(tt, spy)
            verdict[(a, m, 'sharpe')], verdict[(a, m, 'calmar')] = st['sharpe'], st['calmar']
            print(ps.fmt_stats(NAMES[m][:26], st, f'  trades {n}  max U {max(t["U"] for t in tt):.2f}  mean U {statistics.fmean(t["U"] for t in tt):.2f}'))
        print(ps.fmt_stats('SPY buy and hold', bs))
    print('\n=== PASS RULE (declared): a model earns a place only if it beats the 12-month fall alone on Sharpe, Calmar and Pearson in BOTH out-of-era tests ===')
    base = ('twelve',)
    for m in MODELS[1:]:
        wins = [verdict[(a, m, k)] > verdict[(a, base, k)] for a, _ in pairs for k in ('sharpe', 'calmar', 'pear')]
        print(f'  {NAMES[m]:26s} ' + '; '.join(f'fit {a[:4]}: Sharpe {verdict[(a, m, "sharpe")]:.3f}/{verdict[(a, base, "sharpe")]:.3f}, Calmar {verdict[(a, m, "calmar")]:.3f}/{verdict[(a, base, "calmar")]:.3f}, '
                                                    f'Pearson {verdict[(a, m, "pear")]:+.3f}/{verdict[(a, base, "pear")]:+.3f}' for a, _ in pairs) + f'  -> {"PASS" if all(wins) else "not shown"}')
    print('  (each cell: model / 12-month alone)')

    print('\n=== FULL DEVELOPMENT FIT (IN-SAMPLE; not a test) ===')
    full = {m: fit(cohort, m) for m in MODELS}
    for m in MODELS:
        print('  fit  ' + describe(full[m]))
    for nm in ('twelve',):
        f = full[(nm,)]
        k, c = f['p'][nm]
        print(f'  12-month fall add-on in U above 1.0U (layer alone): ' + ', '.join(f'{x:g} ATR: {cs.MULT * max(f["beta"][3], 0) * cs.h(x, k, c):+.2f}U' for x in (5, 8, 10, 12, 15, 20, 25, 30)))
    print('  in-sample portfolio, all development years (SPY beside):')
    st, bs, n = cs.run_port(with_sizes(trades, rowmap, None), spy, flat=True)
    print(ps.fmt_stats('FLAT 1.0U', st, f'  trades {n}'))
    for m in MODELS:
        tt = with_sizes(trades, rowmap, full[m])
        st, bs, n = cs.run_port(tt, spy)
        print(ps.fmt_stats(NAMES[m][:26], st, f'  trades {n}  max U {max(t["U"] for t in tt):.2f}  mean U {statistics.fmean(t["U"] for t in tt):.2f}'))
    print(ps.fmt_stats('SPY buy and hold', bs))
    print('  Caveats: in-sample; the eras share the 2008-09 and 2020 crashes; survivorship unresolved (Entry 65).')


def selftest():
    rng = np.random.default_rng(2)
    rows = []
    for i in range(700):
        t12, t6 = rng.uniform(0, 30), rng.uniform(0, 25)
        r1, n = bool(rng.integers(0, 2)), bool(rng.integers(0, 2))
        ex = 0.1 + 0.1 * r1 + 0.4 * n + 0.05 * cs.h(t12, 8, 25) + rng.normal(0, 0.3)
        rows.append({'R1': r1, 'N': n, 'raw252': -t12, 'raw126': -t6, 'hi252': -rng.uniform(0, 30), 'excess_atr': ex, 'entry': '2008-01-01'})
    rows[0]['raw126'] = None
    f = fit(rows, ('twelve',))
    assert f['p']['twelve'][0] in (5, 8, 10) and f['p']['twelve'][1] in (20, 25, 30), f['p']
    f2 = fit(rows, ('twelve', 'six'))
    assert f2['beta'][4] < 0.02, f2['beta']            # the planted noise layer gets about zero weight
    s = sizes(f, rows)
    assert min(s) >= 1.0 and max(s) <= cs.CAP
    assert depth(rows[0], 'six') == 0.0
    print('continuous_sizing_layers selftest ok: grid fit recovers the planted knot, noise layer gets about zero, missing values count as zero, sizes within [1, cap]')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    assert sys.argv[1] == 'scan'
    scan(*sys.argv[2:])
