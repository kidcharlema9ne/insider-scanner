"""Decline-bucket scan (POST HOC, asked by Michael 8 Nov 2026): how big was the fall before entry, and what did the next 21 sessions pay?

Question: for look-backs of 1, 3, 6, 9 and 12 months (21, 63, 126, 189, 252 completed sessions before the entry session), group the
refined primary entries (Entry 28 cohort) by how far the stock had fallen, and show the 21-session excess over same-window SPY
(stock's ATR units, stock and SPY legs beside it, D-053) for each group. Development years only (entries <= 2020-12-31, D-068);
the 2026 pilot is not used. No sealed return is read. 21-session returns are the Entry 28 results (run 42490748366), unchanged.

Features: Entry 36 features (run 42499472150) hold raw/pct for 21, 63, 126, 252. 9 months (189) was never computed, so the `year`
command recomputes the SAME `factor_decline.features()` code with the window list patched to (189, 252); the 252 values are
compared with the Entry 36 file as a reproduction check (any difference is printed and the run is PROVISIONAL).

Two unit families (Michael did not say whether his 0-2 / 2-4 / ... meant percent or ATR, so both are declared):
  ATR family      D = -(last close - close W sessions earlier) / entry ATR  (ATR = 14 completed sessions before entry, as Entry 28).
                  Buckets (lo < D <= hi): up (D <= 0, not down) | 0-2 | 2-4 | 4-6 | 6-8 | 8-10 | 10-15 | 15-20 | 20+          9 buckets
  Percent family  D = -(last close / close W sessions earlier - 1) * 100.
                  Buckets: up | 0-2 | 2-4 | 4-6 | 6-9 | 9-12 | 12-20 | 20-35 | 35-50 | 50+                                   10 buckets
Windows: 5 (21, 63, 126, 189, 252). Cells: 9*5 + 10*5 = 95.  Edges are fixed here, before any bucket mean is computed.

Menu (the chance test covers exactly this): for every cell with n >= 30, z = (mean excess in the cell - mean excess of all other
events in the same family/window cohort) / (s * sqrt(1/n_cell + 1/n_rest)), s = sd of excess over the whole cohort. Chance = excess
shuffled inside the same entry week (10,000 draws, as Entry 36); two-sided. Reported per cell (single question) and as the best of
all included cells (chance that the largest |z| of the menu is at least the observed one by luck), overall and per family.
Cells with n < 30 are printed but excluded from the menu.
Descriptive only (not in the chance menu): per-cell n, entry weeks, separate entry spells (gap > 42 calendar days), median, share
beating SPY, mean without 2008Q4 / 2011Q3 / 2020Q1, means for entries 2006-2010 vs 2011-2020, quarter-block 95% range (10,000
resamples of quarters); "down at least X" cumulative table (X = 2, 4, 6, 8, 10, 15, 20 ATR); compact window-by-bucket grids.

Cohort: Entry 28 development events that have the 21-session return and the measure for that window (windows reaching before the
first archived session are blank). Different windows therefore have slightly different n; the all-event mean is printed per window.

Cautions written in advance: buckets within a window are nested in time with the other windows (same stocks fall for all
look-backs), so cells are strongly correlated; the 12-month result is the Entry 36 lead seen in finer slices; the deepest buckets
are where Entries 38/40/44 say price series are most likely missing (survivorship); costs are not in any number (Entry 45).
A bucket picked because it looks best after this run is a lead, not a rule.

Usage:  python decline_buckets.py year YEAR --primary FILE --out FILE   |   scan DECLINE_FOLDER F189_FOLDER RETURNS_FOLDER   |   --selftest
"""
import argparse, json, statistics, sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
from refined_baseline import DEV_END, EPISODES, assert_allowed, quarter
from factor_regime import spells

