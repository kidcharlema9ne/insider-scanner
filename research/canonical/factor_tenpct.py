"""Candidates C10 and C7 on the primary set: 10%-owner box among the buyers, and the officer / pure-director mix.

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule.

Background (read from the committed code, not assumed): the refined events are built through cluster_counts_by_year.usable(),
which keeps a filing only if it has exactly one reporting owner, that owner ticks Director and/or Officer on the Form 4,
and the owner's name does not match the entity pattern (LLC, Capital, Trust, ...). So a pure 10%-owner filer, a fund,
or a joint filing can never be one of the four. What can remain is a MIXED filer: a Director or Officer who also ticks the
'10% Owner' box. This script measures how often that happens and whether such events behave differently.

Menu declared before the run (the chance test below covers exactly these):
  T1  any buyer also ticks the 10% Owner box            vs none
  T2  fewer than four buyers WITHOUT the 10% box (the event needs a 10% holder to reach four)   vs the rest
  T3  two or more buyers tick the 10% box               vs the rest
  C7a three or more pure directors (Director, not Officer)   vs the rest   (the pilot's 3 and 4 buckets)
  C7b zero pure directors (every buyer is an Officer)   vs the rest
  C7c Spearman rank correlation of excess with the number of pure directors
Descriptive only (not in the chance menu): bucket tables for the 10%-box count and the pure-director count, the 'Other' box.

Inputs and usage are the same as factor_roles.py:  python factor_tenpct.py EVENTS.json YEAR_FOLDER RETURNS_FOLDER | --selftest
"""
import statistics, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_roles as fr
from factor_roles import DEV_END, EPISODES, SEED, indep, quarter, stats_line, week_boot, week_of


def rel(o):
    """Form 4 boxes ticked, from the relationship string. Matching is by normalised text because the SEC bulk data writes the
    10% value as TenPercentOwner while the live parser writes '10% Owner' (the first run of this script looked only for the
    latter and found none: see Entry 34)."""
    s = (o[1] or '').lower().replace(' ', '')
    out = set()
    if 'director' in s:
        out.add('Director')
    if 'officer' in s:
        out.add('Officer')
    if 'tenpercent' in s or '10%' in s:
        out.add('10% Owner')
    if 'other' in s:
        out.add('Other')
    return out


def roles2(owners):
    """owners: [cik, relationship, title] triples. Flags by the Form 4 boxes."""
    people = {}
    for o in owners:
        people.setdefault(o[0], set()).update(rel(o))
    n = len(people)
    ten = sum('10% Owner' in r for r in people.values())
    oth = sum('Other' in r for r in people.values())
    pure_dir = sum('Director' in r and 'Officer' not in r for r in people.values())
    off = sum('Officer' in r for r in people.values())
    clean = sum(('Director' in r or 'Officer' in r) and '10% Owner' not in r for r in people.values())
    return {'n_buyers': n, 'n_ten': ten, 'n_other': oth, 'n_pure_dir': pure_dir, 'n_off': off, 'n_clean': clean,
            'no_do_box': sum(not ({'Director', 'Officer'} & r) for r in people.values())}


SPLITS = {
    'T1 any buyer ticks the 10% box': lambda r: r['n_ten'] >= 1,
    'T2 fewer than 4 buyers without the 10% box': lambda r: r['n_clean'] < 4,
    'T3 two or more buyers tick the 10% box': lambda r: r['n_ten'] >= 2,
    'C7a three or more pure directors': lambda r: r['n_pure_dir'] >= 3,
    'C7b zero pure directors (all officers)': lambda r: r['n_pure_dir'] == 0,
}


def rank(x):
    """Average ranks (ties share the mean rank); numpy only."""
    import numpy as np
    x = np.asarray(x, dtype=float)
    order = x.argsort(kind='mergesort')
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    return (np.bincount(inv, weights=r) / counts)[inv]


SPEAR = 'C7c Spearman (pure directors vs excess)'


def perm_test(dev, draws=10000):
    """Shuffle excess returns among trades inside the same entry week; every statistic is recomputed on each shuffle.
    Returns observed statistics, single-question chances, the best-of-menu chance (min-p method) and the smallest observed chance."""
    import numpy as np
    dev = sorted(dev, key=week_of)
    ex = np.array([r['excess_atr'] for r in dev])
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in dev}))}
    wi = np.array([wk[week_of(r)] for r in dev])
    lab = {g: np.array([f(r) for r in dev], dtype=bool) for g, f in SPLITS.items()}
    rnp = rank(np.array([r['n_pure_dir'] for r in dev], dtype=float))

    def stats(e):
        d = {g: ((e[l].mean() - e[~l].mean()) if l.any() and (~l).any() else 0.0) for g, l in lab.items()}
        re_ = rank(e)
        d[SPEAR] = float(np.corrcoef(rnp, re_)[0, 1]) if rnp.std() > 0 and re_.std() > 0 else 0.0
        return d
    obs = stats(ex)
    keys = list(obs)
    rng = np.random.default_rng(SEED)
    sim = {g: np.empty(draws) for g in keys}
    for k in range(draws):
        order = np.lexsort((rng.random(len(dev)), wi))
        d = stats(ex[order])
        for g in keys:
            sim[g][k] = abs(d[g])
    srt = {g: np.sort(sim[g]) for g in keys}
    atleast = lambda g, v: 1.0 - np.searchsorted(srt[g], v, side='left') / draws       # share of shuffles with |stat| >= v
    p1 = {g: float(atleast(g, abs(obs[g]) - 1e-12)) for g in keys}
    obs_min = min(p1.values())
    per_shuffle_min = np.min(np.vstack([1.0 - np.searchsorted(srt[g], sim[g] - 1e-12, side='left') / draws for g in keys]), axis=0)
    best = float((per_shuffle_min <= obs_min + 1e-12).mean())
    return obs, p1, best, obs_min


