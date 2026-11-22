"""Base scan (C23, POST HOC, Michael's idea 8 Nov 2026): inside the deep-fall group (D1), did the stock stop falling, consolidate, and then move up?

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used. No sealed return is read.

STAGE 1 (this script, `basedist`): features and distributions ONLY. No return of any kind is joined or printed. The purpose is to choose the cutoffs for
'tight and choppy' from the feature distributions alone, write them down, and only then (stage 2, a later entry) join the 21-session excess.

Features, measured from sessions strictly before the entry session (the last completed session is entry index i-1; the breakout window is the 5 sessions
i-5 .. i-1; the base window is the W sessions i-5-W .. i-6 that end just before it). W = 10, 20, 40, 60.
  width_W   = (highest high - lowest low of the base) / entry ATR.  Small = tight box. A new 252-session low INSIDE the base is allowed: it only sets the
              bottom of the box.
  eff_W     = |last close of the base - first close of the base| / sum of the absolute daily close changes inside the base.  1 = straight line, 0 = round trip.
              Low = choppy / sideways, whatever happened to the lows.
  topgap_W  = (last completed close - highest close of the base) / entry ATR.  > 0 means the stock closed above the top of the box (a breakout);
              <= 0 means it has not.
A window needs 80% valid bars. Entry ATR = mean true range of the 14 completed sessions before entry (identical to Entry 28).
D1 = raw252 <= -15.32 ATR (the fell-most-fifth cut of Entries 51-53; raw252 comes from the Entry 36 feature files, which hold no returns).
Stage 1 prints, for the whole development cohort and for D1: coverage; quantiles (10/25/33/50/67/75/90%) of width, eff and topgap per window; the share with
topgap > 0; Spearman between width and eff; the 3 x 3 count table of width tercile by eff tercile inside D1; and the number of D1 events in each state at the
tentative cutoffs (tight = lowest third of width AND lowest third of eff, both computed inside D1; breakout = topgap > 0):
   state 1 not basing    state 2 basing, no breakout    state 3 basing then breakout.
States are defined for every window. Nothing here depends on a return.
Stage 2 (later entry, cutoffs written first): excess over same-window SPY by state for each window, week-shuffle chance, with and without the three large
episodes, 2006-10 vs 2011-20, stock and SPY legs.
Cautions written in advance: D1 is 255 events, so three states leave roughly 50-100 each; four windows multiply the questions asked; the base windows overlap
(a 40-session base contains the 20-session base); costs and survivorship (Entries 38, 40, 44, 45) are not in any number.

STAGE 2 (`stage2`, cutoffs declared in research_docs/CANDIDATES.md C23 before any return was joined): inside D1 of the flag cohort (Entries 51-58; returns Entry 28,
decline features Entry 36, lead63 Entry 37) join the 21-session excess over same-window SPY (ATR; stock and SPY legs shown). For each W in 10, 20, 40, 60:
BASING-TIGHT = eff_W in the lowest third inside D1, BASING-LOOSE = lowest two thirds, MOVED-UP = topgap_W >= -1 ATR. States 1 not basing, 2 basing and not
moved up, 3 basing and moved up. Chance menu = 12 statistics (flag minus not-flag mean excess for BASING-TIGHT, BASING-LOOSE, MOVED-UP x 4 windows), excess
shuffled inside the entry week, 10,000 draws, single-question and best of 12. Descriptive: state tables, quarter-block ranges, without the three large
episodes, 2006-10 vs 2011-20, and the width-based and width-plus-choppiness definitions of stage 1.

Usage:  python base_scan.py baseyear YEAR --primary FILE --out FILE   |   basedist BASE_FOLDER DECLINE_FOLDER   |   stage2 BASE_FOLDER DECLINE REGIME RETURNS   |   --selftest
"""
import argparse, json, sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
from refined_baseline import ATR_BARS, DEV_END, assert_allowed, load_span, true_range

