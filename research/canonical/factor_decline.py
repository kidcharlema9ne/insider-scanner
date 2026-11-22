"""Candidates C8 / C9 / C1 on the primary set: how far the stock (and SPY) had fallen over several look-back windows before entry.

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule. The 21-session
returns are the Entry 28 results (run 42490748366); this script only adds features measured BEFORE entry, from sessions strictly
earlier than the entry session (the last completed session is entry index - 1). Lookback prices are read from the archive
(entries in January need the year before); no price after an entry is used here, and no returns are computed here.

Features (entry ATR = mean true range of the 14 completed sessions before entry, as in refined_baseline.py):
  rawW   stock close(last) minus close(W sessions earlier), divided by entry ATR            ("stock down X ATR over W sessions")
  relW   rawW minus SPY's move over the same sessions restated in the stock's ATR units     (stock-specific decline)
  spyW   SPY's own percent change over the same W sessions                                   (market regime, C1)
  hiW    (last close - highest close in the last W sessions) / entry ATR, <= 0               (distance below the recent high)
  dnW    share of the last W sessions that closed below the prior close                      (decline duration, C9)
  W in 5, 21, 63, 126, 252 sessions (1 week, 1, 3, 6, 12 months); hiW for 21..252; dnW for 21 and 63.
A reference close missing on the exact session is replaced by the nearest earlier one within 3 sessions; otherwise the feature is blank.

Menu declared before the run (the chance test covers exactly these): 21 measures
  raw5 raw21 raw63 raw126 raw252 | rel5 rel21 rel63 rel126 rel252 | hi21 hi63 hi126 hi252 | dn21 dn63 | spy5 spy21 spy63 spy126 spy252
each with two statistics: (a) Spearman rank correlation of excess with the measure, (b) 'smile' = mean excess of the lowest and
highest fifths minus mean excess of the middle three fifths. 42 statistics. Quintiles: Q1 = lowest value of the measure.
Descriptive only (not in the chance menu): quintile tables with and without the three large episodes, fixed ATR bands for raw21 and
raw63, stock-below/above-median by SPY-up/down crossings for raw and rel, the 2026 pilot split by the development cut points.

Usage:  python factor_decline.py year YEAR --primary FILE --out FILE   |   summary FEATURES_FOLDER RETURNS_FOLDER   |   --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, load_span, quarter, true_range

WINDOWS = (5, 21, 63, 126, 252)
HI_WINDOWS = (21, 63, 126, 252)
DN_WINDOWS = (21, 63)
SEED = 20261108
MEASURES = ([f'raw{w}' for w in WINDOWS] + [f'rel{w}' for w in WINDOWS] + [f'hi{w}' for w in HI_WINDOWS]
            + [f'dn{w}' for w in DN_WINDOWS] + [f'spy{w}' for w in WINDOWS])
EXPECT_DEV = 1372            # Entry 28
EXPECT_MEAN = 0.154


# ------------------------------------------------------------------ features
def features(dates, stock, spy, entry, back=3):
    """dates: sorted session dates; stock, spy: {date: (open, high, low, close)}. Uses only sessions before `entry`."""
    assert_allowed(entry)
    i = bisect_left(dates, entry)
    if i >= len(dates) or dates[i] != entry:
        return {'status': 'entry_not_session'}
    if i < ATR_BARS + 1:
        return {'status': 'atr_missing'}
    win = dates[i - ATR_BARS - 1:i]
    if any(d not in stock for d in win) or entry not in stock:
        return {'status': 'atr_missing'}
    atr = sum(true_range(stock[win[k]], stock[win[k - 1]][3]) for k in range(1, len(win))) / ATR_BARS
    if atr <= 0:
        return {'status': 'atr_missing'}
    last_d = dates[i - 1]
    if last_d not in stock:
        return {'status': 'last_missing'}
    scale = stock[entry][0] / atr
    last = stock[last_d][3]
    spy_last = spy.get(last_d)
    out = {'status': 'ok', 'atr': atr}

    def ref_close(series, idx):
        for k in range(back + 1):
            if idx - k < 0:
                return None
            b = series.get(dates[idx - k])
            if b:
                return b[3]
        return None
    for W in WINDOWS:
        j = i - 1 - W
        if j < 0:
            continue
        rs, rp = ref_close(stock, j), ref_close(spy, j)
        if rs:
            out[f'raw{W}'] = (last - rs) / atr
            out[f'pct{W}'] = last / rs - 1
        if rp and spy_last:
            sp = spy_last[3] / rp - 1
            out[f'spy{W}'] = sp
            if rs:
                out[f'rel{W}'] = (last - rs) / atr - sp * scale
    for W in HI_WINDOWS:
        if i - W < 0:
            continue
        cl = [stock[d][3] for d in dates[i - W:i] if d in stock]
        if len(cl) >= 0.8 * W:
            out[f'hi{W}'] = (last - max(cl)) / atr
    for W in DN_WINDOWS:
        if i - W - 1 < 0:
            continue
        downs = valid = 0
        for k in range(i - W, i):
            a, b = stock.get(dates[k - 1]), stock.get(dates[k])
            if a and b:
                valid += 1
                downs += b[3] < a[3]
        if valid >= 0.8 * W:
            out[f'dn{W}'] = downs / valid
    return out


def year_job(year, primary_path, out):
    from r2_storage import client
    from archive_coverage_audit import DELISTED
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year - 1, year], want, 30, 0)
        spy_bars, _ = load_span(s3, 'etf', [year - 1, year], {'SPY'}, 30, 0)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded (incl. {year - 1}), SPY bars {len(spy)}')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = features(dates, series, spy, e['entry'])
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))) + '; coverage ' +
          ', '.join(f'{m} {sum(m in r for r in rows)}' for m in MEASURES if rows))


# ------------------------------------------------------------------ statistics (numpy)
def week_of(r):
    return date.fromisoformat(r['entry']).isocalendar()[:2]


def rank_avg(x):
    import numpy as np
    x = np.asarray(x, dtype=float)
    order = x.argsort(kind='mergesort')
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    return (np.bincount(inv, weights=r) / counts)[inv]


def prep(dev):
    """Per measure: subset indices (into week-sorted dev), centred ranks of x, quintile labels, smile mask."""
    import numpy as np
    info = {}
    for m in MEASURES:
        idx = np.array([k for k, r in enumerate(dev) if m in r], dtype=int)
        if len(idx) < 50:
            continue
        x = np.array([dev[k][m] for k in idx])
        rx = rank_avg(x)
        rxc = rx - rx.mean()
        cuts = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
        lab = np.searchsorted(cuts, x, side='right')
        info[m] = {'idx': idx, 'x': x, 'rxc': rxc, 'rxn': float(np.sqrt((rxc ** 2).sum())), 'cuts': cuts, 'lab': lab,
                   'ext': (lab == 0) | (lab == 4), 'n': len(idx), 'renorm': float(np.sqrt(((np.arange(len(idx)) - (len(idx) - 1) / 2) ** 2).sum()))}
    return info


def stat_vector(info, e):
    """e: excess in week-sorted dev order. Returns {(measure, 'rho'|'smile'): value}."""
    import numpy as np
    out = {}
    for m, d in info.items():
        es = e[d['idx']]
        order = es.argsort()
        re = np.empty(len(es))
        re[order] = np.arange(len(es), dtype=float)
        re -= re.mean()
        out[(m, 'rho')] = float(d['rxc'] @ re / (d['rxn'] * d['renorm'])) if d['rxn'] > 0 else 0.0
        a, b = es[d['ext']], es[~d['ext']]
        out[(m, 'smile')] = float(a.mean() - b.mean()) if len(a) and len(b) else 0.0
    return out


def perm_test(dev, info, draws=10000):
    import numpy as np
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in dev}))}
    wi = np.array([wk[week_of(r)] for r in dev])
    ex = np.array([r['excess_atr'] for r in dev])
    obs = stat_vector(info, ex)
    keys = list(obs)
    rng = np.random.default_rng(SEED)
    sim = np.empty((draws, len(keys)))
    for k in range(draws):
        order = np.lexsort((rng.random(len(dev)), wi))
        d = stat_vector(info, ex[order])
        sim[k] = [abs(d[key]) for key in keys]
    srt = np.sort(sim, axis=0)
    obs_abs = np.array([abs(obs[key]) for key in keys])
    p1 = np.array([1.0 - np.searchsorted(srt[:, c], obs_abs[c] - 1e-12, side='left') / draws for c in range(len(keys))])
    pmat = np.empty_like(sim)
    for c in range(len(keys)):
        pmat[:, c] = 1.0 - np.searchsorted(srt[:, c], sim[:, c] - 1e-12, side='left') / draws
    best = float((pmat.min(axis=1) <= p1.min() + 1e-12).mean())
    return obs, dict(zip(keys, p1)), best, float(p1.min()), keys


def mean(rs):
    return statistics.fmean(r['excess_atr'] for r in rs) if rs else float('nan')


def cell(rs):
    return f'{mean(rs):+.3f} (n={len(rs)}, {len({week_of(r) for r in rs})}w)' if rs else 'n=0'


def spearman(rows, m, y='excess_atr'):
    import numpy as np
    sub = [r for r in rows if m in r and y in r]
    if len(sub) < 20:
        return float('nan'), len(sub)
    a, b = rank_avg([r[m] for r in sub]), rank_avg([r[y] for r in sub])
    return float(np.corrcoef(a, b)[0, 1]), len(sub)


def quintile_line(rows, m, cuts):
    import numpy as np
    sub = [r for r in rows if m in r]
    lab = np.searchsorted(cuts, [r[m] for r in sub], side='right')
    return [[r for r, l in zip(sub, lab) if l == q] for q in range(5)]


def load(features_folder, returns_folder):
    feats = {}
    for p in sorted(Path(features_folder).glob('decline_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            feats[(r['cik'], r['sym'], r['entry'])] = r
    rows, miss = [], Counter()
    for p in sorted(Path(returns_folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            if r['status'] != 'complete':
                continue
            f = feats.get((r['cik'], r['sym'], r['entry']))
            if not f or f['status'] != 'ok':
                miss[f['status'] if f else 'no_feature_row'] += 1
                continue
            rows.append({**r, **{k: v for k, v in f.items() if k not in ('status', 'entry', 'sym', 'cik')}})
    print(f'complete-return rows joined to features: {len(rows)}; complete rows without usable features: {dict(miss)}')
    return rows


def summary(features_folder, returns_folder):
    import numpy as np
    rows = load(features_folder, returns_folder)
    dev = sorted([r for r in rows if r['entry'] <= DEV_END], key=week_of)
    pil = [r for r in rows if r['entry'] > DEV_END]
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    print(f'development n={len(dev)} excess {mean(dev):+.3f} (Entry 28: n={EXPECT_DEV}, +{EXPECT_MEAN}); without the three episodes n={len(d2)} {mean(d2):+.3f}; pilot n={len(pil)} {mean(pil):+.3f}')
    if len(dev) != EXPECT_DEV or abs(mean(dev) - EXPECT_MEAN) > 0.0006:
        print('WARNING: development does not reproduce Entry 28 exactly; treat everything below as PROVISIONAL until explained')
    info = prep(dev)
    print('\n=== A. Coverage (development events with the measure available) ===')
    print('  ' + '; '.join(f'{m} {sum(m in r for r in dev)}' for m in MEASURES))
    print('\n=== B. Quintiles of each measure, development 2006-2020: mean excess over same-window SPY (ATR), n, weeks. Q1 = lowest value ===')
    obs, p1, best, pmin, keys = perm_test(dev, info)
    for m in MEASURES:
        if m not in info:
            print(f'{m}: too few values')
            continue
        qs = quintile_line(dev, m, info[m]['cuts'])
        qs2 = quintile_line(d2, m, info[m]['cuts'])
        rho2, n2 = spearman(d2, m)
        cutstr = '/'.join(f'{c:.3g}' for c in info[m]['cuts'])
        print(f'{m}  (cut points {cutstr})')
        print('    all dev:  ' + ' | '.join(f'Q{q + 1} {cell(g)}' for q, g in enumerate(qs)))
        print('    no episodes: ' + ' | '.join(f'Q{q + 1} {cell(g)}' for q, g in enumerate(qs2)))
        print(f'    Spearman {obs[(m, "rho")]:+.3f} (chance alone {p1[(m, "rho")]:.1%}); smile {obs[(m, "smile")]:+.3f} (chance alone {p1[(m, "smile")]:.1%}); '
              f'without episodes Spearman {rho2:+.3f} (n={n2})')
    print('\n=== C. Chance test: excess shuffled inside the same entry week (10,000 shuffles, development only) ===')
    ranked = sorted(keys, key=lambda k: p1[k])
    print('smallest single-question chances: ' + '; '.join(f'{k[0]} {k[1]} {obs[k]:+.3f} ({p1[k]:.1%})' for k in ranked[:6]))
    print(f'Best of this menu of {len(keys)} statistics (21 measures x Spearman and smile): smallest single chance {pmin:.1%}; '
          f'chance the best of {len(keys)} is at least that small by luck {best:.1%}')
    print('\n=== D. Fixed ATR bands, development (all | without episodes) ===')
    for m in ('raw21', 'raw63'):
        bands = [('down more than 3 ATR', lambda v: v <= -3), ('down 1 to 3 ATR', lambda v: -3 < v <= -1),
                 ('within 1 ATR', lambda v: -1 < v < 1), ('up more than 1 ATR', lambda v: v >= 1)]
        for name, f in bands:
            print(f'{m} {name}: {cell([r for r in dev if m in r and f(r[m])])} | {cell([r for r in d2 if m in r and f(r[m])])}')
    print('\n=== E. Crossing with the market: stock below / above the development median of the measure, by SPY up / down over the same window ===')
    for kind in ('raw', 'rel'):
        for W in WINDOWS:
            m = f'{kind}{W}'
            if m not in info:
                continue
            med = float(np.median(info[m]['x']))
            for lab_, sel in (('stock lower half', lambda r: r[m] <= med), ('stock upper half', lambda r: r[m] > med)):
                for sp_lab, sp in (('SPY down', lambda r: r[f'spy{W}'] <= 0), ('SPY up', lambda r: r[f'spy{W}'] > 0)):
                    a = [r for r in dev if m in r and f'spy{W}' in r and sel(r) and sp(r)]
                    b = [r for r in d2 if m in r and f'spy{W}' in r and sel(r) and sp(r)]
                    print(f'{m} {lab_}, {sp_lab}: {cell(a)} | no episodes {cell(b)}')
    print('\n=== F. 2026 pilot (in-sample, small): quintiles by the DEVELOPMENT cut points ===')
    for m in MEASURES:
        if m not in info:
            continue
        qs = quintile_line(pil, m, info[m]['cuts'])
        r_, n_ = spearman(pil, m)
        print(f'{m}: ' + ' | '.join(f'Q{q + 1} {cell(g)}' for q, g in enumerate(qs)) + f'  Spearman {r_:+.3f} (n={n_})')
    confound_checks(dev, pil)
    print(f'\nQuestions asked on this cohort in this entry: {len(keys)} statistics in the menu (21 measures x 2), plus descriptive quintile, band, crossing and pilot tables.')


def perm_rho(rows, x, y, draws=10000):
    """Single-question chance for the Spearman of x with y, y shuffled inside the same entry week."""
    import numpy as np
    sub = sorted([r for r in rows if x in r and y in r], key=week_of)
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in sub}))}
    wi = np.array([wk[week_of(r)] for r in sub])
    xs = rank_avg([r[x] for r in sub])
    xc = xs - xs.mean()
    yv = np.array([r[y] for r in sub])
    n = len(sub)
    norm = float(np.sqrt((xc ** 2).sum()) * np.sqrt(((np.arange(n) - (n - 1) / 2) ** 2).sum()))

    def rho(v):
        o = v.argsort()
        r = np.empty(n)
        r[o] = np.arange(n, dtype=float)
        return float(xc @ (r - r.mean()) / norm)
    obs = rho(yv)
    rng = np.random.default_rng(SEED)
    hits = sum(abs(rho(yv[np.lexsort((rng.random(n), wi))])) >= abs(obs) - 1e-12 for _ in range(draws))
    return obs, hits / draws, n


def confound_checks(dev, pil):
    """POST-HOC follow-up (asked after seeing the Entry 36 long-window result): is the long-window pattern an artifact of the
    ATR scaling (both the decline and the excess are divided by the entry ATR) or of price level?"""
    import numpy as np
    for r in dev + pil:
        r['atr_pct'] = r['atr'] / r['entry_open']
        r['excess_pct'] = r['excess_atr'] * r['atr_pct']              # stock % return minus SPY % return over the 21-session hold
    print('\n=== G. POST-HOC follow-up: ATR-scale and price-level checks (development) ===')
    for a, b in (('atr_pct', 'excess_atr'), ('atr_pct', 'raw252'), ('atr_pct', 'pct252'), ('entry_open', 'raw252'), ('entry_open', 'excess_atr')):
        r_, n_ = spearman(dev, a, b)
        print(f'Spearman {a} vs {b}: {r_:+.3f} (n={n_})')
    print('Percent-unit version (stock decline in % vs excess in % over the hold; no ATR scaling on either side), shuffle chance alone:')
    for W in (21, 63, 126, 252):
        o, p, n = perm_rho(dev, f'pct{W}', 'excess_pct')
        o2, p2, _ = perm_rho(dev, f'pct{W}', 'excess_atr')
        print(f'  pct{W} vs excess_pct: Spearman {o:+.3f} (chance {p:.1%}); pct{W} vs excess_atr: {o2:+.3f} (chance {p2:.1%}); n={n}')
        sub = [r for r in dev if f'pct{W}' in r]
        cuts = np.quantile([r[f'pct{W}'] for r in sub], [0.2, 0.4, 0.6, 0.8])
        lab = np.searchsorted(cuts, [r[f'pct{W}'] for r in sub], side='right')
        cells = []
        for q in range(5):
            g = [r for r, l in zip(sub, lab) if l == q]
            cells.append(f'Q{q + 1} {100 * statistics.fmean(r["excess_pct"] for r in g):+.2f}% / {statistics.fmean(r["excess_atr"] for r in g):+.3f} ATR (n={len(g)})')
        print('    by fifth of pct decline (Q1 = biggest fall): ' + ' | '.join(cells) + '   cuts ' + '/'.join(f'{100 * c:.0f}%' for c in cuts))
    for key, name in (('atr_pct', 'daily-range % of price (ATR / entry open)'), ('entry_open', 'entry price')):
        vals = [r[key] for r in dev]
        t1, t2 = np.quantile(vals, [1 / 3, 2 / 3])
        print(f'Within terciles of {name} (cuts {t1:.4g} / {t2:.4g}):')
        for lab_, f in (('low', lambda v: v <= t1), ('middle', lambda v: t1 < v <= t2), ('high', lambda v: v > t2)):
            g = [r for r in dev if f(r[key])]
            a, na = spearman(g, 'raw252', 'excess_atr')
            b, nb = spearman(g, 'pct252', 'excess_pct')
            c, nc = spearman(g, 'rel252', 'excess_atr')
            print(f'  {lab_}: n={len(g)}, mean excess {mean(g):+.3f} ATR / {100 * statistics.fmean(r["excess_pct"] for r in g):+.2f}%; '
                  f'raw252 vs excess_atr {a:+.3f}; rel252 vs excess_atr {c:+.3f}; pct252 vs excess_pct {b:+.3f} (n={nb})')
    print('Questions asked in this follow-up (post hoc): 8 Spearman tests with chance, 8 descriptive Spearman rows, 6 tercile cells x 3.')


# ------------------------------------------------------------------ self-test
def selftest():
    import random
    # synthetic bars: close rises 1/day for 300 sessions, ATR 2, SPY +0.1%/day
    base = date(2010, 1, 4)
    ds, d = [], base
    while len(ds) < 320:
        if d.weekday() < 5:
            ds.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    stock = {x: (100 + k, 101 + k, 99 + k, 100 + k) for k, x in enumerate(ds)}   # true range 2 or so
    spy = {x: (100 * 1.001 ** k,) * 4 for k, x in enumerate(ds)}
    entry = ds[290]
    f = features(ds, stock, spy, entry)
    assert f['status'] == 'ok', f
    last, i = stock[ds[289]][3], 290
    assert abs(f['raw21'] - (last - stock[ds[289 - 21]][3]) / f['atr']) < 1e-9
    assert abs(f['spy21'] - (spy[ds[289]][3] / spy[ds[289 - 21]][3] - 1)) < 1e-12
    assert abs(f['rel21'] - (f['raw21'] - f['spy21'] * stock[entry][0] / f['atr'])) < 1e-9
    assert f['hi21'] == 0 and f['dn21'] == 0 and 'raw252' in f
    # a window reaching before the first session is blank, not an error
    f2 = features(ds, stock, spy, ds[100])
    assert 'raw252' not in f2 and 'raw63' in f2
    # a missing reference bar falls back to the nearest earlier one
    s2 = dict(stock)
    del s2[ds[289 - 21]]
    assert abs(features(ds, s2, spy, entry)['raw21'] - (last - stock[ds[289 - 22]][3]) / f['atr']) < 1e-9
    # falling series: distance below the high and the down share
    s3 = {x: (200 - k, 201 - k, 199 - k, 200 - k) for k, x in enumerate(ds)}
    f3 = features(ds, s3, spy, entry)
    assert f3['dn21'] == 1.0 and f3['hi21'] < 0 and f3['raw21'] < 0
    # D-068 guard
    try:
        features(ds, stock, spy, '2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    # permutation machinery: reproducible, and a built-in relationship is detected
    rng = random.Random(1)
    rows = []
    for k in range(400):
        v = rng.gauss(0, 1)
        rows.append({'entry': f'2010-{1 + k % 12:02d}-{1 + k % 27:02d}', 'cik': str(k), 'excess_atr': 0.8 * v + rng.gauss(0, 1),
                     'atr': 1.0 + rng.random(), 'entry_open': 10 + 30 * rng.random(),
                     **{f'pct{w}': rng.gauss(0, 0.2) for w in WINDOWS},
                     **{m: (v if m == 'raw21' else rng.gauss(0, 1)) for m in MEASURES}})
    rows.sort(key=week_of)
    info = prep(rows)
    a = perm_test(rows, info, 200)
    b = perm_test(rows, info, 200)
    assert a[0] == b[0] and a[2] == b[2]
    assert a[1][('raw21', 'rho')] < 0.02 and a[0][('raw21', 'rho')] > 0.3, (a[0][('raw21', 'rho')], a[1][('raw21', 'rho')])
    assert a[2] < 0.05                       # best-of-menu also sees it
    null = [{**r, 'excess_atr': rng.gauss(0, 1)} for r in rows]
    n1 = perm_test(null, prep(null), 200)
    assert n1[2] > 0.05, n1[2]
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        confound_checks([dict(r) for r in rows], [dict(r) for r in rows[:30]])
    assert 'Within terciles of entry price' in buf.getvalue() and 'pct252 vs excess_pct' in buf.getvalue()
    o, p, n = perm_rho(rows, 'raw21', 'excess_atr', 300)
    assert o > 0.3 and p < 0.01 and n == 400
    print('factor_decline self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'summary':
        summary(a.arg, a.arg2)
    else:
        raise SystemExit(__doc__)