def buckets(rs, key, cap):
    out = []
    for v in range(cap + 1):
        sub = [r for r in rs if (min(r[key], cap) == v)]
        out.append((f'{v}{"+" if v == cap else ""}', sub))
    return out


def show(title, rs, dev=False):
    print(f'\n--- {title} ---')
    print(f'all: {stats_line(rs)}')
    for name, f in SPLITS.items():
        a, b = [r for r in rs if f(r)], [r for r in rs if not f(r)]
        extra = ''
        if dev and len(a) > 30 and len(b) > 30:
            lo, hi = week_boot(a)
            extra = f'  | mean 95% range {lo:+.3f} to {hi:+.3f}; {indep(a)}'
        print(f'{name}:\n    yes {stats_line(a)}{extra}\n    no  {stats_line(b)}')
    for label, key, cap in (('number of buyers ticking the 10% box', 'n_ten', 3), ('number of pure directors', 'n_pure_dir', 4),
                            ('number of officers (Officer box)', 'n_off', 4), ('number of buyers without the 10% box', 'n_clean', 6)):
        print(f'by {label}:')
        for v, sub in buckets(rs, key, cap):
            print(f'    {v}: {stats_line(sub)}')


def main(events_path, year_folder, returns_folder):
    fr.roles = roles2                       # factor_roles.load() calls the module-level roles()
    rows = fr.load(events_path, year_folder, returns_folder)
    dev = [r for r in rows if r['entry'] <= DEV_END]
    pil = [r for r in rows if r['entry'] > DEV_END]
    raw = Counter(o[1] for r in rows for o in r['owners'])
    print(f'\nRaw relationship strings among the buyers (all analysed events): {raw.most_common(12)}; strings with a space after a comma: '
          f'{sum(v for k, v in raw.items() if ", " in k)}; buyers recognised as 10% Owner: {sum(r["n_ten"] for r in rows)} of {sum(raw.values())}')
    print(f'\nComposition (all {len(rows)} analysed events): buyers per event {Counter(min(r["n_buyers"], 8) for r in rows)}')
    print(f'events with at least one buyer ticking the 10% box: {sum(r["n_ten"] >= 1 for r in rows)} '
          f'({sum(r["n_ten"] >= 1 for r in rows) / len(rows):.1%}); two or more: {sum(r["n_ten"] >= 2 for r in rows)}; '
          f'fewer than 4 buyers without the box: {sum(r["n_clean"] < 4 for r in rows)}')
    print(f'buyers with neither Director nor Officer box (should be 0): {sum(r["no_do_box"] for r in rows)}; '
          f'events with an Other-box buyer: {sum(r["n_other"] >= 1 for r in rows)}')
    print(f'events by number of pure directors: {sorted(Counter(r["n_pure_dir"] for r in rows).items())}')
    show('A. DEVELOPMENT 2006-2020 (entries <= 2020-12-31): excess over same-window SPY, ATR, price only', dev, dev=True)
    show('B. 2026 PILOT (in-sample, small)', pil)
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    show('C. Development without the three large episodes (2008Q4, 2011Q3, 2020Q1)', d2)
    print('\n--- D. Chance test: labels shuffled among trades inside the same entry week (10,000 shuffles, development only) ---')
    obs, p1, best, obs_min = perm_test(dev)
    for g in obs:
        print(f'  {g}: observed {obs[g]:+.3f}, chance of one this large (this question alone) {p1[g]:.1%}')
    print(f'Best of this menu of 6: smallest single-question chance {obs_min:.1%}; chance the best of 6 is at least that small by luck {best:.1%}')
    print('Questions asked on this cohort in this entry: 5 binary splits + 1 rank correlation (menu), plus 4 descriptive bucket tables.')


def selftest():
    o = [['1', 'Director,10% Owner', ''], ['2', 'Officer', 'CFO'], ['3', 'Director', ''], ['4', 'Director', ''], ['4', 'Officer', 'x']]
    r = roles2(o)
    assert r['n_buyers'] == 4 and r['n_ten'] == 1 and r['n_clean'] == 3 and r['n_pure_dir'] == 2 and r['n_off'] == 2, r
    assert roles2([['1', 'Director', '']] * 4)['n_pure_dir'] == 1       # same cik repeated is one person
    assert roles2([[str(k), 'Director', ''] for k in range(4)])['n_pure_dir'] == 4
    assert roles2([['1', '10% Owner', '']])['no_do_box'] == 1
    assert rel(['1', 'Director,TenPercentOwner', '']) == {'Director', '10% Owner'}
    assert rel(['1', 'Director, 10% Owner', '']) == {'Director', '10% Owner'}
    assert rel(['1', 'Officer', '']) == {'Officer'} and rel(['1', 'Other', '']) == {'Other'}
    assert roles2([['1', 'Officer,TenPercentOwner', ''], ['2', 'Director', ''], ['3', 'Director', ''], ['4', 'Director', '']])['n_clean'] == 3
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float(k % 5) - 1.0, 'stock_atr': 0.0, 'spy_atr': 0.0,
             'cik': str(k), **roles2([[str(k), 'Director', ''], [str(k) + 'b', 'Officer', ''], [str(k) + 'c', 'Director,10% Owner' if k % 3 == 0 else 'Director', ''],
                                      [str(k) + 'd', 'Director' if k % 4 else 'Officer', '']])} for k in range(120)]
    a = perm_test(rows, 100)
    b = perm_test(rows, 100)
    assert a == b
    print('factor_tenpct self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    else:
        main(*sys.argv[1:4])
