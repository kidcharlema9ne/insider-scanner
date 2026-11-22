"""C45 (POST HOC, Michael 9 Nov 2026): size each trade by a CONTINUOUS function of how far the stock has fallen, instead of yes/no steps.

Michael: "I want it scaled to the edge. So do both drawdowns and find whatever the edge is to give it a score, and it can be a small amount relative to the edge, so
that we're not thinking, oh, it's got to be down 50% and missing trade because it's down 49%."  Both measures: (1) percent drop from the 12-month closing high
(dd252, a fraction), (2) 12-month fall in ATRs (fall = -raw252, floored at 0).

NEW CODE, PROVISIONAL.  Development entries only (D-068); no sealed entry is read; the 2026 pilot is not run.  Cohort, flags, per-trade paths, cost (0.10 ATR round trip,
Entry 89), 3 ATR stop and 42-session exit exactly as portfolio_sim.py (Entry 82/90; the paths come from run 42639575093).

DECLARED BEFORE RUNNING:
 A. Model (per era): excess_atr = a + b1*[no CEO and no CFO] + b2*[Nasdaq lagging] + b3*h(percent drop; k1, c1) + b4*h(ATR fall; k2, c2), fit by least squares,
    h(x; k, c) = min(max(x, k), c) - k  (zero up to k, rising in a straight line to c, flat after c).  excess_atr = the 21-session excess over SPY (Entry 28 returns).
    k and c are chosen on the TRAINING era only, by smallest in-era squared error on a fixed grid: percent drop k in {0.10,0.20,0.30,0.40,0.50}, c in {0.60,0.70,0.80,0.90};
    ATR fall k in {0,3,5,8,10,12}, c in {15,20,25,30,40} (c > k).  Negative fitted slopes are set to zero (a layer never shrinks a position below the base).
 B. Size: U = min(CAP, 1 + MULT * (b1*R1 + b2*N + b3*h1 + b4*h2)), base = 1.0U = 0.1% of equity per 1 ATR.  MULT = 2.0 (Entry 78's 0.5 selection haircut / 0.25 ATR per 1U),
    shown also at 1.0 and 3.0 (the haircut at 0.25 and 0.75).  CAP = 4.0U.  No per-term reliability weights here (Entry 78 used them): the same rule is applied to every model
    so the comparison is like for like.
 C. Models compared (each fitted the same way): STEP (the two fall layers as the old yes/no: down 50%+ from the 12-month high; down 15+ ATR); GRADIENT both measures;
    GRADIENT ATR fall only; GRADIENT percent drop only.  The last three keep the no-CEO/CFO and Nasdaq-lagging layers; FLAT = 1.0U for every trade (reference).
 D. Out-of-era test (the only honest one inside the development years): fit on 2006-2010 and size 2011-2020 trades; fit on 2011-2020 and size 2006-2010 trades.  For each:
    Pearson and Spearman correlation of predicted layer excess with realised excess, mean excess of the top third vs the bottom third of predictions, and the $100,000
    portfolio (3 ATR stop, 42 sessions, 0.10 ATR) with max drawdown, Sharpe, Sortino, Calmar, CAGR.  SPY over the same dates beside every table (D-053).
 E. PASS RULE (declared now): GRADIENT (both measures) beats STEP on Sharpe AND Calmar in BOTH out-of-era portfolios, and on out-of-era Pearson in both eras.  Anything less
    is reported as not shown.  Ties and one-era wins are not a pass.
 F. Also printed: the full-development fit (parameters, add-on table by depth, in-sample portfolio) as the working proposal.  It is in-sample and labelled so.
Cautions written in advance: every model is fitted on post hoc development data; about half the deep-fall trades are 2008, 2009 and 2020; the two eras are not independent
of those crashes; survivorship (Entry 65) is not in any number; the portfolio equity curve is one path.

Usage:  python continuous_sizing.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER PATH_FOLDER
        python continuous_sizing.py --selftest
"""
import itertools, math, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import portfolio_sim as ps