WINDOWS = (21, 63, 126, 189, 252)
LABEL = {21: '1m', 63: '3m', 126: '6m', 189: '9m', 252: '12m'}
SEED = 20261108
MIN_N = 30
ATR_EDGES = [(None, 0, 'up'), (0, 2, '0-2'), (2, 4, '2-4'), (4, 6, '4-6'), (6, 8, '6-8'), (8, 10, '8-10'),
             (10, 15, '10-15'), (15, 20, '15-20'), (20, None, '20+')]
PCT_EDGES = [(None, 0, 'up'), (0, 2, '0-2'), (2, 4, '2-4'), (4, 6, '4-6'), (6, 9, '6-9'), (9, 12, '9-12'),
             (12, 20, '12-20'), (20, 35, '20-35'), (35, 50, '35-50'), (50, None, '50+')]
FAMILIES = {'ATR': ('raw', -1.0, ATR_EDGES), 'PCT': ('pct', -100.0, PCT_EDGES)}
CUM_ATR = (2, 4, 6, 8, 10, 15, 20)


def decline(r, fam, W):
    key, sign, _ = FAMILIES[fam]
    v = r.get(f'{key}{W}')
    return None if v is None else sign * v


def in_bucket(d, lo, hi):
    """lo < d <= hi; 'up' bucket has lo None and hi 0 (d <= 0); top bucket has hi None."""
    if lo is None:
        return d <= hi
    return d > lo and (hi is None or d <= hi)


# ------------------------------------------------------------------ features for 9 months
def year_job(year, primary, out):
    fd.WINDOWS = (189, 252)                    # same features() code, window list patched; year_job reads module globals at call time
    fd.year_job(year, primary, out)


