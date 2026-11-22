"""Context scan (POST HOC, three proposals approved by Michael 8 Nov 2026): C20 bounce off the 12-month low, C21 dollar volume vs the excess,
C22 SPY below its 200-session average as a gate on the two live leads.

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used. No sealed return is read. Returns = Entry 28 (run 42490748366),
decline features = Entry 36 (run 42499472150), SPY/Nasdaq date features = Entry 37 (run 42501167019), dollar volume = Entry 54 (run 42518394556).
Excess = stock minus same-window SPY over 21 sessions in the stock's ATR units, stock and SPY legs shown (D-053). No costs. Returns code PROVISIONAL
as in Entry 28. Leads used: N = lead63 <= its 20th percentile (Nasdaq lagging, Entries 37, 39, 41), D1 = raw252 <= its 20th percentile (fell most over
12 months, Entry 36); both recomputed on the cohort that has both (about 1,275 events, as Entries 51 and 53).

=== bounce (C20) ===  new features from the 252 sessions strictly before the entry session (the last completed session is entry index - 1):
  up_low  (last close - lowest close of the 252 sessions) / entry ATR      up_pct  last close / lowest close - 1
  dsl     sessions between the lowest close and the last completed session (0 = the low is the last session; ties take the latest low)
  new-low flag: dsl <= 4 (a 252-session closing low was set in the last 5 sessions).  A window needs 80% valid closes.
  Chance menu (week-shuffle of excess, 10,000 draws, Entry 36 machinery): 3 measures x 2 statistics (Spearman, smile) = 6 on the whole cohort, and the
  same 6 inside D1. Single-question chance and best of 6, for each set separately (12 on the tally).
  Descriptive: quintiles (terciles inside D1) with and without 2008Q4 / 2011Q3 / 2020Q1; fixed bands up_low <= 1, 2, 4 and >= 4, 8, 12 ATR and
  dsl <= 4, >= 21, 63, 126, in the whole cohort and inside D1; overlap (Spearman with raw21, raw252, lead63); 2006-10 vs 2011-20;
  excess = a + bN*N + bD*D1 + bLo*Lo + bHi*Hi, Lo / Hi = lowest / highest fifth of up_low, quarter-block 95% ranges (10,000 resamples of calendar quarters).
=== dv (C21) ===  dv_mean / dv_median = mean / median of close x volume over the 15 completed sessions before entry (D-061 definition, Entry 54 files).
  Chance menu: 2 measures x 2 statistics = 4, on the whole cohort, inside D1 and inside N (12 on the tally).
  Descriptive: bands under $5M, 5-10M, 10-25M, 25-100M, 100M and over for all events, D1, not-D1, N, not-N, with D1-minus-rest and N-minus-rest
  differences and quarter-block ranges; D1 and N events with dv_mean >= $10M and >= $25M, with and without the three episodes; trades per month.
=== gate (C22) ===  B = SPY close below its 200-session average at entry (Entry 37 feature spyt200 < 0).
  Tables: B alone; D1 x B; N x B; (N + D1 points) x B; with and without the three episodes; 2006-10 vs 2011-20; separate entry spells (gap > 42 days);
  Entry 36's SPY-over-252-sessions crossing restated (spy252 < 0) for comparison.
  Chance menu: 2 statistics = difference-in-differences DiD_D1 = [mean(D1,B) - mean(D1,notB)] - [mean(notD1,B) - mean(notD1,notB)] and DiD_N likewise;
  circular shift of the B series over the entry dates (exact, as Entry 37), single-question chance and best of 2.
Cautions written in advance: every lead used here was found on this same data (Entries 36, 37), so nothing here is out-of-sample; market features have
few independent episodes (a handful of long stretches); the deepest fallers carry survivorship exposure (Entries 38, 40, 44) and costs (Entry 45) that no
number here includes; best-of-menu chances are conservative inside a family of correlated measures. Anything picked because it looks best after this run
is a lead, not a rule.

Usage:  python context_scan.py lowyear YEAR --primary FILE --out FILE
        python context_scan.py bounce LOW_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER
        python context_scan.py dv DV_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER
        python context_scan.py gate DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER
        python context_scan.py --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
import factor_regime as fg
from factor_regime import spells
from oversold_scan import legs, mean_or_nan
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, load_span, quarter, true_range
from score_scan import QBoot

LOW_W = 252
LOW_MEASURES = ['up_low', 'up_pct', 'dsl']
DV_MEASURES = ['dv_mean', 'dv_median']
DV_BANDS = [('under $5M', 0, 5e6), ('$5-10M', 5e6, 10e6), ('$10-25M', 10e6, 25e6), ('$25-100M', 25e6, 100e6), ('$100M and over', 100e6, float('inf'))]
MONTHS = 180
SEED = fd.SEED


# ------------------------------------------------------------------ C20 features
def low_features(dates, stock, entry):
    """dates: sorted session dates; stock: {date: (o, h, l, c)}. Uses only sessions strictly before `entry`."""
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
    if i - LOW_W < 0:
        return out
    window = dates[i - LOW_W:i]
    pts = [(k, stock[d][3]) for k, d in enumerate(window) if d in stock and stock[d][3] > 0]
    if len(pts) >= 0.8 * LOW_W:
        low = min(c for _, c in pts)
        pos = max(k for k, c in pts if c == low)               # latest occurrence of the lowest close
        out['up_low'] = (last - low) / atr
        out['up_pct'] = last / low - 1
        out['dsl'] = float(LOW_W - 1 - pos)
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
            r = low_features(dates, series, e['entry'])
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))) + '; coverage ' + ', '.join(f'{m} {sum(m in r for r in rows)}' for m in LOW_MEASURES))


# ------------------------------------------------------------------ shared loading
def load_base(decline_folder, regime_folder, returns_folder):
    """Development events with returns and Entry 36 features, plus date-level regime features (lead63, spyt200)."""
    rows = fd.load(decline_folder, returns_folder)
    fdate = fg.load_features(regime_folder)
    dev = []
    for r in rows:
        if r['entry'] > DEV_END:
            continue
        rg = fdate.get(r['entry'], {})
        extra = {k: rg[k] for k in ('lead63', 'spyt200') if k in rg}
        dev.append({**r, **extra})
    dev.sort(key=fd.week_of)
    return dev


def flag_cohort(dev):
    """Cohort with lead63 and raw252: N = lead63 <= 20th pct, D1 = raw252 <= 20th pct (recomputed on the joined cohort, as Entry 51)."""
    import numpy as np
    coh = [r for r in dev if 'lead63' in r and 'raw252' in r]
    cn = float(np.quantile([r['lead63'] for r in coh], 0.2))
    cd = float(np.quantile([r['raw252'] for r in coh], 0.2))
    for r in coh:
        r['N'], r['D1'] = r['lead63'] <= cn, r['raw252'] <= cd
        r['pts'] = int(r['N']) + int(r['D1'])
    return coh, cn, cd


def no_ep(rs):
    return [r for r in rs if quarter(r['entry']) not in EPISODES]


def chance_block(label, rows, measures):
    """Entry 36 week-shuffle machinery on `rows` for `measures` (2 statistics each)."""
    rows = sorted(rows, key=fd.week_of)
    fd.MEASURES = measures
    info = fd.prep(rows)
    if not info:
        print(f'  [{label}] too few values for the chance test')
        return
    obs, p1, best, pmin, keys = fd.perm_test(rows, info)
    print(f'  [{label}] n={len(rows)}: ' + '; '.join(f'{k[0]} {k[1]} {obs[k]:+.3f} (chance alone {p1[k]:.1%})' for k in keys))
    print(f'  [{label}] smallest single chance {pmin:.1%}; chance the best of {len(keys)} is at least that small by luck {best:.1%}')
    return info


def fmt_range(r):
    return f'[{r[0]:+.3f}, {r[1]:+.3f}]'


# ------------------------------------------------------------------ C20 scan
def load_low(low_folder, dev):
    new = {}
    for p in sorted(Path(low_folder).glob('low_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            new[(r['cik'], r['sym'], r['entry'])] = r
    out, nof, atr_diff = [], 0, 0
    for r in dev:
        f = new.get((r['cik'], r['sym'], r['entry']))
        if not f or f['status'] != 'ok':
            nof += 1
            continue
        if abs(f['atr'] - r['atr']) > 1e-9:
            atr_diff += 1
        out.append({**r, **{m: f[m] for m in LOW_MEASURES if m in f}})
    print(f'development rows with returns and Entry 36 features {len(dev)}; with 12-month-low features {len(out)}; no usable row {nof}; '
          f'entry ATR differences vs the Entry 36 file: {atr_diff}')
    return out, atr_diff


def bounce(low_folder, decl, regime, ret):
    import numpy as np
    dev0 = load_base(decl, regime, ret)
    dev, atr_diff = load_low(low_folder, dev0)
    n_all = len(dev)
    dev = [r for r in dev if all(m in r for m in LOW_MEASURES)]       # entries with less than 252 sessions of archived history have no low features
    print(f'events with all three 12-month-low features: {len(dev)} of {n_all} (the rest have too little archived history or too many missing closes)')
    print(f'development cohort n={len(dev)} excess {mean_or_nan(dev):+.3f}')
    if atr_diff:
        print('WARNING: entry ATR does not match the Entry 36 file for some rows; PROVISIONAL until explained')
    d2 = no_ep(dev)
    print('\n=== A. Coverage ===\n  ' + '; '.join(f'{m} {sum(m in r for r in dev)}' for m in LOW_MEASURES))
    coh, cn, cd = flag_cohort([r for r in dev if all(m in r for m in LOW_MEASURES)])
    d1 = [r for r in coh if r['D1']]
    print(f'  flag cohort (lead63, raw252 and low features) n={len(coh)}; N cut {cn:+.4f}; D1 cut {cd:+.2f} ATR; D1 n={len(d1)}')
    print('\n=== B. Whole cohort: quintiles (Q1 = lowest = still at its low) and chance ===')
    info = chance_block('whole cohort', dev, LOW_MEASURES)
    for m in LOW_MEASURES:
        if not info or m not in info:
            continue
        qs, qs2 = fd.quintile_line(sorted(dev, key=fd.week_of), m, info[m]['cuts']), fd.quintile_line(sorted(d2, key=fd.week_of), m, info[m]['cuts'])
        print(f'{m}  (cut points {"/".join(f"{c:.3g}" for c in info[m]["cuts"])})')
        print('    all dev:     ' + ' | '.join(f'Q{q + 1} {fd.cell(g)}' for q, g in enumerate(qs)))
        print('    no episodes: ' + ' | '.join(f'Q{q + 1} {fd.cell(g)}' for q, g in enumerate(qs2)))
        print(f'    Q1 legs: {legs(qs[0])}\n    Q5 legs: {legs(qs[4])}')
    print('\n=== C. Inside D1 (fell most over 12 months): chance, terciles, bands ===')
    info1 = chance_block('inside D1', d1, LOW_MEASURES)
    print(f'  D1 reference: {legs(d1)}')
    print(f'  D1 without episodes: {legs(no_ep(d1))}')
    for m in LOW_MEASURES:
        x = np.array([r[m] for r in d1])
        cuts = np.quantile(x, [1 / 3, 2 / 3])
        lab = np.searchsorted(cuts, x, side='right')
        print(f'  {m} terciles inside D1 (cuts {cuts[0]:.3g} / {cuts[1]:.3g}):')
        for t in range(3):
            g = [r for r, l in zip(d1, lab) if l == t]
            print(f'     T{t + 1}: {legs(g)}  | no episodes: {mean_or_nan(no_ep(g)):+.3f} (n={len(no_ep(g))})')
    print('\n=== D. Fixed bands (whole cohort | inside D1) ===')
    bands = [('up_low <= 1 ATR', lambda r: r['up_low'] <= 1), ('up_low <= 2 ATR', lambda r: r['up_low'] <= 2), ('up_low <= 4 ATR', lambda r: r['up_low'] <= 4),
             ('up_low >= 4 ATR', lambda r: r['up_low'] >= 4), ('up_low >= 8 ATR', lambda r: r['up_low'] >= 8), ('up_low >= 12 ATR', lambda r: r['up_low'] >= 12),
             ('new-low flag (dsl <= 4)', lambda r: r['dsl'] <= 4), ('dsl >= 21', lambda r: r['dsl'] >= 21), ('dsl >= 63', lambda r: r['dsl'] >= 63),
             ('dsl >= 126', lambda r: r['dsl'] >= 126)]
    for name, f in bands:
        print(f'  {name}:\n      all: {legs([r for r in dev if f(r)])}\n      D1:  {legs([r for r in d1 if f(r)])}')
    print('\n=== E. Overlap: Spearman(measure, raw21 / raw252 / lead63) ===')
    for m in LOW_MEASURES:
        parts = []
        for o in ('raw21', 'raw252', 'lead63'):
            sub = [r for r in dev if m in r and o in r]
            rho = float(np.corrcoef(fd.rank_avg([r[m] for r in sub]), fd.rank_avg([r[o] for r in sub]))[0, 1]) if len(sub) > 30 else float('nan')
            parts.append(f'{o} {rho:+.2f}')
        print(f'  {m}: ' + ', '.join(parts))
    print('\n=== F. Does the bounce add to N + D1? (flag cohort; Lo / Hi = lowest / highest fifth of up_low in this cohort) ===')
    lo_cut, hi_cut = [float(np.quantile([r['up_low'] for r in coh], q)) for q in (0.2, 0.8)]
    for r in coh:
        r['Lo'], r['Hi'] = r['up_low'] <= lo_cut, r['up_low'] >= hi_cut
    print(f'  up_low cuts: lowest fifth <= {lo_cut:.3g} ATR, highest fifth >= {hi_cut:.3g} ATR')
    print('  reference by points (N + D1): ' + ' | '.join(f'{k}: {legs([r for r in coh if r["pts"] == k])}' for k in (0, 1, 2)))
    for k in (0, 1, 2):
        for nm in ('Lo', 'Hi'):
            a, b = [r for r in coh if r['pts'] == k and r[nm]], [r for r in coh if r['pts'] == k and not r[nm]]
            print(f'  points {k}, {nm}: with {legs(a)}\n             without {legs(b)}')
    for nm in ('Lo', 'Hi'):
        e1 = [r for r in d1 if r[nm] and r['entry'] < '2011-01-01']
        e2 = [r for r in d1 if r[nm] and r['entry'] >= '2011-01-01']
        print(f'  D1 and {nm} by era: 2006-10 {mean_or_nan(e1):+.3f} (n={len(e1)}) | 2011-20 {mean_or_nan(e2):+.3f} (n={len(e2)})')
    qb = QBoot(coh)
    qid = np.array([qb.qi[quarter(r['entry'])] for r in coh])
    X = np.array([[1.0, float(r['N']), float(r['D1']), float(r['Lo']), float(r['Hi'])] for r in coh])
    beta, lo, hi = qb.ols_ranges(X, np.array([r['excess_atr'] for r in coh]), qid)
    print('  regression excess = a + bN*N + bD*D1 + bLo*Lo + bHi*Hi (quarter-block 95%): ' +
          '; '.join(f'{nm} {beta[j]:+.3f} {fmt_range((lo[j], hi[j]))}' for j, nm in ((1, 'N'), (2, 'D1'), (3, 'Lo'), (4, 'Hi'))))
    print('\nQuestions asked on this cohort in this entry: 12 chance-tested statistics (6 whole cohort + 6 inside D1), plus descriptive quintiles, terciles, bands, '
          'overlaps and 1 regression. POST HOC.')


# ------------------------------------------------------------------ C21 scan
def load_dv(dv_folder, dev):
    dv = {}
    for p in sorted(Path(dv_folder).glob('dv_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            dv[(r['cik'], r['sym'], r['entry'])] = r
    out, miss = [], 0
    for r in dev:
        d = dv.get((r['cik'], r['sym'], r['entry']))
        if d is None or d.get('bars', 0) < 15 or 'dv_mean' not in d:
            miss += 1
            continue
        out.append({**r, 'dv_mean': d['dv_mean'], 'dv_median': d['dv_median']})
    print(f'development events {len(dev)}; with all 15 dollar-volume bars {len(out)}; without {miss}')
    return out


def band_rows(rs, lo, hi):
    return [r for r in rs if lo <= r['dv_mean'] < hi]


def dv_scan(dv_folder, decl, regime, ret):
    dev = load_dv(dv_folder, load_base(decl, regime, ret))
    print(f'development cohort n={len(dev)} excess {mean_or_nan(dev):+.3f}')
    coh, cn, cd = flag_cohort(dev)
    d1, nn = [r for r in coh if r['D1']], [r for r in coh if r['N']]
    print(f'  flag cohort n={len(coh)}; N cut {cn:+.4f}; D1 cut {cd:+.2f} ATR; D1 n={len(d1)}; N n={len(nn)}')
    print('\n=== A. Chance (excess shuffled inside the entry week): dv_mean and dv_median, 2 statistics each ===')
    chance_block('whole cohort', dev, DV_MEASURES)
    chance_block('inside D1', d1, DV_MEASURES)
    chance_block('inside N', nn, DV_MEASURES)
    print('\n=== B. Bands of 15-session average dollar volume ===')
    for name, grp in (('all events', dev), ('flag cohort', coh)):
        print(f'-- {name} --')
        for lab, lo, hi in DV_BANDS:
            print(f'   {lab:15s} {legs(band_rows(grp, lo, hi))}')
    print('\n=== C. Leads inside each band (flag cohort): D1 vs not-D1 and N vs not-N; difference with quarter-block range ===')
    qb = QBoot(coh)
    for flag, nm in (('D1', 'fell most over 12 months'), ('N', 'Nasdaq lagging')):
        print(f'-- {flag} ({nm}) --')
        for lab, lo, hi in DV_BANDS:
            g = band_rows(coh, lo, hi)
            a, b = [r for r in g if r[flag]], [r for r in g if not r[flag]]
            if len(a) >= 15 and len(b) >= 15:
                dr = fmt_range(qb.diff_range(a, b))
                diff = f'difference {mean_or_nan(a) - mean_or_nan(b):+.3f} {dr}'
            else:
                diff = 'difference n/a (a group under 15)'
            print(f'   {lab:15s} with flag {legs(a)}\n   {"":15s} without   {legs(b)}\n   {"":15s} {diff}')
    print('\n=== D. Liquidity floors on the leads (with | without the three large episodes) ===')
    for flag, grp in (('D1', d1), ('N', nn)):
        for floor in (0, 10e6, 25e6):
            g = [r for r in grp if r['dv_mean'] >= floor]
            print(f'  {flag}, dv_mean >= ${floor / 1e6:.0f}M: {legs(g)} | no episodes {mean_or_nan(no_ep(g)):+.3f} (n={len(no_ep(g))}); {len(g) / MONTHS:.2f} trades a month')
    print('\nQuestions asked on this cohort in this entry: 12 chance-tested statistics (4 whole cohort, 4 inside D1, 4 inside N), plus descriptive bands, '
          'differences and floors. POST HOC. Every event already passed the $3M floor; no spreads or market impact are measured.')


# ------------------------------------------------------------------ C22 scan
def did(rows, flag, b):
    """Difference in differences of mean excess: [(flag, b) - (flag, not b)] - [(not flag, b) - (not flag, not b)]; 0 if a cell is empty."""
    cells = {}
    for f in (True, False):
        for bb in (True, False):
            v = [x for (x, ff, bv) in rows if ff == f and bv == bb]
            if not v:
                return 0.0
            cells[(f, bb)] = sum(v) / len(v)
    return (cells[(True, True)] - cells[(True, False)]) - (cells[(False, True)] - cells[(False, False)])


def shift_did(coh, flags=('D1', 'N')):
    """Exact circular shift of B over the sorted entry dates. Returns observed, single-question chances, best-of-menu chance."""
    import numpy as np
    dates = sorted({r['entry'] for r in coh})
    nd = len(dates)
    pos = {d: k for k, d in enumerate(dates)}
    bser = np.array([next(r['B'] for r in coh if r['entry'] == d) for d in dates])
    di = np.array([pos[r['entry']] for r in coh])
    ex = [r['excess_atr'] for r in coh]
    fl = {f: [r[f] for r in coh] for f in flags}

    def stats_at(s):
        bv = bser[(di + s) % nd]
        return {f: did(list(zip(ex, fl[f], bv.tolist())), f, None) for f in flags}
    obs = stats_at(0)
    sims = {f: np.empty(nd - 1) for f in flags}
    for s in range(1, nd):
        d = stats_at(s)
        for f in flags:
            sims[f][s - 1] = abs(d[f])
    n = nd - 1
    srt = {f: np.sort(sims[f]) for f in flags}
    p1 = {f: float((n - np.searchsorted(srt[f], abs(obs[f]) - 1e-12, side='left') + 1) / (n + 1)) for f in flags}
    pmin = min(p1.values())
    perm = np.min(np.vstack([(n - np.searchsorted(srt[f], sims[f] - 1e-12, side='left') + 1) / (n + 1) for f in flags]), axis=0)
    best = float(((perm <= pmin + 1e-12).sum() + 1) / (n + 1))
    return obs, p1, best, pmin, nd


def gate(decl, regime, ret):
    dev = load_base(decl, regime, ret)
    dev = [r for r in dev if 'spyt200' in r]
    coh, cn, cd = flag_cohort(dev)
    # B must be a date-level series: one value per entry date
    for r in coh:
        r['B'] = r['spyt200'] < 0
    print(f'development events with SPY-200 feature {len(dev)}; flag cohort (lead63, raw252, spyt200) n={len(coh)}; N cut {cn:+.4f}; D1 cut {cd:+.2f} ATR')
    print(f'  all: {legs(coh)}\n  B (SPY below its 200-session average): {legs([r for r in coh if r["B"]])}\n  not B: {legs([r for r in coh if not r["B"]])}')
    qb = QBoot(coh)
    b_, nb_ = [r for r in coh if r['B']], [r for r in coh if not r['B']]
    print(f'  B minus not-B {mean_or_nan(b_) - mean_or_nan(nb_):+.3f} {fmt_range(qb.diff_range(b_, nb_))}')
    d2 = no_ep(coh)
    b2, nb2 = [r for r in d2 if r['B']], [r for r in d2 if not r['B']]
    print(f'  without episodes: B {legs(b2)}\n                    not B {legs(nb2)}')
    print('\n=== A. Two-by-two tables (excess; stock and SPY legs; n; weeks) ===')
    for flag, nm in (('D1', 'fell most over 12 months'), ('N', 'Nasdaq lagging')):
        print(f'-- {flag} ({nm}) x B --')
        for f in (True, False):
            for bb in (True, False):
                g = [r for r in coh if r[flag] == f and r['B'] == bb]
                g2 = no_ep(g)
                print(f'   {flag}={"yes" if f else "no ":3s} B={"below" if bb else "above"}: {legs(g)} | no episodes {mean_or_nan(g2):+.3f} (n={len(g2)}) | spells {len(spells(sorted({r["entry"] for r in g})))}')
        for f in (True, False):
            a = [r for r in coh if r[flag] == f and r['B']]
            b = [r for r in coh if r[flag] == f and not r['B']]
            if len(a) >= 15 and len(b) >= 15:
                print(f'   within {flag}={"yes" if f else "no"}: below minus above {mean_or_nan(a) - mean_or_nan(b):+.3f} {fmt_range(qb.diff_range(a, b))}')
    print('-- points (N + D1) x B --')
    for k in (0, 1, 2):
        for bb in (True, False):
            g = [r for r in coh if r['pts'] == k and r['B'] == bb]
            print(f'   points {k}, B={"below" if bb else "above"}: {legs(g)}')
    print('\n=== B. By era (flag D1 and B) ===')
    for lab, f in (('2006-10', lambda r: r['entry'] < '2011-01-01'), ('2011-20', lambda r: r['entry'] >= '2011-01-01')):
        for flag in ('D1', 'N'):
            a = [r for r in coh if f(r) and r[flag] and r['B']]
            b = [r for r in coh if f(r) and r[flag] and not r['B']]
            print(f'   {lab} {flag}: below {mean_or_nan(a):+.3f} (n={len(a)}) | above {mean_or_nan(b):+.3f} (n={len(b)})')
    print('\n=== C. Entry 36 crossing restated (stock lower half of raw252 x SPY down over the same 252 sessions, spy252 < 0), for comparison ===')
    med = statistics.median(r['raw252'] for r in coh)
    for lab, lowhalf in (('lower half', True), ('upper half', False)):
        for sd in (True, False):
            g = [r for r in coh if (r['raw252'] <= med) == lowhalf and r.get('spy252') is not None and (r['spy252'] < 0) == sd]
            print(f'   stock {lab}, SPY {"down" if sd else "up"} over 252: {legs(g)}')
    print('\n=== D. Chance: circular shift of B over entry dates (difference-in-differences, 2 statistics) ===')
    obs, p1, best, pmin, nd = shift_did(coh)
    print(f'  entry dates {nd}; ' + '; '.join(f'DiD_{f} {obs[f]:+.3f} (chance alone {p1[f]:.1%})' for f in obs) +
          f'; smallest {pmin:.1%}; chance the best of 2 is at least that small by luck {best:.1%}')
    print('\nQuestions asked on this cohort in this entry: 2 chance-tested statistics, plus descriptive 2x2 tables, era splits and the Entry 36 restatement. POST HOC. '
          'B is a date-level series with few independent stretches (read the spell counts).')


# ------------------------------------------------------------------ self-test
def selftest():
    import random
    from datetime import date
    ds, d = [], date(2010, 1, 4)
    while len(ds) < 330:
        if d.weekday() < 5:
            ds.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)

    def mk(prices):
        return {x: (p, p + 1, p - 1, p) for x, p in zip(ds, prices)}
    # falls to a low at session 290, then bounces 10 points
    px = [300 - k for k in range(291)] + [10 + 2 * j for j in range(1, 40)]
    stock = mk(px)
    e = ds[300]                                                    # entry index 300; last completed session 299
    f = low_features(ds, stock, e)
    assert f['status'] == 'ok' and abs(f['up_pct'] - (px[299] / px[290] - 1)) < 1e-12
    assert f['dsl'] == 9.0 and abs(f['up_low'] - (px[299] - px[290]) / f['atr']) < 1e-9
    # window is the 252 sessions before entry: the high-priced start (sessions < 48) is outside it
    assert LOW_W == 252
    # lowest close in the last session -> dsl 0, up_low 0
    g = low_features(ds, stock, ds[291])
    assert g['dsl'] == 0.0 and g['up_low'] == 0.0 and g['up_pct'] == 0.0
    # no lookahead: changing the entry day and later changes nothing
    alt = dict(stock)
    for x in ds[300:]:
        alt[x] = (1, 2, 0.5, 1)
    assert low_features(ds, alt, e) == f
    # short history leaves the low features blank
    assert 'up_low' not in low_features(ds, stock, ds[100]) and 'up_low' not in low_features(ds, stock, ds[200])
    try:
        low_features(ds, stock, '2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    # difference in differences
    rows = [(1.0, True, True)] * 3 + [(0.0, True, False)] * 3 + [(0.0, False, True)] * 3 + [(0.0, False, False)] * 3
    assert abs(did(rows, 'D1', None) - 1.0) < 1e-12 and did(rows[:6], 'D1', None) == 0.0
    # circular shift: planted interaction is detected, null is not
    rng = random.Random(7)
    coh = []
    for k in range(600):
        day = date.fromordinal(date(2008, 1, 1).toordinal() + k // 2).isoformat()
        bser = ((k // 2) // 40) % 2 == 0                       # long stretches
        d1 = rng.random() < 0.3
        coh.append({'entry': day, 'D1': d1, 'N': rng.random() < 0.3, 'B': bser, 'excess_atr': (1.5 if (d1 and bser) else 0.0) + rng.gauss(0, 1)})
    obs, p1, best, pmin, nd = shift_did(coh)
    assert obs['D1'] > 1.0 and abs(obs['N']) < 1.0 and nd == 300
    assert p1['D1'] < 0.2                                            # few independent stretches: even a planted effect has a large circular-shift p
    # band helper
    assert [r['dv_mean'] for r in band_rows([{'dv_mean': 4e6}, {'dv_mean': 5e6}, {'dv_mean': 9e6}], 5e6, 10e6)] == [5e6, 9e6]
    print('context_scan self-test passed')


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
    if a.cmd == 'lowyear':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'bounce':
        bounce(a.arg, a.arg2, a.arg3, a.arg4)
    elif a.cmd == 'dv':
        dv_scan(a.arg, a.arg2, a.arg3, a.arg4)
    elif a.cmd == 'gate':
        gate(a.arg, a.arg2, a.arg3)
    else:
        raise SystemExit(__doc__)