MULT = 2.0
CAP = 4.0
ERA_SPLIT = '2011-01-01'
DD_K, DD_C = (0.10, 0.20, 0.30, 0.40, 0.50), (0.60, 0.70, 0.80, 0.90)
FALL_K, FALL_C = (0, 3, 5, 8, 10, 12), (15, 20, 25, 30, 40)
STEP_DD, STEP_FALL = 0.50, 15.0


def h(x, k, c):
    return min(max(x, k), c) - k


def fall_of(r):
    return max(0.0, -r['raw252'])


def design(rows, model, p):
    """Feature columns for a model (without the intercept)."""
    cols = []
    for r in rows:
        f = [1.0 if r['R1'] else 0.0, 1.0 if r['N'] else 0.0]
        if model == 'step':
            f += [1.0 if r['dd252'] >= STEP_DD else 0.0, 1.0 if r['raw252'] <= -STEP_FALL else 0.0]
        else:
            if model in ('both', 'pct'):
                f.append(h(r['dd252'], p['k1'], p['c1']))
            if model in ('both', 'atr'):
                f.append(h(fall_of(r), p['k2'], p['c2']))
        cols.append(f)
    return np.asarray(cols)


def ols(X, y):
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    sse = float(np.sum((A @ beta - y) ** 2))
    return beta, sse


def fit(train, model):
    y = np.asarray([r['excess_atr'] for r in train])
    if model == 'step':
        beta, sse = ols(design(train, 'step', {}), y)
        return {'model': model, 'beta': beta, 'p': {}, 'sse': sse}
    grids = {'both': list(itertools.product(DD_K, DD_C, FALL_K, FALL_C)),
             'pct': [(a, b, 0, 15) for a, b in itertools.product(DD_K, DD_C)],
             'atr': [(0.1, 0.6, a, b) for a, b in itertools.product(FALL_K, FALL_C)]}[model]
    best = None
    for k1, c1, k2, c2 in grids:
        if c1 <= k1 or c2 <= k2:
            continue
        p = {'k1': k1, 'c1': c1, 'k2': k2, 'c2': c2}
        beta, sse = ols(design(train, model, p), y)
        if best is None or sse < best['sse'] - 1e-12:
            best = {'model': model, 'beta': beta, 'p': p, 'sse': sse}
    return best


def layer_excess(fit_, rows):
    """Predicted layer excess (no intercept), negative slopes set to zero."""
    X = design(rows, fit_['model'], fit_['p'])
    b = np.maximum(fit_['beta'][1:], 0.0)
    return X @ b


def sizes(fit_, rows, mult=MULT):
    return [min(CAP, 1.0 + mult * float(v)) for v in layer_excess(fit_, rows)]


def describe(fit_):
    m, b, p = fit_['model'], fit_['beta'], fit_['p']
    s = f'{m}: intercept {b[0]:+.3f}, no CEO/CFO {b[1]:+.3f}, Nasdaq lagging {b[2]:+.3f}'
    if m == 'step':
        return s + f', down {STEP_DD:.0%}+ from the 12-month high {b[3]:+.3f}, down {STEP_FALL:.0f}+ ATR {b[4]:+.3f}'
    i = 3
    if m in ('both', 'pct'):
        s += f', percent drop: starts {p["k1"]:.0%}, flat from {p["c1"]:.0%}, {b[i] * 0.1:+.3f} ATR per 10 points'
        i += 1
    if m in ('both', 'atr'):
        s += f', ATR fall: starts {p["k2"]} ATR, flat from {p["c2"]} ATR, {b[i]:+.3f} ATR per 1 ATR'
    return s


def corr_stats(fit_, test):
    pred = layer_excess(fit_, test)
    y = np.asarray([r['excess_atr'] for r in test])
    pear = float(np.corrcoef(pred, y)[0, 1]) if pred.std() > 0 else float('nan')
    rk = lambda v: np.argsort(np.argsort(v, kind='stable'), kind='stable').astype(float)
    spear = float(np.corrcoef(rk(pred), rk(y))[0, 1]) if pred.std() > 0 else float('nan')
    order = np.argsort(pred, kind='stable')
    n3 = len(test) // 3
    return pear, spear, float(y[order[-n3:]].mean()), float(y[order[:n3]].mean())


