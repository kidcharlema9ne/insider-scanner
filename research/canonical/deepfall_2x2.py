"""C27 (POST HOC, Michael 8 Nov 2026: "Yeah, go ahead" after Entry 66): which ruler carries the deep-fall pay - a fixed PERCENT drawdown (P) or a fixed
ATR fall (F)?  Neither uses a ranking: both are fixed numbers that a live scanner can apply on entry day.

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used. No sealed return is read. Same inputs and cohort as Entry 66
(drawdown features from run 42536126909, returns 42490748366, decline 42499472150, regime 42501167019, roles 42493259014, year files 42488283630,
dollar volume 42518394556). Excess = stock minus same-window SPY over 21 sessions in the stock's ATR units, stock and SPY legs shown (D-053). No costs.
Returns code PROVISIONAL as in Entry 28. Cohort: events with roles, lead63, raw252 and dd252 (n=1,273 in Entry 66).

DECLARED BEFORE RUNNING:
  P  = dd252 >= 50%  (down at least 50% from the highest close of the 252 sessions before entry; Entry 66)
  F  = raw252 <= -15.0 ATR  (12-month close change, in entry-ATR units; a FIXED number, not the quintile cut -15.32 of D1; Entry 49 bucket 15+ ATR)
 A. The 2x2: P and F, P only, F only, neither: n, weeks, spells, excess with stock and SPY legs, median, share beating SPY, quarter-block 95% range of the mean,
    without 2008Q4 / 2011Q3 / 2020Q1, 2006-10 vs 2011-20; overlap with D1 (the Entry 36 fifth) and with Entry 66 G4 >= 2.
 B. Chance menu (5 statistics; excess shuffled inside the same entry week, 10,000 draws, as Entries 36 and 66): mean excess of P, of F and of (P and F),
    each minus the rest, on the whole cohort (3); P minus not-P inside F, and F minus not-F inside P (2). Single-question chance and, per family, the chance
    that the best is this extreme by luck. The tally for this entry is 5 statistics.
 C. Descriptive threshold sensitivity (not chance-tested, NOT on the tally): F at -10, -12, -15, -20, -25 ATR and P at 40, 50, 60, 70%, cumulative.
 D. Score: R1 (neither CEO nor CFO among the buyers) + N (Nasdaq lagging, lowest fifth of lead63) + one deep-fall term:
      S_P = R1+N+P    S_F = R1+N+F    S_PF = R1+N+(P and F)    S_or = R1+N+(P or F)    S_2 = R1+N+P+F (0..4)
    by score: n, excess, no-episode mean; score >= 2 vs the rest with a quarter-block range of the difference; and the regression
    excess = a + bR*R1 + bN*N + bP*P + bF*F with quarter-block 95% ranges (does each ruler add given the other?). Reference: Entry 51 score A = R1+N+D1.
 E. For P, F and (P and F): Entry 54 dollar-volume bands (under $5M, 5-10, 10-25, 25-100, 100M+) and the Entry 65 wipe-out break-even
    (terminal loss 55% of the entry open): extra wiped-out events, as a share of the group, that pull the mean to zero.
 F. Events per entry year for each group (crash clustering).
Cautions written in advance: both rulers and the 50% / 15 ATR numbers were chosen after seeing Entries 36, 49, 52 and 66, so nothing here is out-of-sample;
P and F overlap heavily, so the 2x2 off-diagonal cells are small and noisy; survivorship (Entries 38, 40, 44, 65) and costs (Entry 45) are not in any
number except the break-even; anything picked because it looks best after this run is a lead, not a rule.

Usage:  python deepfall_2x2.py EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER   |   --selftest
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import factor_decline as fd
import score_scan as ss
import context_scan as cs
import drawdown_scan as dd
from refined_baseline import quarter

P_CUT = 0.50
F_CUT = -15.0


def flags(r):
    r['P'] = r['dd252'] >= P_CUT
    r['F'] = r['raw252'] <= F_CUT
    r['PF'] = r['P'] and r['F']
    r['Por'] = r['P'] or r['F']


def pr(label, rs, qb=None):
    rg = qb.mean_range(rs) if (qb and len(rs) > 1) else None
    extra = f' | range {dd.rng_s(rg)}' if rg else ''
    print(f'  {label}: {dd.line(rs)}{extra}')


def scan(events, years, decl, regime, ret, dd_folder, dv_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, atr_diff = dd.load_dd(dd_folder, dev0)
    if atr_diff:
        print('WARNING: entry ATR does not match the Entry 36 file for some rows; PROVISIONAL until explained')
    cohort = [r for r in dev if 'dd252' in r]
    d1c = float(np.quantile([r['raw252'] for r in cohort], 0.2))
    for r in cohort:
        flags(r)
        r['D1'] = r['raw252'] <= d1c
        r['G4ge2'] = dd.g4(r['dd252']) >= 2
    qb = ss.QBoot(cohort)
    n = len(cohort)
    print(f'\n=== A. The 2x2 (cohort n={n}; all: {dd.line(cohort)}) ===')
    cells = [('P and F', lambda r: r['P'] and r['F']), ('P only (down 50%+, fell under 15 ATR)', lambda r: r['P'] and not r['F']),
             ('F only (fell 15+ ATR, down under 50%)', lambda r: r['F'] and not r['P']), ('neither', lambda r: not r['P'] and not r['F'])]
    for nm, f in cells:
        g = [r for r in cohort if f(r)]
        pr(nm, g, qb)
        print(f'      no episodes {ss.mean_or_nan(dd.noep(g)):+.3f} (n={len(dd.noep(g))}) | {dd.era(g)}')
    for nm, key in (('P', 'P'), ('F', 'F'), ('P or F', 'Por')):
        pr(f'{nm} (all)', [r for r in cohort if r[key]], qb)
    print(f'  overlap: D1 n={sum(r["D1"] for r in cohort)}; F n={sum(r["F"] for r in cohort)}; D1 and F {sum(r["D1"] and r["F"] for r in cohort)}; '
          f'P n={sum(r["P"] for r in cohort)}; P and G4>=2 {sum(r["P"] and r["G4ge2"] for r in cohort)} (should equal P); '
          f'D1 {line_mean([r for r in cohort if r["D1"]])} vs F {line_mean([r for r in cohort if r["F"]])}')

    print('\n=== B. Chance menu (5 statistics; excess shuffled inside the entry week, 10,000 draws) ===')
    fl = [('P', lambda r: r['P']), ('F', lambda r: r['F']), ('P and F', lambda r: r['PF'])]
    res, best, nn = dd.week_menu(cohort, fl, [])
    for nm, o, p in res:
        print(f'  {nm:18s} {o:+.3f}  chance alone {p:.2%}')
    print(f'  chance the best of these 3 is this extreme by luck: {best:.2%}')
    insF = [r for r in cohort if r['F']]
    res2, b2, n2 = dd.week_menu(insF, [('P (inside F)', lambda r: r['P'])], [])
    insP = [r for r in cohort if r['P']]
    res3, b3, n3 = dd.week_menu(insP, [('F (inside P)', lambda r: r['F'])], [])
    for (nm, o, p), n_ in ((res2[0], n2), (res3[0], n3)):
        print(f'  {nm:18s} {o:+.3f} (mean excess with the flag minus without, n={n_})  chance alone {p:.2%}')

    print('\n=== C. Threshold sensitivity (descriptive, not on the tally) ===')
    for t in (-10, -12, -15, -20, -25):
        g = [r for r in cohort if r['raw252'] <= t]
        print(f'  raw252 <= {t} ATR: {dd.line(g)}')
    for t in (0.40, 0.50, 0.60, 0.70):
        g = [r for r in cohort if r['dd252'] >= t]
        print(f'  dd252 >= {t:.0%}: {dd.line(g)}')

    print('\n=== D. Score = R1 + N + deep-fall term ===')
    defs = {'S_P  = R1+N+P': lambda r: int(r['R1']) + int(r['N']) + int(r['P']),
            'S_F  = R1+N+F': lambda r: int(r['R1']) + int(r['N']) + int(r['F']),
            'S_PF = R1+N+(P and F)': lambda r: int(r['R1']) + int(r['N']) + int(r['PF']),
            'S_or = R1+N+(P or F)': lambda r: int(r['R1']) + int(r['N']) + int(r['Por']),
            'S_2  = R1+N+P+F': lambda r: int(r['R1']) + int(r['N']) + int(r['P']) + int(r['F']),
            'A    = R1+N+D1 (Entry 51)': lambda r: int(r['R1']) + int(r['N']) + int(r['D1'])}
    for nm, f in defs.items():
        for r in cohort:
            r['_s'] = f(r)
        top = max(r['_s'] for r in cohort)
        print(f'  {nm}')
        for k in range(top + 1):
            g = [r for r in cohort if r['_s'] == k]
            print(f'    score {k}: {dd.line(g)}' + (f' | no episodes {ss.mean_or_nan(dd.noep(g)):+.3f}' if g else ''))
        hi = [r for r in cohort if r['_s'] >= 2]
        lo = [r for r in cohort if r['_s'] < 2]
        print(f'    score >= 2: {dd.line(hi)}  vs rest {ss.mean_or_nan(lo):+.3f}; difference range {dd.rng_s(qb.diff_range(hi, lo))}; ~{len(hi) / 180:.2f} trades a month')
    qid = np.array([qb.qi[quarter(r['entry'])] for r in cohort])
    y = np.array([r['excess_atr'] for r in cohort])
    for cols in (['R1', 'N', 'P', 'F'], ['R1', 'N', 'P'], ['R1', 'N', 'F']):
        X = np.array([[1.0] + [float(r[c]) for c in cols] for r in cohort])
        beta, lo_, hi_ = qb.ols_ranges(X, y, qid)
        print('  regression excess = a + ' + ' + '.join(cols) + ' (quarter-block 95%): ' + '; '.join(
            f'{c} {beta[j + 1]:+.3f} {dd.rng_s((lo_[j + 1], hi_[j + 1]))}' for j, c in enumerate(cols)))

    print('\n=== E. Liquidity and wipe-out break-even ===')
    dvrows = cs.load_dv(dv_folder, cohort)
    for nm, key in (('P', 'P'), ('F', 'F'), ('P and F', 'PF')):
        grp = [r for r in dvrows if r[key]]
        print(f'  {nm}: {dd.line(grp)}')
        for bn, lo_, hi_ in cs.DV_BANDS:
            print(f'     {bn:15s} {dd.line(cs.band_rows(grp, lo_, hi_))}')
        full = [r for r in cohort if r[key]]
        h, m, mu = dd.breakeven_h(full)
        print(f'     wipe-out break-even (terminal loss {dd.P_TERMINAL:.0%}): n={len(full)}, mean {mu:+.3f}; extra wiped-out events to reach zero m={m:.1f} (h={h:.1%})')

    print('\n=== F. Events per entry year (n / mean excess) ===')
    for nm, key in (('P', 'P'), ('F', 'F'), ('P and F', 'PF')):
        g = [r for r in cohort if r[key]]
        print(f'  {nm}: ' + ', '.join(f'{yy} {sum(r["entry"][:4] == yy for r in g)}/{ss.mean_or_nan([r for r in g if r["entry"][:4] == yy]):+.2f}' for yy in sorted({r["entry"][:4] for r in g})))
    print('\nQuestions asked on this cohort in this entry: 5 chance-tested statistics, plus the 2x2, six score variants, three regressions, thresholds, '
          'liquidity and break-even rows. POST HOC.')


def line_mean(rs):
    return f'{ss.mean_or_nan(rs):+.3f} (n={len(rs)})'


def selftest():
    from datetime import date, timedelta
    rng = np.random.default_rng(3)
    rows = []
    for i in range(500):
        d = float(rng.uniform(0, 0.9))
        rows.append({'entry': (date(2010, 1, 4) + timedelta(days=int(i // 5) * 7 + i % 5)).isoformat(), 'dd252': d, 'raw252': -30 * d + float(rng.normal(0, 3)),
                     'excess_atr': (1.0 if d >= 0.5 else 0.0) + float(rng.normal(0, 1)), 'entry_open': 10.0, 'atr': 0.7, 'spy_atr': 0.2})
    for r in rows:
        flags(r)
    tot = sum(r['P'] and r['F'] for r in rows) + sum(r['P'] and not r['F'] for r in rows) + sum(r['F'] and not r['P'] for r in rows) + sum(not r['P'] and not r['F'] for r in rows)
    assert tot == len(rows) and all(r['Por'] == (r['P'] or r['F']) for r in rows)
    res, best, n = dd.week_menu(rows, [('P', lambda r: r['P']), ('F', lambda r: r['F']), ('PF', lambda r: r['PF'])], [], draws=300)
    assert res[0][1] > 0.5 and res[0][2] < 0.02 and best < 0.05, (res, best)
    sub = [r for r in rows if r['F']]
    res2, _, _ = dd.week_menu(sub, [('P', lambda r: r['P'])], [], draws=200)
    assert len(res2) == 1
    print('selftest ok: flags partition the cohort; week_menu works with flags only and on subsets')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    else:
        scan(*sys.argv[1:8])