# ------------------------------------------------------------------ loading
def load(decline_folder, f189_folder, returns_folder):
    rows = fd.load(decline_folder, returns_folder)
    new = {}
    for p in sorted(Path(f189_folder).glob('*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            new[(r['cik'], r['sym'], r['entry'])] = r
    dev, mism, nof = [], 0, 0
    for r in rows:
        if r['entry'] > DEV_END:
            continue
        f = new.get((r['cik'], r['sym'], r['entry']))
        if not f or f['status'] != 'ok':
            nof += 1
        else:
            for k in ('raw189', 'pct189'):
                if k in f:
                    r[k] = f[k]
            for k in ('raw252', 'pct252'):                          # reproduction check against Entry 36 features
                if (k in f) != (k in r) or (k in f and abs(f[k] - r[k]) > 1e-9):
                    mism += 1
        dev.append(r)
    print(f'development rows with a 21-session return and Entry 36 features: {len(dev)}; no 9-month feature row: {nof}; '
          f'raw252/pct252 differences between the new and the Entry 36 file: {mism}')
    return dev, mism


# ------------------------------------------------------------------ statistics
def cell_stats(rs):
    ex = [r['excess_atr'] for r in rs]
    ds = sorted(r['entry'] for r in rs)
    return {'n': len(rs), 'weeks': len({fd.week_of(r) for r in rs}), 'spells': len(spells(ds)) if ds else 0,
            'ex': statistics.fmean(ex) if ex else float('nan'), 'st': statistics.fmean(r['stock_atr'] for r in rs) if rs else float('nan'),
            'sp': statistics.fmean(r['spy_atr'] for r in rs) if rs else float('nan'),
            'med': statistics.median(ex) if ex else float('nan'), 'beat': sum(e > 0 for e in ex) / len(ex) if ex else float('nan')}


def fmt(c):
    if c['n'] == 0:
        return 'n=0'
    return (f'n={c["n"]:4d} w={c["weeks"]:3d} sp={c["spells"]:2d}  excess {c["ex"]:+.3f} (stock {c["st"]:+.3f}, SPY {c["sp"]:+.3f})  '
            f'median {c["med"]:+.3f}  beat SPY {c["beat"]:.0%}')


def mean_or_nan(rs):
    return statistics.fmean(r['excess_atr'] for r in rs) if rs else float('nan')


def scan_cells(dev):
    """Returns list of cells: dict(fam, W, name, idx(list of dev indices))."""
    cells = []
    for fam, (_, _, edges) in FAMILIES.items():
        for W in WINDOWS:
            have = [k for k, r in enumerate(dev) if decline(r, fam, W) is not None]
            for lo, hi, name in edges:
                idx = [k for k in have if in_bucket(decline(dev[k], fam, W), lo, hi)]
                cells.append({'fam': fam, 'W': W, 'name': name, 'idx': idx, 'have': have})
    return cells


def chance(dev, cells, draws=10000):
    """Within-week shuffle of excess. z per included cell vs the rest of its (family, window) cohort. Returns obs z, single p, best-of p."""
    import numpy as np
    n = len(dev)
    ex = np.array([r['excess_atr'] for r in dev])
    wk = {w: i for i, w in enumerate(sorted({fd.week_of(r) for r in dev}))}
    wi = np.array([wk[fd.week_of(r)] for r in dev])
    inc = [c for c in cells if len(c['idx']) >= MIN_N and len(c['have']) - len(c['idx']) >= MIN_N]
    M = np.zeros((len(inc), n))
    H = np.zeros((len(inc), n))                       # cohort membership (events having the measure)
    for j, c in enumerate(inc):
        M[j, c['idx']] = 1.0
        H[j, c['have']] = 1.0
    nb, nh = M.sum(1), H.sum(1)
    nr = nh - nb
    s = np.array([ex[c['have']].std(ddof=1) for c in inc])

    def zvec(e):
        sb, sh = M @ e, H @ e
        return ((sb / nb) - ((sh - sb) / nr)) / (s * np.sqrt(1 / nb + 1 / nr))
    obs = zvec(ex)
    rng = np.random.default_rng(SEED)
    fam_ix = {f: np.array([j for j, c in enumerate(inc) if c['fam'] == f]) for f in FAMILIES}
    cnt = np.zeros(len(inc))
    maxall, maxfam = np.empty(draws), {f: np.empty(draws) for f in FAMILIES}
    for k in range(draws):
        order = np.lexsort((rng.random(n), wi))
        z = np.abs(zvec(ex[order]))
        cnt += z >= np.abs(obs) - 1e-12
        maxall[k] = z.max()
        for f, ix in fam_ix.items():
            maxfam[f][k] = z[ix].max()
    single = cnt / draws
    best_all = (maxall[:, None] >= np.abs(obs)[None, :] - 1e-12).mean(0)
    best_fam = np.empty(len(inc))
    for f, ix in fam_ix.items():
        best_fam[ix] = (maxfam[f][:, None] >= np.abs(obs[ix])[None, :] - 1e-12).mean(0)
    out = {}
    for j, c in enumerate(inc):
        out[(c['fam'], c['W'], c['name'])] = (float(obs[j]), float(single[j]), float(best_fam[j]), float(best_all[j]))
    return out, len(inc)


def quarter_ranges(dev, cells, draws=10000):
    import numpy as np
    qs = sorted({quarter(r['entry']) for r in dev})
    qi = {q: i for i, q in enumerate(qs)}
    ex = np.array([r['excess_atr'] for r in dev])
    qv = np.array([qi[quarter(r['entry'])] for r in dev])
    rng = np.random.default_rng(SEED + 1)
    Wt = rng.multinomial(len(qs), [1 / len(qs)] * len(qs), size=draws).astype(float)
    out = {}
    for c in cells:
        if len(c['idx']) < MIN_N:
            continue
        S, N = np.zeros(len(qs)), np.zeros(len(qs))
        for k in c['idx']:
            S[qv[k]] += ex[k]
            N[qv[k]] += 1
        num, den = Wt @ S, Wt @ N
        ok = den > 0
        m = num[ok] / den[ok]
        out[(c['fam'], c['W'], c['name'])] = (float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975)))
    return out


