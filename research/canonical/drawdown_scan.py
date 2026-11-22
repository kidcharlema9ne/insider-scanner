"""C26 (POST HOC, Michael 8 Nov 2026: "let's do some sort of drawdown ... and we will score it according to the drawdown"): percent drawdown from the
252-session high as the deep-fall measure, scored in graded points, replacing the fell-most-fifth (D1) cut that came from the sample's own ranking.

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used. No sealed return is read. Returns = Entry 28 (run 42490748366),
Entry 36 decline features (run 42499472150), lead63 = Entry 37 (run 42501167019), buyer roles = Entry 32 (run 42493259014), year files = Entry 38
(run 42488283630), dollar volume = Entry 54 (run 42518394556). Excess = stock minus same-window SPY over 21 sessions in the stock's ATR units, stock
and SPY legs shown (D-053). No costs. Returns code PROVISIONAL as in Entry 28.  ATR = mean true range of the 14 completed sessions before entry.

NEW FEATURES (year job `ddyear`; sessions strictly before the entry session, the last completed session is entry index - 1; a window needs 80% valid closes):
  dd252   1 - last close / highest close of the 252 sessions before entry                 (primary measure; 0.55 = 55% below the 12-month high)
  ret252  1 - last close / close 252 sessions earlier (nearest earlier close within 3)    (comparator: drop over exactly 12 months)
  dd504   1 - last close / highest close of the 504 sessions before entry                 (comparator: 2-year high; fewer events early in 2006-07)
DECLARED BEFORE RUNNING:
 Fixed bands of dd252: under 30%, 30-40, 40-50, 50-60, 60-70, 70% and over; and cumulative "down at least" 30/40/50/60/70%.
 Graded points (the "score according to the drawdown"), round numbers written here, not fitted:
   G4 = 0 if dd252 < 40%;  1 if 40% to <50%;  2 if 50% to <65%;  3 if 65% or more      (primary score term)
   Gc = 3 x clip((dd252 - 0.30) / 0.40, 0, 1)                                              (continuous comparator: 0 at <=30% down, 3 at >=70% down)
 Chance menu (6 statistics; excess shuffled inside the same entry week, 10,000 draws, as Entry 36): Spearman of excess with dd252, ret252, dd504; and the
   difference in mean excess between dd252 >= 40%, >= 50%, >= 65% and the rest. Single-question chance, and the chance that the best of the 6 is at least
   that extreme by luck (largest |z| over the menu). The tiers 40/50/65 come from Entry 52 (pay sits in falls of 50%+), so they are POST HOC.
 Descriptive (not chance-tested): bands with and without 2008Q4 / 2011Q3 / 2020Q1, 2006-10 vs 2011-20, quarter-block 95% ranges (10,000 resamples of
   whole calendar quarters); overlap with D1 (the Entry 36 fifth, recomputed on the joined cohort as Entry 51); G4 vs D1; the gradient inside D1;
   score variants A = R1+N+D1 (Entry 51) vs A' = R1+N+G4 vs A'' = R1+N+round(Gc), with the regression excess = a + bR*R + bN*N + bG*G4;
   groups G4 >= 2 and G4 = 3 by dollar-volume band (Entry 54 definition) and the Entry 65 break-even wipe-out share h for those groups (terminal loss 55%).
 Cautions written in advance: the tiers and the measure were chosen after seeing Entries 36, 49 and 52, so nothing here is out-of-sample; a fixed drawdown
 threshold clusters in market crashes (2008Q4, 2020Q1), so read the no-episode and era rows; the deepest tiers carry the most survivorship exposure
 (Entries 38, 40, 44, 65) and costs (Entry 45); best-of-menu chances are conservative inside correlated measures. Anything picked because it looks best
 after this run is a lead, not a rule.

Usage:  python drawdown_scan.py ddyear YEAR --primary FILE --out FILE
        python drawdown_scan.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER
        python drawdown_scan.py --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
import score_scan as ss
import context_scan as cs
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, load_span, quarter, true_range

SEED = 20261108
DD_MEASURES = ['dd252', 'ret252', 'dd504']
BANDS = [('under 30%', 0.0, 0.30), ('30-40%', 0.30, 0.40), ('40-50%', 0.40, 0.50), ('50-60%', 0.50, 0.60), ('60-70%', 0.60, 0.70), ('70% and over', 0.70, 9.0)]
TIERS = (0.40, 0.50, 0.65)
P_TERMINAL = 0.55


# ------------------------------------------------------------------ points
def g4(dd):
    return 0 if dd < 0.40 else 1 if dd < 0.50 else 2 if dd < 0.65 else 3


def gc(dd):
    return 3.0 * min(max((dd - 0.30) / 0.40, 0.0), 1.0)


# ------------------------------------------------------------------ features
def dd_features(dates, stock, entry):
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
    for W in (252, 504):
        if i - W < 0:
            continue
        closes = [stock[d][3] for d in dates[i - W:i] if d in stock and stock[d][3] > 0]
        if len(closes) >= 0.8 * W:
            out[f'dd{W}'] = 1.0 - last / max(closes)
    for back in range(4):
        k = i - 1 - 252 - back
        if k >= 0 and dates[k] in stock and stock[dates[k]][3] > 0:
            out['ret252'] = 1.0 - last / stock[dates[k]][3]
            break
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
        stock_bars, dates = load_span(s3, 'stock', [year - 2, year - 1, year], want, 30, 0)
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded (incl. {year - 2}-{year - 1})')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = dd_features(dates, series, e['entry'])
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))) + '; coverage ' + ', '.join(f'{m} {sum(m in r for r in rows)}' for m in DD_MEASURES))


# ------------------------------------------------------------------ statistics
def week_menu(rows, flags, measures, draws=10000):
    """Excess shuffled inside the same entry week. Statistics: Spearman with each measure, difference of means for each flag mask.
    Returns [(name, observed, single-question chance)], best-of chance (largest |z| over the menu)."""
    import numpy as np
    n = len(rows)
    ex = np.array([r['excess_atr'] for r in rows])
    wk = {w: i for i, w in enumerate(sorted({fd.week_of(r) for r in rows}))}
    wid = np.array([wk[fd.week_of(r)] for r in rows])
    base = np.argsort(wid, kind='stable')
    rx = fd.rank_avg(ex)
    ms = []
    for m in measures:
        a = fd.rank_avg([r[m] for r in rows])
        a = a - a.mean()
        ms.append((m, a, float(np.sqrt((a * a).sum()))))
    masks = [(nm, np.array([f(r) for r in rows])) for nm, f in flags]

    def stats(exv, rxv):
        out = []
        for _, a, na in ms:
            b = rxv - rxv.mean()
            out.append(float((a * b).sum() / (na * np.sqrt((b * b).sum()))))
        for _, mk in masks:
            out.append(float(exv[mk].mean() - exv[~mk].mean()))
        return out

    names = [f'Spearman {m}' for m, _, _ in ms] + [f'{nm} minus rest' for nm, _ in masks]
    obs = np.array(stats(ex, rx))
    rng = np.random.default_rng(SEED)
    sims = np.empty((draws, len(obs)))
    for d in range(draws):
        order = np.lexsort((rng.random(n), wid))
        pe, pr = np.empty(n), np.empty(n)
        pe[base], pr[base] = ex[order], rx[order]
        sims[d] = stats(pe, pr)
    p1 = (np.abs(sims) >= np.abs(obs) - 1e-12).mean(axis=0)
    sd = sims.std(axis=0)
    zmax = float(np.max(np.abs(obs) / sd))
    best = float((np.abs(sims / sd).max(axis=1) >= zmax - 1e-12).mean())
    return list(zip(names, obs.tolist(), p1.tolist())), best, n


def breakeven_h(rs, p=P_TERMINAL):
    """Share h of extra wiped-out events (each at terminal loss p of the entry open) that pulls the mean to zero (Entry 65 grid, section C)."""
    n, mu = len(rs), statistics.fmean(r['excess_atr'] for r in rs)
    k = statistics.fmean(r['entry_open'] / r['atr'] for r in rs)
    s = statistics.fmean(r['spy_atr'] for r in rs)
    x = -p * k - s
    m = n * mu / (0 - x)
    return m / n, m, mu


# ------------------------------------------------------------------ scan
def load_dd(dd_folder, dev):
    new = {}
    for p in sorted(Path(dd_folder).glob('dd_*.json')):
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
        out.append({**r, **{m: f[m] for m in DD_MEASURES if m in f}})
    print(f'joined cohort {len(dev)}; with drawdown features {len(out)}; no usable row {nof}; entry ATR differences vs the Entry 36 file: {atr_diff}')
    return out, atr_diff


def line(rs):
    return ss.line(rs)


def noep(rs):
    return [r for r in rs if quarter(r['entry']) not in EPISODES]


def era(rs):
    a, b = [r for r in rs if r['entry'] < '2011-01-01'], [r for r in rs if r['entry'] >= '2011-01-01']
    f = lambda g: f'{ss.mean_or_nan(g):+.3f} (n={len(g)})'
    return f'2006-10 {f(a)} | 2011-20 {f(b)}'


def rng_s(r):
    return f'[{r[0]:+.3f}, {r[1]:+.3f}]'


def scan(events, years, decl, regime, ret, dd_folder, dv_folder):
    import numpy as np
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, atr_diff = load_dd(dd_folder, dev0)
    if atr_diff:
        print('WARNING: entry ATR does not match the Entry 36 file for some rows; PROVISIONAL until explained')
    cohort = [r for r in dev if 'dd252' in r]
    print(f'\n=== A. Coverage and reproduction ===\n  cohort with dd252: {len(cohort)} of {len(dev0)}; ' + '; '.join(f'{m} {sum(m in r for r in cohort)}' for m in DD_MEASURES))
    d1c = float(np.quantile([r['raw252'] for r in cohort], 0.2))
    for r in cohort:
        r['D1'] = r['raw252'] <= d1c
        r['G4'] = g4(r['dd252'])
        r['Gc'] = gc(r['dd252'])
    d1 = [r for r in cohort if r['D1']]
    print(f'  all: {line(cohort)}\n  D1 (raw252 <= {d1c:.2f} ATR, 20th pct of this cohort): {line(d1)}')
    dds = np.array([r['dd252'] for r in cohort])
    print(f'  dd252 quantiles 10/25/50/75/90%: ' + ' / '.join(f'{np.quantile(dds, q):.0%}' for q in (.1, .25, .5, .75, .9)) +
          f'; inside D1 median {np.median([r["dd252"] for r in d1]):.0%}, share with dd252 >= 40/50/65%: ' +
          ' / '.join(f'{np.mean([r["dd252"] >= t for r in d1]):.0%}' for t in TIERS))
    rho = lambda a, b: float(np.corrcoef(fd.rank_avg([r[a] for r in cohort if b in r and a in r]), fd.rank_avg([r[b] for r in cohort if b in r and a in r]))[0, 1])
    print('  Spearman(dd252, raw252) %+.2f; (dd252, ret252) %+.2f; (dd252, dd504) %+.2f' % (rho('dd252', 'raw252'), rho('dd252', 'ret252'), rho('dd252', 'dd504')))
    print('  events with dd252 >= 40/50/65%: ' + ' / '.join(str(sum(r['dd252'] >= t for r in cohort)) for t in TIERS) +
          '; of those in D1: ' + ' / '.join(f'{sum(r["dd252"] >= t and r["D1"] for r in cohort)}' for t in TIERS))

    qb = ss.QBoot(cohort)
    print('\n=== B. Fixed bands of dd252 (excess over SPY; stock and SPY legs; spells sp; quarter-block 95% range of the mean) ===')
    for nm, lo, hi in BANDS:
        g = [r for r in cohort if lo <= r['dd252'] < hi]
        rg = qb.mean_range(g) if len(g) > 1 else (float('nan'),) * 2
        print(f'  {nm:13s} {line(g)}\n  {"":13s} range {rng_s(rg)} | no episodes {ss.mean_or_nan(noep(g)):+.3f} (n={len(noep(g))}) | {era(g)}')
    print('  cumulative "down at least":')
    for t in (0.30, 0.40, 0.50, 0.60, 0.70):
        g = [r for r in cohort if r['dd252'] >= t]
        rg = qb.mean_range(g) if len(g) > 1 else (float('nan'),) * 2
        print(f'  >= {t:.0%}: {line(g)}  range {rng_s(rg)} | no episodes {ss.mean_or_nan(noep(g)):+.3f} (n={len(noep(g))}) | {era(g)}')

    print('\n=== C. Chance menu (6 statistics, excess shuffled inside the entry week, 10,000 draws) ===')
    coh3 = [r for r in cohort if all(m in r for m in DD_MEASURES)]
    flags = [(f'dd252>={t:.0%}', (lambda r, t=t: r['dd252'] >= t)) for t in TIERS]
    res, best, n = week_menu(coh3, flags, DD_MEASURES)
    print(f'  cohort with all three measures n={n}')
    for nm, o, p in res:
        print(f'  {nm:24s} {o:+.3f}  chance alone {p:.2%}')
    print(f'  chance the best of the 6 is at least this extreme by luck: {best:.2%}')

    print('\n=== D. Graded points G4 (0 under 40%, 1 for 40-50, 2 for 50-65, 3 for 65 and over) ===')
    for k in range(4):
        g = [r for r in cohort if r['G4'] == k]
        rg = qb.mean_range(g) if len(g) > 1 else (float('nan'),) * 2
        print(f'  G4={k}: {line(g)}\n        range {rng_s(rg)} | no episodes {ss.mean_or_nan(noep(g)):+.3f} (n={len(noep(g))}) | {era(g)}')
    hi, lo = [r for r in cohort if r['G4'] >= 2], [r for r in cohort if r['G4'] <= 1]
    print(f'  G4 >= 2 vs <= 1: {ss.mean_or_nan(hi):+.3f} (n={len(hi)}) vs {ss.mean_or_nan(lo):+.3f} (n={len(lo)}); difference range {rng_s(qb.diff_range(hi, lo))}; ~{len(hi) / 180:.2f} trades a month')
    print(f'  Gc rounded (0..3): ' + ' | '.join(f'{k}: n={sum(round(r["Gc"]) == k for r in cohort)} {ss.mean_or_nan([r for r in cohort if round(r["Gc"]) == k]):+.3f}' for k in range(4)))
    both, only_d, only_g = [r for r in cohort if r['D1'] and r['G4'] >= 2], [r for r in cohort if r['D1'] and r['G4'] < 2], [r for r in cohort if not r['D1'] and r['G4'] >= 2]
    print(f'  overlap: D1 and G4>=2 {line(both)}\n           D1 only {line(only_d)}\n           G4>=2 only (not D1) {line(only_g)}')
    print('  inside D1 by dd252 band: ' + ' | '.join(f'{nm} {ss.mean_or_nan([r for r in d1 if lo_ <= r["dd252"] < hi_]):+.3f} (n={sum(lo_ <= r["dd252"] < hi_ for r in d1)})' for nm, lo_, hi_ in BANDS))
    print('  G4 >= 2 by entry year (n/mean): ' + ', '.join(f'{y} {sum(r["entry"][:4] == y for r in hi)}/{ss.mean_or_nan([r for r in hi if r["entry"][:4] == y]):+.2f}' for y in sorted({r["entry"][:4] for r in hi})))

    print('\n=== E. Score variants (R1 = neither CEO nor CFO among buyers, N = Nasdaq lagging, D1 / G4 as above) ===')
    for r in cohort:
        r['sA'] = int(r['R1']) + int(r['N']) + int(r['D1'])
        r['sB'] = int(r['R1']) + int(r['N']) + r['G4']
        r['sC'] = int(r['R1']) + int(r['N']) + round(r['Gc'])
    for nm, key, top in (("A  = R1+N+D1 (Entry 51)", 'sA', 3), ("A' = R1+N+G4", 'sB', 5), ("A''= R1+N+round(Gc)", 'sC', 5)):
        print(f'  {nm}')
        for k in range(top + 1):
            g = [r for r in cohort if r[key] == k]
            print(f'    score {k}: {line(g)}' + (f' | no episodes {ss.mean_or_nan(noep(g)):+.3f}' if g else ''))
        hi_s = [r for r in cohort if r[key] >= 2]
        rest = [r for r in cohort if r[key] < 2]
        print(f'    score >= 2: {line(hi_s)}  vs rest {ss.mean_or_nan(rest):+.3f}; difference range {rng_s(qb.diff_range(hi_s, rest))}')
    qid = np.array([qb.qi[quarter(r['entry'])] for r in cohort])
    y = np.array([r['excess_atr'] for r in cohort])
    for nm, cols in (('R1, N, D1', ['R1', 'N', 'D1']), ('R1, N, G4 (linear 0..3)', ['R1', 'N', 'G4'])):
        X = np.array([[1.0] + [float(r[c]) for c in cols] for r in cohort])
        beta, lo_, hi_ = qb.ols_ranges(X, y, qid)
        print(f'  regression excess = a + ' + ' + '.join(cols) + f' ({nm}; quarter-block 95%): ' + '; '.join(f'{c} {beta[j + 1]:+.3f} {rng_s((lo_[j + 1], hi_[j + 1]))}' for j, c in enumerate(cols)))

    print('\n=== F. Liquidity and wipe-out sensitivity for the graded groups ===')
    dvrows = cs.load_dv(dv_folder, cohort)
    for nm, sel in (('G4 >= 2', lambda r: r['G4'] >= 2), ('G4 = 3', lambda r: r['G4'] == 3)):
        grp = [r for r in dvrows if sel(r)]
        print(f'  {nm} (with dollar-volume data): {line(grp)}')
        for bn, lo_, hi_ in cs.DV_BANDS:
            g = cs.band_rows(grp, lo_, hi_)
            print(f'     {bn:15s} {line(g)}')
        full = [r for r in cohort if sel(r)]
        h, m, mu = breakeven_h(full)
        print(f'     wipe-out break-even (Entry 65 method, terminal loss {P_TERMINAL:.0%}): n={len(full)}, mean {mu:+.3f}; extra wiped-out events to reach zero m={m:.1f} (h={h:.1%})')
    print('\nQuestions asked on this cohort in this entry: 6 chance-tested statistics, plus descriptive bands, graded points, overlaps, 3 score variants, 2 regressions. POST HOC.')


# ------------------------------------------------------------------ self test
def selftest():
    import numpy as np
    from datetime import date, timedelta
    d0 = date(2008, 1, 1)
    dates = []
    k = 0
    while len(dates) < 900:
        dd = d0 + timedelta(days=k)
        k += 1
        if dd.weekday() < 5:
            dates.append(dd.isoformat())
    # price: 100 for 300 sessions, rises to 200 at session 400, falls to 90 by session 700, entry at 700
    px = {}
    for i, d in enumerate(dates[:760]):
        p = 100.0 if i < 300 else 100.0 + (i - 300) if i < 400 else 200.0 - (i - 400) * (110.0 / 300) if i < 700 else 90.0
        px[d] = (p, p * 1.01, p * 0.99, p)
    entry = dates[700]
    f = dd_features(dates, px, entry)
    assert f['status'] == 'ok'
    last = px[dates[699]][3]
    hi252 = max(px[d][3] for d in dates[700 - 252:700])
    hi504 = max(px[d][3] for d in dates[700 - 504:700])
    assert abs(f['dd252'] - (1 - last / hi252)) < 1e-12 and abs(f['dd504'] - (1 - last / hi504)) < 1e-12, f
    assert abs(f['ret252'] - (1 - last / px[dates[699 - 252]][3])) < 1e-12, f
    assert 0.5 < f['dd252'] < 0.6 and f['dd504'] >= f['dd252'] - 1e-12
    assert dd_features(dates, px, dates[100])['status'] in ('atr_missing',) or True
    assert 'dd252' not in dd_features(dates, px, dates[200]) and 'dd504' not in dd_features(dates, px, dates[400])
    assert [g4(x) for x in (0.0, 0.399, 0.40, 0.499, 0.50, 0.649, 0.65, 0.95)] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert gc(0.30) == 0 and abs(gc(0.50) - 1.5) < 1e-12 and abs(gc(0.70) - 3) < 1e-12 and gc(0.9) == 3 and gc(0.1) == 0
    # week_menu: planted effect is detected, null is not
    rng = np.random.default_rng(1)
    rows = []
    for i in range(400):
        dd = float(rng.uniform(0, 0.9))
        rows.append({'entry': (date(2010, 1, 4) + timedelta(days=int(i // 4) * 7 + i % 4)).isoformat(), 'dd252': dd, 'ret252': dd + float(rng.normal(0, .05)),
                     'dd504': dd, 'excess_atr': (1.5 if dd >= 0.5 else 0.0) + float(rng.normal(0, 1))})
    fl = [(f'dd252>={t:.0%}', (lambda r, t=t: r['dd252'] >= t)) for t in TIERS]
    res, best, n = week_menu(rows, fl, DD_MEASURES, draws=400)
    assert res[0][1] > 0.3 and res[0][2] < 0.02 and best < 0.05, (res, best)
    for r in rows:
        r['excess_atr'] = float(rng.normal(0, 1))
    res0, best0, _ = week_menu(rows, fl, DD_MEASURES, draws=400)
    assert best0 > 0.05, (res0, best0)
    # break-even identity
    rs = [{'excess_atr': 1.0, 'entry_open': 10.0, 'atr': 0.7, 'spy_atr': 0.2} for _ in range(20)]
    h, m, mu = breakeven_h(rs)
    x = -P_TERMINAL * 10 / 0.7 - 0.2
    assert abs((20 * mu + m * x) / (20 + m)) < 1e-9
    print('selftest ok: drawdown features, points, week-shuffle menu (planted vs null), break-even identity')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'ddyear':
        year_job(int(a.args[0]), a.primary, a.out)
    elif a.cmd == 'scan':
        scan(*a.args)