WINDOWS = (10, 20, 40, 60)
BREAK_N = 5
D1_CUT = -15.32
QUANTS = (0.10, 0.25, 1 / 3, 0.50, 2 / 3, 0.75, 0.90)


def base_features(dates, stock, entry):
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
    for W in WINDOWS:
        lo_i = i - BREAK_N - W
        if lo_i < 0:
            continue
        base = [stock[d] for d in dates[lo_i:i - BREAK_N] if d in stock]
        if len(base) < 0.8 * W or len(base) < 3:
            continue
        closes = [b[3] for b in base]
        path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
        out[f'width{W}'] = (max(b[1] for b in base) - min(b[2] for b in base)) / atr
        out[f'eff{W}'] = abs(closes[-1] - closes[0]) / path if path > 0 else 0.0
        out[f'topgap{W}'] = (last - max(closes)) / atr
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
            r = base_features(dates, series, e['entry'])
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))) + '; coverage ' +
          ', '.join(f'W{W} {sum(f"width{W}" in r for r in rows)}' for W in WINDOWS))


# ------------------------------------------------------------------ stage 1: distributions, no returns
def load_features(base_folder, decline_folder):
    base = {}
    for p in sorted(Path(base_folder).glob('base_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            base[(r['cik'], r['sym'], r['entry'])] = r
    rows, miss = [], Counter()
    for p in sorted(Path(decline_folder).glob('decline_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            if r['entry'] > DEV_END or r['status'] != 'ok' or 'raw252' not in r:
                continue
            b = base.get((r['cik'], r['sym'], r['entry']))
            if not b or b['status'] != 'ok':
                miss[b['status'] if b else 'no_base_row'] += 1
                continue
            rows.append({'entry': r['entry'], 'sym': r['sym'], 'cik': r['cik'], 'raw252': r['raw252'], 'atr': r['atr'],
                         **{k: v for k, v in b.items() if k.startswith(('width', 'eff', 'topgap'))}})
    print(f'development events with Entry 36 raw252 and base features: {len(rows)}; without: {dict(miss)}')
    return rows


def qline(v):
    import numpy as np
    return '  '.join(f'{int(round(q * 100))}%={x:.3g}' for q, x in zip(QUANTS, np.quantile(v, QUANTS)))


def tercile_label(x, cuts):
    return 0 if x <= cuts[0] else (1 if x <= cuts[1] else 2)


def stage1(base_folder, decline_folder):
    import numpy as np
    rows = load_features(base_folder, decline_folder)
    d1 = [r for r in rows if r['raw252'] <= D1_CUT]
    print(f'whole development cohort n={len(rows)}; D1 (raw252 <= {D1_CUT}) n={len(d1)}')
    for W in WINDOWS:
        print(f'\n=== Window W={W} (base = sessions i-{BREAK_N + W} .. i-{BREAK_N + 1}; breakout window = last {BREAK_N} sessions) ===')
        allw = [r for r in rows if f'width{W}' in r]
        dd = [r for r in d1 if f'width{W}' in r]
        print(f'coverage: whole {len(allw)} of {len(rows)}; D1 {len(dd)} of {len(d1)}')
        if len(dd) < 30:
            print('  too few D1 events with this window'); continue
        for nm, grp in (('whole cohort', allw), ('D1', dd)):
            print(f'  {nm} (n={len(grp)}):')
            for m in ('width', 'eff', 'topgap'):
                print(f'     {m}{W}: ' + qline([r[f'{m}{W}'] for r in grp]))
            print(f'     share with topgap > 0 (closed above the top of the box): {sum(r[f"topgap{W}"] > 0 for r in grp) / len(grp):.1%}')
        rw, re_ = fd.rank_avg([r[f'width{W}'] for r in dd]), fd.rank_avg([r[f'eff{W}'] for r in dd])
        print(f'  Spearman width vs eff inside D1: {float(np.corrcoef(rw, re_)[0, 1]):+.2f}')
        cw = np.quantile([r[f'width{W}'] for r in dd], [1 / 3, 2 / 3])
        ce = np.quantile([r[f'eff{W}'] for r in dd], [1 / 3, 2 / 3])
        print(f'  D1 tercile cuts: width {cw[0]:.3g} / {cw[1]:.3g}; eff {ce[0]:.3g} / {ce[1]:.3g}')
        tab = Counter((tercile_label(r[f'width{W}'], cw), tercile_label(r[f'eff{W}'], ce)) for r in dd)
        print('  count table inside D1 (rows = width tercile tight/mid/wide; columns = eff tercile choppy/mid/trending):')
        for a, nm in enumerate(('tight', 'mid  ', 'wide ')):
            print(f'     {nm}  ' + '  '.join(f'{tab[(a, b)]:4d}' for b in range(3)))
        st = Counter()
        for r in dd:
            tight = r[f'width{W}'] <= cw[0] and r[f'eff{W}'] <= ce[0]
            st[1 if not tight else (3 if r[f'topgap{W}'] > 0 else 2)] += 1
        print(f'  tentative states inside D1: 1 not basing {st[1]}; 2 basing, no breakout {st[2]}; 3 basing then breakout {st[3]}')
        loose = Counter()
        for r in dd:
            tight = r[f'width{W}'] <= cw[1] and r[f'eff{W}'] <= ce[1]
            loose[1 if not tight else (3 if r[f'topgap{W}'] > 0 else 2)] += 1
        print(f'  looser states (lowest TWO thirds of both): 1 not basing {loose[1]}; 2 basing, no breakout {loose[2]}; 3 basing then breakout {loose[3]}')
    print('\nNo return was joined or printed in this stage. Cutoffs for stage 2 are to be chosen from the tables above and written in the log before any return is read.')


# ------------------------------------------------------------------ stage 2: returns joined, cutoffs declared in CANDIDATES.md
def read_base(base_folder):
    base = {}
    for p in sorted(Path(base_folder).glob('base_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            base[(r['cik'], r['sym'], r['entry'])] = r
    return base


def diff_stats(ex, wi, flags, draws=10000, seed=fd.SEED):
    """flags: (n, k) bool. Returns observed flag-minus-rest mean differences, single chances (two-sided) and best-of-k chance."""
    import numpy as np
    F = flags.astype(float)
    nf, nr = F.sum(0), (1 - F).sum(0)

    def stat(e):
        return (F * e[:, None]).sum(0) / np.maximum(nf, 1) - ((1 - F) * e[:, None]).sum(0) / np.maximum(nr, 1)
    obs = stat(ex)
    rng = np.random.default_rng(seed)
    sim = np.empty((draws, flags.shape[1]))
    for k in range(draws):
        order = np.lexsort((rng.random(len(ex)), wi))
        sim[k] = np.abs(stat(ex[order]))
    srt = np.sort(sim, axis=0)
    obs_abs = np.abs(obs)
    p1 = np.array([1.0 - np.searchsorted(srt[:, c], obs_abs[c] - 1e-12, side='left') / draws for c in range(flags.shape[1])])
    pmat = np.empty_like(sim)
    for c in range(flags.shape[1]):
        pmat[:, c] = 1.0 - np.searchsorted(srt[:, c], sim[:, c] - 1e-12, side='left') / draws
    best = float((pmat.min(axis=1) <= p1.min() + 1e-12).mean())
    return obs, p1, best


def stage2(base_folder, decl, regime, ret):
    import numpy as np
    import context_scan as cs
    from oversold_scan import legs, mean_or_nan
    from score_scan import QBoot
    from refined_baseline import quarter
    dev = cs.load_base(decl, regime, ret)
    coh, cn, cd = cs.flag_cohort(dev)
    base = read_base(base_folder)
    d1, miss = [], 0
    for r in coh:
        if not r['D1']:
            continue
        b = base.get((r['cik'], r['sym'], r['entry']))
        if not b or b['status'] != 'ok' or any(f'eff{W}' not in b for W in WINDOWS):
            miss += 1
            continue
        d1.append({**r, **{k: v for k, v in b.items() if k.startswith(('width', 'eff', 'topgap'))}})
    d1.sort(key=fd.week_of)
    print(f'flag cohort n={len(coh)} (N cut {cn:+.4f}, D1 cut {cd:+.2f} ATR); D1 with all four base windows n={len(d1)} (missing {miss}); D1 excess {mean_or_nan(d1):+.3f}')
    print(f'  D1 reference: {legs(d1)}')
    qb = QBoot(d1)
    ex = np.array([r['excess_atr'] for r in d1])
    wk = {w: i for i, w in enumerate(sorted({fd.week_of(r) for r in d1}))}
    wi = np.array([wk[fd.week_of(r)] for r in d1])
    cols, labels = [], []
    cut = {}
    for W in WINDOWS:
        e = np.array([r[f'eff{W}'] for r in d1])
        t1, t2 = np.quantile(e, [1 / 3, 2 / 3])
        cut[W] = (t1, t2)
        for r in d1:
            r[f'tight{W}'], r[f'loose{W}'], r[f'up{W}'] = r[f'eff{W}'] <= t1, r[f'eff{W}'] <= t2, r[f'topgap{W}'] >= -1.0
        w1, w2 = np.quantile([r[f'width{W}'] for r in d1], [1 / 3, 2 / 3])
        for r in d1:        # descriptive stage-1 definitions
            r[f'wtight{W}'] = r[f'width{W}'] <= w1
            r[f'wloose{W}'] = r[f'width{W}'] <= w2
            r[f'btight{W}'] = r[f'wtight{W}'] and r[f'tight{W}']
            r[f'bloose{W}'] = r[f'wloose{W}'] and r[f'loose{W}']
    for kind in ('tight', 'loose', 'up'):
        for W in WINDOWS:
            cols.append([r[f'{kind}{W}'] for r in d1])
            labels.append(f'{kind.upper()}{W}')
    flags = np.array(cols, dtype=bool).T
    obs, p1, best = diff_stats(ex, wi, flags)
    print('\n=== A. Chance menu (12 statistics): mean excess with the flag minus without it, inside D1; excess shuffled inside the entry week ===')
    for k, lab in enumerate(labels):
        n1 = int(flags[:, k].sum())
        print(f'  {lab:8s} flag n={n1:3d} vs {len(d1) - n1:3d}: difference {obs[k]:+.3f} (chance alone {p1[k]:.1%})')
    print(f'  smallest single chance {p1.min():.1%}; chance the best of 12 is at least that small by luck {best:.1%}')
    for W in WINDOWS:
        print(f'\n=== B. Window W={W}: eff cutoffs inside D1 tight <= {cut[W][0]:.3g}, loose <= {cut[W][1]:.3g}; moved up = topgap >= -1 ATR ===')
        for rule in ('tight', 'loose'):
            s1 = [r for r in d1 if not r[f'{rule}{W}']]
            s2 = [r for r in d1 if r[f'{rule}{W}'] and not r[f'up{W}']]
            s3 = [r for r in d1 if r[f'{rule}{W}'] and r[f'up{W}']]
            print(f'  rule {rule}:')
            for nm, g in (('1 not basing', s1), ('2 basing, not moved up', s2), ('3 basing and moved up', s3)):
                print(f'     {nm:24s} {legs(g)} | no episodes {mean_or_nan(no_ep_(g)):+.3f} (n={len(no_ep_(g))})')
            a, b = [r for r in d1 if r[f'{rule}{W}']], s1
            if len(a) >= 15 and len(b) >= 15:
                print(f'     basing minus not basing {mean_or_nan(a) - mean_or_nan(b):+.3f} quarter-block {cs.fmt_range(qb.diff_range(a, b))}')
            for lab, f in (('2006-10', lambda r: r['entry'] < '2011-01-01'), ('2011-20', lambda r: r['entry'] >= '2011-01-01')):
                aa, bb = [r for r in a if f(r)], [r for r in b if f(r)]
                print(f'     {lab}: basing {mean_or_nan(aa):+.3f} (n={len(aa)}) | not basing {mean_or_nan(bb):+.3f} (n={len(bb)})')
        u, nu = [r for r in d1 if r[f'up{W}']], [r for r in d1 if not r[f'up{W}']]
        print(f'  moved up (any base): {legs(u)}\n  not moved up:        {legs(nu)}')
    print('\n=== C. Descriptive: width-based and width-plus-choppiness definitions (basing minus not basing; n) ===')
    for W in WINDOWS:
        parts = []
        for kind in ('wtight', 'wloose', 'btight', 'bloose'):
            a, b = [r for r in d1 if r[f'{kind}{W}']], [r for r in d1 if not r[f'{kind}{W}']]
            parts.append(f'{kind} {mean_or_nan(a):+.3f} (n={len(a)}) vs {mean_or_nan(b):+.3f} (n={len(b)})')
        print(f'  W={W}: ' + '; '.join(parts))
    print('\nQuestions asked on this cohort in this entry: 12 chance-tested statistics, plus descriptive state tables, eras and alternative definitions. POST HOC. '
          'D1 is about 255 events and the windows overlap, so the 12 statistics are far from independent (best-of-12 is conservative).')


def no_ep_(rs):
    from refined_baseline import EPISODES, quarter
    return [r for r in rs if quarter(r['entry']) not in EPISODES]


# ------------------------------------------------------------------ self-test
def selftest():
    from datetime import date
    ds, d = [], date(2010, 1, 4)
    while len(ds) < 200:
        if d.weekday() < 5:
            ds.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    # falls to session 100, zig-zags between 50 and 54 for sessions 101..144, then rises 55..59 over sessions 145..149
    px = [200 - k for k in range(101)] + [(50 if k % 2 else 54) for k in range(44)] + [54 + k for k in range(1, 6)] + [59] * 50
    stock = {x: (p, p + 1, p - 1, p) for x, p in zip(ds, px)}
    e = ds[150]                                                     # last completed session 149, breakout window 145..149, base W=20: sessions 125..144
    f = base_features(ds, stock, e)
    assert f['status'] == 'ok'
    assert abs(f['width20'] - (55 - 49) / f['atr']) < 1e-9              # highs 55, lows 49
    assert f['eff20'] == 0.0 or f['eff20'] < 0.25                      # zig-zag: first and last close 54 -> 50, path 4 x 19
    base_max = 54
    assert abs(f['topgap20'] - (px[149] - base_max) / f['atr']) < 1e-9 and f['topgap20'] > 0
    # trending base has high efficiency
    up = {x: (100 + k, 101 + k, 99 + k, 100 + k) for k, x in enumerate(ds)}
    g = base_features(ds, up, ds[150])
    assert g['eff20'] == 1.0 and g['topgap20'] > 0
    # no lookahead
    alt = dict(stock)
    for x in ds[150:]:
        alt[x] = (1, 2, 0.5, 1)
    assert base_features(ds, alt, e) == f
    # short history leaves the long windows blank
    h = base_features(ds, stock, ds[40])
    assert 'width10' in h and 'width60' not in h
    try:
        base_features(ds, stock, '2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    # flag-minus-rest chance machinery: a planted difference is found, a null is not
    import numpy as np
    rng = np.random.default_rng(3)
    n = 400
    wi = np.repeat(np.arange(100), 4)
    f1 = rng.random(n) < 0.4
    f2 = rng.random(n) < 0.4
    exs = rng.normal(0, 1, n) + 1.0 * f1
    obs, p1, best = diff_stats(exs, wi, np.array([f1, f2]).T, draws=300)
    assert obs[0] > 0.7 and p1[0] < 0.02 and abs(obs[1]) < 0.5 and best < 0.05
    print('base_scan self-test passed')


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
    if a.cmd == 'baseyear':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'basedist':
        stage1(a.arg, a.arg2)
    elif a.cmd == 'stage2':
        stage2(a.arg, a.arg2, a.arg3, a.arg4)
    else:
        raise SystemExit(__doc__)
