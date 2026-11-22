"""Oversold scan (POST HOC, asked by Michael 8 Nov 2026): does RSI, or the distance below a moving average in ATRs, predict the next 21-session
excess over same-window SPY, and does it add anything to the leads already found (Nasdaq lagging N, deep 12-month fall D1)?

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used. No sealed return is read. Returns = Entry 28 (run 42490748366),
decline features = Entry 36 (run 42499472150), lead63 = Entry 37 (run 42501167019). New features are measured from sessions strictly before the entry
session (the last completed session is entry index - 1); no price at or after entry is used, and no returns are computed here.

Features (several horizons, declared before any value was joined to a return):
  rsiP   RSI over the last P completed sessions, SIMPLE averages (Cutler form: average of the up-moves over average of the down-moves of the last P
         close-to-close changes; RSI = 100 - 100/(1 + up/down); 100 if no down-moves, 50 if no moves). Not Wilder's smoothed RSI: it needs no warm-up and is
         exactly reproducible. P in 5, 14, 28, 63 sessions (1 week, 3 weeks, 6 weeks, 3 months).  Low value = oversold.
  maW    (last close - simple moving average of the last W closes) / entry ATR, so negative = that many ATRs below the average. W in 20, 50, 100, 200 sessions.
         Entry ATR = mean true range of the 14 completed sessions before entry (identical to Entry 28; checked against the Entry 36 file).
  A window needs 80% valid closes; otherwise the feature is blank. maW needs W sessions before entry, so the 200-session value is blank for entries
  with too little archived history.
Menu (the chance test covers exactly this): 8 measures (rsi5 rsi14 rsi28 rsi63, ma20 ma50 ma100 ma200) x 2 statistics = 16: (a) Spearman rank correlation
of excess with the measure, (b) 'smile' = mean excess of the lowest and highest fifths minus the middle three fifths. Chance = excess shuffled inside the
same entry week (10,000 draws, as Entry 36; `factor_decline.perm_test`), single-question and best of 16. Q1 = lowest value = most oversold.
Descriptive only (not in the chance menu):
  B. quintile tables, all development and without 2008Q4 / 2011Q3 / 2020Q1 (n, entry weeks, stock and SPY legs in the summary line of the lowest fifth);
  C. fixed thresholds: RSI <= 10, 20, 30 for each period; ma <= -1, -2, -3, -4, -6 ATR for each window;
  D. overlap: Spearman of each measure with raw21, raw252 and lead63 (is 'oversold' just the same stocks as the 12-month fall, or the same market periods?);
  E. incremental value: O = lowest fifth of the measure. Excess by (N + D1 points 0, 1, 2) with and without O, and a regression
     excess = a + bN*N + bD*D1 + bO*O with quarter-block 95% ranges (10,000 resamples of calendar quarters). Does bO stay away from zero once N and D1 are in?
  F. O by era (2006-10 vs 2011-20).
Cohort for E: development events with all measures needed, lead63 and raw252 (about 1,275, as Entry 51). N = lead63 <= 20th percentile; D1 = raw252 <= 20th
percentile, both recomputed on the joined cohort (as Entry 51).
Cautions written in advance: Entry 36 found 5-, 21- and 63-session declines show no relationship with the next 21 sessions, so the short RSI and short
moving-average measures are expected to show little; the long ones (ma100, ma200, rsi63) overlap the 12-month fall; measures within a family are strongly
correlated, so best-of-16 is conservative and single-question chances are optimistic; costs and survivorship (Entries 38, 40, 44, 45) are not in any number.
Anything picked because it looks best after this run is a lead, not a rule.

Usage:  python oversold_scan.py year YEAR --primary FILE --out FILE   |   scan OSC_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER   |   --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
import factor_regime as fg
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, load_span, quarter, true_range
from score_scan import QBoot

RSI_P = (5, 14, 28, 63)
MA_W = (20, 50, 100, 200)
MEASURES = [f'rsi{p}' for p in RSI_P] + [f'ma{w}' for w in MA_W]
RSI_CUTS = (10, 20, 30)
MA_CUTS = (-1, -2, -3, -4, -6)


def rsi_from(closes):
    """closes: valid closes in time order (last = most recent). Simple-average RSI of consecutive changes."""
    ups = downs = 0.0
    for a, b in zip(closes, closes[1:]):
        if b > a:
            ups += b - a
        elif b < a:
            downs += a - b
    if ups == 0 and downs == 0:
        return 50.0
    if downs == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ups / downs)


def features(dates, stock, entry):
    """dates: sorted session dates; stock: {date: (o, h, l, c)}. Uses only sessions before `entry`."""
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
    last = stock[last_d][3]
    out = {'status': 'ok', 'atr': atr}
    for p in RSI_P:
        if i - 1 - p < 0:
            continue
        cl = [stock[d][3] for d in dates[i - 1 - p:i] if d in stock]
        if len(cl) >= 0.8 * (p + 1) and len(cl) >= 3:
            out[f'rsi{p}'] = rsi_from(cl)
    for w in MA_W:
        if i - w < 0:
            continue
        cl = [stock[d][3] for d in dates[i - w:i] if d in stock]
        if len(cl) >= 0.8 * w:
            out[f'ma{w}'] = (last - sum(cl) / len(cl)) / atr
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
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded (incl. {year - 1})')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = features(dates, series, e['entry'])
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))) + '; coverage ' + ', '.join(f'{m} {sum(m in r for r in rows)}' for m in MEASURES))


# ------------------------------------------------------------------ analysis
def load(osc_folder, decline_folder, regime_folder, returns_folder):
    rows = fd.load(decline_folder, returns_folder)
    new = {}
    for p in sorted(Path(osc_folder).glob('osc_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            new[(r['cik'], r['sym'], r['entry'])] = r
    fdate = fg.load_features(regime_folder)
    dev, atr_diff, nof = [], 0, 0
    for r in rows:
        if r['entry'] > DEV_END:
            continue
        f = new.get((r['cik'], r['sym'], r['entry']))
        if not f or f['status'] != 'ok':
            nof += 1
            continue
        if abs(f['atr'] - r['atr']) > 1e-9:
            atr_diff += 1
        rg = fdate.get(r['entry'], {})
        dev.append({**r, **{m: f[m] for m in MEASURES if m in f}, **({'lead63': rg['lead63']} if 'lead63' in rg else {})})
    print(f'development rows with returns and Entry 36 features: {len(dev) + nof}; with oscillator features {len(dev)}; no usable oscillator row {nof}; '
          f'entry ATR differences vs the Entry 36 file: {atr_diff}')
    return dev, atr_diff


def mean_or_nan(rs):
    return statistics.fmean(r['excess_atr'] for r in rs) if rs else float('nan')


def legs(rs):
    if not rs:
        return 'n=0'
    ex = [r['excess_atr'] for r in rs]
    return (f'n={len(rs):4d} w={len({fd.week_of(r) for r in rs}):3d}  excess {statistics.fmean(ex):+.3f} '
            f'(stock {statistics.fmean(r["stock_atr"] for r in rs):+.3f}, SPY {statistics.fmean(r["spy_atr"] for r in rs):+.3f})  '
            f'median {statistics.median(ex):+.3f}  beat SPY {sum(e > 0 for e in ex) / len(ex):.0%}')


def scan(osc_folder, decline_folder, regime_folder, returns_folder):
    import numpy as np
    dev, atr_diff = load(osc_folder, decline_folder, regime_folder, returns_folder)
    allm = mean_or_nan(dev)
    print(f'development cohort n={len(dev)} excess {allm:+.3f}')
    if atr_diff:
        print('WARNING: entry ATR does not match the Entry 36 file for some rows; PROVISIONAL until explained')
    dev.sort(key=fd.week_of)
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    print('\n=== A. Coverage (events with the measure) ===')
    print('  ' + '; '.join(f'{m} {sum(m in r for r in dev)}' for m in MEASURES))
    fd.MEASURES = MEASURES                                   # reuse the Entry 36 chance machinery for this menu
    info = fd.prep(dev)
    obs, p1, best, pmin, keys = fd.perm_test(dev, info)
    print('\n=== B. Quintiles of each measure (Q1 = lowest = most oversold): mean excess over same-window SPY (ATR), n, entry weeks ===')
    for m in MEASURES:
        if m not in info:
            print(f'{m}: too few values')
            continue
        qs, qs2 = fd.quintile_line(dev, m, info[m]['cuts']), fd.quintile_line(d2, m, info[m]['cuts'])
        rho2, n2 = fd.spearman(d2, m)
        print(f'{m}  (cut points {"/".join(f"{c:.3g}" for c in info[m]["cuts"])})')
        print('    all dev:     ' + ' | '.join(f'Q{q + 1} {fd.cell(g)}' for q, g in enumerate(qs)))
        print('    no episodes: ' + ' | '.join(f'Q{q + 1} {fd.cell(g)}' for q, g in enumerate(qs2)))
        print(f'    Q1 legs: {legs(qs[0])}')
        print(f'    Spearman {obs[(m, "rho")]:+.3f} (chance alone {p1[(m, "rho")]:.1%}); smile {obs[(m, "smile")]:+.3f} (chance alone {p1[(m, "smile")]:.1%}); '
              f'without episodes Spearman {rho2:+.3f} (n={n2})')
    print('\n=== C. Chance test: excess shuffled inside the same entry week (10,000 draws, development only) ===')
    ranked = sorted(keys, key=lambda k: p1[k])
    print('smallest single-question chances: ' + '; '.join(f'{k[0]} {k[1]} {obs[k]:+.3f} ({p1[k]:.1%})' for k in ranked[:6]))
    print(f'Best of this menu of {len(keys)} statistics: smallest single chance {pmin:.1%}; chance the best of {len(keys)} is at least that small by luck {best:.1%}')
    print('\n=== D. Fixed thresholds (descriptive) ===')
    for p in RSI_P:
        for c in RSI_CUTS:
            print(f'  rsi{p} <= {c}: {legs([r for r in dev if f"rsi{p}" in r and r[f"rsi{p}"] <= c])}')
    for w in MA_W:
        for c in MA_CUTS:
            print(f'  ma{w} <= {c} ATR below average: {legs([r for r in dev if f"ma{w}" in r and r[f"ma{w}"] <= c])}')
    print('\n=== E. Overlap with the known leads: Spearman(measure, raw21 / raw252 / lead63) (descriptive) ===')
    for m in MEASURES:
        parts = []
        for o in ('raw21', 'raw252', 'lead63'):
            sub = [r for r in dev if m in r and o in r]
            rho = float(np.corrcoef(fd.rank_avg([r[m] for r in sub]), fd.rank_avg([r[o] for r in sub]))[0, 1]) if len(sub) > 30 else float('nan')
            parts.append(f'{o} {rho:+.2f}')
        print(f'  {m}: ' + ', '.join(parts))
    # incremental value on the cohort with lead63 and raw252
    coh = [r for r in dev if 'lead63' in r and 'raw252' in r]
    cn = float(np.quantile([r['lead63'] for r in coh], 0.2))
    cd = float(np.quantile([r['raw252'] for r in coh], 0.2))
    for r in coh:
        r['N'], r['D1'] = r['lead63'] <= cn, r['raw252'] <= cd
        r['pts'] = int(r['N']) + int(r['D1'])
    print(f'\n=== F. Does an oversold flag add to N + D1? cohort n={len(coh)} (lead63 20th pct {cn:+.4f}; raw252 20th pct {cd:+.2f}); O = lowest fifth of the measure within this cohort ===')
    print(f'  reference by points (N + D1): ' + ' | '.join(f'{k}: {legs([r for r in coh if r["pts"] == k])}' for k in (0, 1, 2)))
    qb = QBoot(coh)
    qid = np.array([qb.qi[quarter(r['entry'])] for r in coh])
    y = np.array([r['excess_atr'] for r in coh])
    for m in MEASURES:
        sub = [r for r in coh if m in r]
        if len(sub) < 200:
            print(f'  {m}: too few'); continue
        cut = float(np.quantile([r[m] for r in sub], 0.2))
        for r in sub:
            r['O'] = r[m] <= cut
        print(f'  -- {m}  (O: value <= {cut:.3g}) --')
        for k in (0, 1, 2):
            a, b = [r for r in sub if r['pts'] == k and r['O']], [r for r in sub if r['pts'] == k and not r['O']]
            print(f'     points {k}: with O {legs(a)}\n               without O {legs(b)}')
        e1 = [r for r in sub if r['O'] and r['entry'] < '2011-01-01']
        e2 = [r for r in sub if r['O'] and r['entry'] >= '2011-01-01']
        print(f'     O by era: 2006-10 {mean_or_nan(e1):+.3f} (n={len(e1)}) | 2011-20 {mean_or_nan(e2):+.3f} (n={len(e2)})')
        sq = QBoot(sub)
        sqid = np.array([sq.qi[quarter(r['entry'])] for r in sub])
        X = np.array([[1.0, float(r['N']), float(r['D1']), float(r['O'])] for r in sub])
        beta, lo, hi = sq.ols_ranges(X, np.array([r['excess_atr'] for r in sub]), sqid)
        print('     regression excess = a + bN*N + bD*D1 + bO*O (quarter-block 95%): ' +
              '; '.join(f'{nm} {beta[j]:+.3f} [{lo[j]:+.3f}, {hi[j]:+.3f}]' for j, nm in ((1, 'N'), (2, 'D1'), (3, 'O'))))
    print(f'\nQuestions asked on this cohort in this entry: {len(keys)} chance-tested statistics (8 measures x 2), plus descriptive quintiles, thresholds, overlaps and '
          f'8 incremental regressions. POST HOC.')


# ------------------------------------------------------------------ self-test
def selftest():
    import random
    from datetime import date
    assert rsi_from([1, 2, 3, 4]) == 100.0 and rsi_from([4, 3, 2, 1]) == 0.0 and rsi_from([5, 5, 5]) == 50.0
    assert abs(rsi_from([10, 11, 10, 11]) - 66.6666667) < 1e-4          # ups 2, downs 1
    ds, d = [], date(2010, 1, 4)
    while len(ds) < 320:
        if d.weekday() < 5:
            ds.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    up = {x: (100 + k, 101 + k, 99 + k, 100 + k) for k, x in enumerate(ds)}
    f = features(ds, up, ds[290])
    assert f['status'] == 'ok' and f['rsi14'] == 100.0 and f['rsi63'] == 100.0
    last = up[ds[289]][3]
    sma50 = sum(up[x][3] for x in ds[240:290]) / 50
    assert abs(f['ma50'] - (last - sma50) / f['atr']) < 1e-9 and f['ma50'] > 0
    dn = {x: (300 - k, 301 - k, 299 - k, 300 - k) for k, x in enumerate(ds)}
    g = features(ds, dn, ds[290])
    assert g['rsi5'] == 0.0 and g['ma200'] < 0 and g['ma20'] < 0
    # no lookahead: changing the entry-day and later bars changes nothing
    alt = dict(up)
    for x in ds[290:]:
        alt[x] = (1, 2, 0.5, 1)
    assert features(ds, alt, ds[290]) == f
    # window reaching before the first session is blank
    assert 'ma200' not in features(ds, up, ds[100]) and 'ma50' in features(ds, up, ds[100])
    try:
        features(ds, up, '2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    # the reused chance machinery works on this measure menu
    rng = random.Random(2)
    rows = []
    for k in range(500):
        v = rng.gauss(0, 1)
        rows.append({'entry': f'2010-{1 + k % 12:02d}-{1 + k % 27:02d}', 'cik': str(k), 'excess_atr': 0.8 * v + rng.gauss(0, 1),
                     **{m: (v if m == 'rsi14' else rng.gauss(0, 1)) for m in MEASURES}})
    rows.sort(key=fd.week_of)
    fd.MEASURES = MEASURES
    info = fd.prep(rows)
    o, p, best, pmin, keys = fd.perm_test(rows, info, 200)
    assert len(keys) == 16 and o[('rsi14', 'rho')] > 0.3 and p[('rsi14', 'rho')] < 0.02 and best < 0.05
    print('oversold_scan self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('arg3', nargs='?')
    ap.add_argument('arg4', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'scan':
        scan(a.arg, a.arg2, a.arg3, a.arg4)
    else:
        raise SystemExit(__doc__)