def scan(decline_folder, f189_folder, returns_folder):
    dev, mism = load(decline_folder, f189_folder, returns_folder)
    allmean = mean_or_nan(dev)
    print(f'development n={len(dev)} excess {allmean:+.3f} (Entry 28: n={fd.EXPECT_DEV}, +{fd.EXPECT_MEAN})')
    if len(dev) != fd.EXPECT_DEV or abs(allmean - fd.EXPECT_MEAN) > 0.0006 or mism:
        print('WARNING: cohort or features do not reproduce Entry 28 / Entry 36 exactly; treat everything below as PROVISIONAL until explained')
    dev.sort(key=fd.week_of)
    cells = scan_cells(dev)
    print('\n=== A. Coverage: events with the measure, and all-event mean excess over that cohort ===')
    for W in WINDOWS:
        have = [r for r in dev if f'raw{W}' in r]
        print(f'{LABEL[W]} ({W} sessions): n={len(have)}, excess {mean_or_nan(have):+.3f}, stock {statistics.fmean(r["stock_atr"] for r in have):+.3f}, '
              f'SPY {statistics.fmean(r["spy_atr"] for r in have):+.3f}')
    print(f'\nRunning chance test over the menu (cells with n >= {MIN_N} in the bucket and in the rest; 10,000 within-week shuffles)...')
    ch, ninc = chance(dev, cells)
    rng_ = quarter_ranges(dev, cells)
    print(f'Menu size: {ninc} cells included of {len(cells)} declared.')
    early = [r for r in dev if r['entry'] < '2011-01-01']
    late = [r for r in dev if r['entry'] >= '2011-01-01']
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    print('\n=== B. Every cell (excess over same-window SPY in ATR; stock and SPY legs; w = entry weeks; sp = separate entry spells) ===')
    for fam in FAMILIES:
        for W in WINDOWS:
            print(f'\n-- {fam} family, {LABEL[W]} look-back ({W} sessions); D = how far the stock fell ({"ATR" if fam == "ATR" else "percent"}) --')
            for c in [c for c in cells if c['fam'] == fam and c['W'] == W]:
                rs = [dev[k] for k in c['idx']]
                key = (fam, W, c['name'])
                st = fmt(cell_stats(rs))
                if not rs:
                    print(f'  {c["name"]:>6}: n=0')
                    continue
                ids = set(c['idx'])
                ne = [dev[k] for k in c['idx'] if quarter(dev[k]['entry']) not in EPISODES]
                e1 = [r for r in rs if r['entry'] < '2011-01-01']
                e2 = [r for r in rs if r['entry'] >= '2011-01-01']
                tail = f'no-episodes {mean_or_nan(ne):+.3f} (n={len(ne)}) | 2006-10 {mean_or_nan(e1):+.3f} (n={len(e1)}) | 2011-20 {mean_or_nan(e2):+.3f} (n={len(e2)})'
                if key in ch:
                    z, p1, pf, pa = ch[key]
                    lo, hi = rng_[key]
                    tail += f' | z {z:+.2f}, chance alone {p1:.1%}, best-of-family {pf:.1%}, best-of-all {pa:.1%} | quarter-block range [{lo:+.3f}, {hi:+.3f}]'
                else:
                    tail += ' | thin cell, not in menu'
                print(f'  {c["name"]:>6}: {st}\n          {tail}')
    print('\n=== C. Compact grids: mean excess (n) by bucket and look-back ===')
    for fam, (_, _, edges) in FAMILIES.items():
        print(f'-- {fam} family --   ' + ''.join(f'{LABEL[W]:>16}' for W in WINDOWS))
        for lo, hi, name in edges:
            line = f'{name:>6}        '
            for W in WINDOWS:
                c = next(c for c in cells if c['fam'] == fam and c['W'] == W and c['name'] == name)
                rs = [dev[k] for k in c['idx']]
                line += f'{(f"{mean_or_nan(rs):+.2f} ({len(rs)})" if rs else "-"):>16}'
            print(line)
    print('\n=== D. Down at least X ATR (cumulative, descriptive) ===')
    for W in WINDOWS:
        parts = []
        for x in CUM_ATR:
            rs = [r for r in dev if f'raw{W}' in r and -r[f'raw{W}'] >= x]
            parts.append(f'>={x}: {mean_or_nan(rs):+.2f} (n={len(rs)})' if rs else f'>={x}: n=0')
        print(f'{LABEL[W]}: ' + ' | '.join(parts))
    print('\n=== E. Menu summary: strongest cells by |z| (menu cells only) ===')
    top = sorted(ch.items(), key=lambda kv: -abs(kv[1][0]))[:12]
    for (fam, W, name), (z, p1, pf, pa) in top:
        c = next(c for c in cells if c['fam'] == fam and c['W'] == W and c['name'] == name)
        print(f'{fam} {LABEL[W]} down {name}: {fmt(cell_stats([dev[k] for k in c["idx"]]))} | z {z:+.2f}, alone {p1:.1%}, best-of-family {pf:.1%}, best-of-{ninc} {pa:.1%}')
    zs = sorted(ch.values(), key=lambda v: -abs(v[0]))
    print(f'Largest |z| in the menu {abs(zs[0][0]):.2f}; chance that the largest of {ninc} is at least that big by luck {zs[0][3]:.1%}.')
    print(f'\nQuestions asked on this cohort in this entry: {ninc} cell z-tests (menu) plus descriptive cell tables, grids and the cumulative table. POST HOC.')