def run_port(trades, spy, **kw):
    cal_all = sorted(spy)
    d_first = min(t['entry'] for t in trades)
    d_last = max(t['exit_date'] for t in trades)
    prior = [d for d in cal_all if d < d_first]
    d0 = prior[-1] if prior else cal_all[0]
    cal = [d for d in cal_all if d_first <= d <= d_last]
    curve, recs, cnt = ps.simulate(trades, cal, **kw)
    st = ps.curve_stats(curve, ps.START)
    bs = ps.curve_stats(ps.spy_curve(spy, cal, d0, ps.START), ps.START)
    return st, bs, len(recs)


def with_sizes(trades, rowmap, fit_, mult=MULT):
    rows = [rowmap[(t['entry'], t['sym'])] for t in trades]
    us = sizes(fit_, rows, mult) if fit_ else [1.0] * len(trades)
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
    dv = ps.load_dv_soft(dv_folder)
    trades, miss, _ = ps.build_trades(cohort, sim, dv, ps.add_on_u(), 'stop')
    rowmap = {(r['entry'], r['sym']): r for r in cohort}
    report(cohort, trades, rowmap, spy)


def report(cohort, trades, rowmap, spy):
    eras = {'2006-2010': lambda e: e < ERA_SPLIT, '2011-2020': lambda e: e >= ERA_SPLIT}
    coh = {k: [r for r in cohort if f(r['entry'])] for k, f in eras.items()}
    trd = {k: [t for t in trades if f(t['entry'])] for k, f in eras.items()}
    print(f'cohort {len(cohort)} (2006-2010 {len(coh["2006-2010"])}, 2011-2020 {len(coh["2011-2020"])}); tradable paths {len(trades)}; '
          f'base 1.0U = {ps.BASE_PCT}% of equity per 1 ATR; cost {ps.COST} ATR round trip; 3 ATR stop, 42 sessions; MULT {MULT}, cap {CAP}U')
    models = [('step', 'STEP (old yes/no layers)'), ('both', 'GRADIENT both measures'), ('atr', 'GRADIENT ATR fall only'), ('pct', 'GRADIENT percent drop only')]
    verdict = {}
    pairs = [('2006-2010', '2011-2020'), ('2011-2020', '2006-2010')]
    for train_era, test_era in pairs:
        print(f'\n=== OUT OF ERA: fit on {train_era} (n={len(coh[train_era])}), size and test on {test_era} (n={len(coh[test_era])}) ===')
        fits = {m: fit(coh[train_era], m) for m, _ in models}
        for m, label in models:
            print('  fit  ' + describe(fits[m]))
        print('  prediction quality on the test era (layer excess vs realised excess, ATR):')
        for m, label in models:
            pe, sp, top, bot = corr_stats(fits[m], coh[test_era])
            verdict[(train_era, m, 'pear')] = pe
            print(f'    {label:28s} Pearson {pe:+.3f}  Spearman {sp:+.3f}  top third mean {top:+.3f}  bottom third mean {bot:+.3f}')
        print(f'  portfolio on {test_era} ($100,000, 3 ATR stop, 42 sessions, 0.10 ATR; SPY same dates beside):')
        st, bs, n = run_port(with_sizes(trd[test_era], rowmap, None), spy, flat=True)
        print(ps.fmt_stats('FLAT 1.0U', st, f'  trades {n}'))
        for m, label in models:
            for mult in ((MULT,) if m != 'both' else (1.0, MULT, 3.0)):
                tt = with_sizes(trd[test_era], rowmap, fits[m], mult)
                st, bs, n = run_port(tt, spy)
                tag = label + ('' if mult == MULT else f' x{mult:g}')
                print(ps.fmt_stats(tag[:26], st, f'  trades {n}  max U {max(t["U"] for t in tt):.2f}  mean U {statistics.fmean(t["U"] for t in tt):.2f}'))
                if mult == MULT:
                    verdict[(train_era, m, 'sharpe')], verdict[(train_era, m, 'calmar')] = st['sharpe'], st['calmar']
        print(ps.fmt_stats('SPY buy and hold', bs))
    ok = all(verdict[(a, 'both', k)] > verdict[(a, 'step', k)] for a, _ in pairs for k in ('sharpe', 'calmar', 'pear'))
    print('\n=== PASS RULE (declared): GRADIENT both measures beats STEP on Sharpe, Calmar and Pearson in BOTH out-of-era tests ===')
    for a, b in pairs:
        print(f'  fit {a} -> test {b}: ' + '; '.join(f'{k} {verdict[(a, "both", k)]:+.3f} vs step {verdict[(a, "step", k)]:+.3f}' for k in ('sharpe', 'calmar', 'pear')))
    print('  RESULT: ' + ('PASS' if ok else 'NOT SHOWN (not a pass in both eras on all three)'))

    print('\n=== FULL DEVELOPMENT FIT (IN-SAMPLE; the working proposal, not a test) ===')
    full = {m: fit(cohort, m) for m, _ in models}
    for m, _ in models:
        print('  fit  ' + describe(full[m]))
    g = full['both']
    b, p = g['beta'], g['p']
    print('  add-on size in U (above the 1.0U base) from the fall layers alone, both measures at the same depth is NOT additive here; each measure by itself:')
    print('    percent drop from the 12-month high: ' + ', '.join(f'{x:.0%}: {MULT * max(b[3], 0) * h(x, p["k1"], p["c1"]):+.2f}U' for x in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)))
    print('    12-month fall in ATR:                ' + ', '.join(f'{x:g}: {MULT * max(b[4], 0) * h(x, p["k2"], p["c2"]):+.2f}U' for x in (5, 8, 10, 12, 15, 20, 25, 30)))
    print('  in-sample portfolio, all development years (SPY beside):')
    st, bs, n = run_port(with_sizes(trades, rowmap, None), spy, flat=True)
    print(ps.fmt_stats('FLAT 1.0U', st, f'  trades {n}'))
    for m, label in models:
        tt = with_sizes(trades, rowmap, full[m])
        st, bs, n = run_port(tt, spy)
        print(ps.fmt_stats(label[:26], st, f'  trades {n}  max U {max(t["U"] for t in tt):.2f}  mean U {statistics.fmean(t["U"] for t in tt):.2f}'))
    print(ps.fmt_stats('SPY buy and hold', bs))
    print('  Caveats: in-sample; sizes fitted on the same trades they size; the two eras share the 2008-09 and 2020 crashes; survivorship unresolved (Entry 65).')


