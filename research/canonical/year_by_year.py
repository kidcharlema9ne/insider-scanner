"""C33 (declared 9 Nov 2026, BEFORE any run; Michael: "I'm game for year-by-year consistency").  Descriptive only, no new simulation: re-reads the paths of
the Entry 70/71 run (artifacts cost-YYYY, run 42601132693) and tabulates, by entry year, the deep-fall rule (down 15+ ATR over 12 months) against everything else.

Per entry year, for the deep-fall rule: signals n, distinct entry weeks, excess over SPY (stock ATR minus SPY ATR, same window, gross of cost) for the plain hold
of 21 and 42 sessions, a fixed 2.5 ATR stop and a fixed 5 ATR stop at 42 sessions, and the plain 42 excess of all other signals that year.  Then: how many years
are positive; the pooled mean versus the equal-weight mean of years with 5+ signals; the pooled mean with 2008, 2009 and 2020 removed, with the three episode
quarters (2008Q4, 2011Q3, 2020Q1) removed, and with the single best year removed; week-block 95% range of the plain 42 excess pooled; effective independent
weeks.  Development entries only (D-068).  Small cells (a few events a year) are shown with their n and are not a basis for a claim.

Usage:  python year_by_year.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER SIM_FOLDER DV_FOLDER
"""
import statistics, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_scan as ss
import cost_stops_f as cf
from refined_baseline import EPISODES, quarter
from stop_test import block_range
import datetime as dt


def mean(xs):
    xs = list(xs)
    return statistics.fmean(xs) if xs else float('nan')


def ex_(r, key, H):
    c = cf.cell(r, key, H)
    return None if c is None else c[0] - c[1]


def wk(r):
    y, w, _ = dt.date.fromisoformat(r['entry']).isocalendar()
    return (y, w)


def scan(events, years, decl, regime, ret, sim_folder, dv_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    rows = cf.load_join(sim_folder, dev0, dv_folder)
    for r in rows:
        r['F'] = r['raw252'] <= cf.F_CUT
    F = [r for r in rows if r['F']]
    O = [r for r in rows if not r['F']]
    print(f'groups: ALL {len(rows)}, deep-fall {len(F)}, others {len(O)}')
    print(f'reproduction: deep-fall plain 21 excess {mean(x for x in (ex_(r, "none0", 21) for r in F) if x is not None):+.3f} (Entry 70: +0.599), '
          f'plain 42 {mean(x for x in (ex_(r, "none0", 42) for r in F) if x is not None):+.3f} (+1.123)')
    yrs = sorted({r['entry'][:4] for r in rows})
    print('\n=== Deep-fall rule by entry year (excess over SPY in ATR, gross of cost) ===')
    print(f'  {"year":5s} {"n":>4s} {"weeks":>5s} {"plain21":>8s} {"plain42":>8s} {"fix2.5@42":>9s} {"fix5@42":>8s} | {"others n":>8s} {"others plain42":>14s}')
    per = {}
    for y in yrs:
        g = [r for r in F if r['entry'][:4] == y]
        o = [r for r in O if r['entry'][:4] == y]
        v = lambda rs, k, H: [x for x in (ex_(r, k, H) for r in rs) if x is not None]
        p21, p42, f25, f5 = v(g, 'none0', 21), v(g, 'none0', 42), v(g, 'fixed2.5', 42), v(g, 'fixed5', 42)
        o42 = v(o, 'none0', 42)
        per[y] = (len(g), mean(p42) if p42 else float('nan'), p42)
        f = lambda xs: f'{mean(xs):+8.2f}' if xs else f'{"-":>8s}'
        print(f'  {y:5s} {len(g):4d} {len({wk(r) for r in g}):5d} {f(p21)} {f(p42)} {f(f25):>9s} {f(f5)} | {len(o):8d} {mean(o42) if o42 else float("nan"):>+14.2f}')
    ok = [y for y in yrs if per[y][0] > 0 and per[y][2]]
    pos = [y for y in ok if per[y][1] > 0]
    big = [y for y in ok if per[y][0] >= 5]
    print(f'\n  years with at least one signal {len(ok)}; years with positive plain-42 excess {len(pos)} of {len(ok)}; of the {len(big)} years with 5+ signals, positive {sum(per[y][1] > 0 for y in big)}')
    allv = [x for x in (ex_(r, 'none0', 42) for r in F) if x is not None]
    print(f'  pooled plain-42 mean {mean(allv):+.3f} (n={len(allv)}); equal-weight mean of the {len(big)} years with 5+ signals {mean(per[y][1] for y in big):+.3f}; median of those years {statistics.median(per[y][1] for y in big):+.3f}')

    def pooled(label, keep):
        g = [r for r in F if keep(r)]
        xs = [x for x in (ex_(r, 'none0', 42) for r in g) if x is not None]
        xs21 = [x for x in (ex_(r, 'none0', 21) for r in g) if x is not None]
        print(f'  {label}: n={len(xs)}, distinct weeks {len({wk(r) for r in g})}; plain 42 {mean(xs):+.3f}; plain 21 {mean(xs21):+.3f}')
    print('\n=== Pooled, with parts removed ===')
    pooled('all development years', lambda r: True)
    pooled('without 2008, 2009 and 2020', lambda r: r['entry'][:4] not in ('2008', '2009', '2020'))
    pooled('without the three episode quarters (2008Q4, 2011Q3, 2020Q1)', lambda r: quarter(r['entry']) not in EPISODES)
    bestyear = max(big, key=lambda y: per[y][1] * per[y][0])
    pooled(f'without the single largest contributor, {bestyear}', lambda r: r['entry'][:4] != bestyear)
    pooled('2006-10 only', lambda r: r['entry'] < '2011-01-01')
    pooled('2011-20 only', lambda r: r['entry'] >= '2011-01-01')
    pooled('2011-17 only', lambda r: '2011' <= r['entry'][:4] <= '2017')
    pooled('2018-20 only', lambda r: r['entry'][:4] >= '2018')
    lo, hi, _ = block_range([{'entry': r['entry'], 'x': ex_(r, 'none0', 42)} for r in F if ex_(r, 'none0', 42) is not None], 'x')
    print(f'\n  week-block 95% range of the pooled plain-42 mean: [{lo:+.3f}, {hi:+.3f}]')
    print('\nDescriptive only; deep-fall rule chosen post hoc (Entries 36-67); small yearly cells are not a basis for a claim.')


if __name__ == '__main__':
    if sys.argv[1] == 'scan':
        scan(*sys.argv[2:])