# ------------------------------------------------------------------ self-test
def selftest():
    import random
    assert in_bucket(-3, None, 0) and in_bucket(0, None, 0) and not in_bucket(0.1, None, 0)
    assert in_bucket(0.5, 0, 2) and in_bucket(2, 0, 2) and not in_bucket(2.01, 0, 2) and not in_bucket(0, 0, 2)
    assert in_bucket(99, 50, None) and not in_bucket(50, 50, None)
    # every value lands in exactly one bucket of each family
    for fam, (_, _, edges) in FAMILIES.items():
        for v in (-5, 0, 0.01, 2, 3, 6, 9, 10, 12, 20, 35, 50, 51, 500):
            assert sum(in_bucket(v, lo, hi) for lo, hi, _ in edges) == 1, (fam, v)
    r = {'raw21': -3.0, 'pct21': -0.07}
    assert decline(r, 'ATR', 21) == 3.0 and abs(decline(r, 'PCT', 21) - 7.0) < 1e-9 and decline(r, 'ATR', 63) is None
    # chance machinery: a built-in effect in one bucket is found, noise is not
    rng = random.Random(5)
    rows = []
    for k in range(600):
        d = abs(rng.gauss(0, 4))
        e = (1.5 if 4 < d <= 6 else 0.0) + rng.gauss(0, 1)
        rows.append({'entry': f'2010-{1 + k % 12:02d}-{1 + k % 27:02d}', 'cik': str(k), 'sym': 'X', 'excess_atr': e, 'stock_atr': e, 'spy_atr': 0.0,
                     **{f'raw{w}': -d for w in WINDOWS}, **{f'pct{w}': -d / 40 for w in WINDOWS}})
    rows.sort(key=fd.week_of)
    cells = scan_cells(rows)
    ch, ninc = chance(rows, cells, 300)
    z, p1, pf, pa = ch[('ATR', 63, '4-6')]
    assert z > 4 and p1 < 0.01 and pa < 0.05, (z, p1, pa)
    null = [{**r_, 'excess_atr': rng.gauss(0, 1)} for r_ in rows]
    chn, _ = chance(null, scan_cells(null), 300)
    assert min(v[3] for v in chn.values()) > 0.05
    q = quarter_ranges(rows, cells, 300)
    lo, hi = q[('ATR', 63, '4-6')]
    assert 0.5 < lo < hi
    try:
        assert_allowed('2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    print('decline_buckets self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('arg3', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'scan':
        scan(a.arg, a.arg2, a.arg3)
    else:
        raise SystemExit(__doc__)