def selftest():
    rng = np.random.default_rng(1)
    rows = []
    for i in range(600):
        dd_, fall = rng.uniform(0, 0.9), rng.uniform(0, 30)
        r1, n = bool(rng.integers(0, 2)), bool(rng.integers(0, 2))
        ex = 0.1 + 0.1 * r1 + 0.4 * n + 3.0 * h(dd_, 0.4, 0.8) + 0.04 * h(fall, 8, 25) + rng.normal(0, 0.3)
        rows.append({'R1': r1, 'N': n, 'dd252': dd_, 'raw252': -fall, 'excess_atr': ex, 'entry': '2008-01-01'})
    f = fit(rows, 'both')
    assert f['p']['k1'] in (0.30, 0.40) and f['p']['c1'] in (0.70, 0.80), f['p']
    assert f['p']['k2'] in (5, 8) and f['p']['c2'] in (20, 25, 30), f['p']
    assert abs(f['beta'][2] - 0.4) < 0.1
    s = sizes(f, rows)
    assert min(s) >= 1.0 and max(s) <= CAP
    st = fit(rows, 'step')
    assert corr_stats(f, rows)[0] > corr_stats(st, rows)[0]
    assert h(0.45, 0.4, 0.8) == 0.45 - 0.4 and h(0.2, 0.4, 0.8) == 0 and abs(h(0.9, 0.4, 0.8) - 0.4) < 1e-12
    print('continuous_sizing selftest ok: hinge, fit recovers the planted knots, sizes within [1, cap], gradient beats step on planted gradient data')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    assert sys.argv[1] == 'scan'
    scan(*sys.argv[2:])
