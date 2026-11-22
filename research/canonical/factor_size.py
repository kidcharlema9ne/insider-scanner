"""Candidate C4 and C6 on the primary set: how big were the purchases, in dollars and as a share of what the buyer already held?

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule.

Per buyer (within the 15-session window, routine rows already excluded by D-064):
  dollars   = sum of shares x price over all his purchase lines
  pct       = shares bought / shares held before, from the 'shares owned following' column of the Form 4 (direct-ownership
              lines when present, else all lines): holdings before = holdings after his latest line - shares bought.
              A buyer whose holdings before are about zero is a NEW POSITION (pct capped at 1,000%).
Five measures per event (declared before running; this is the menu for the chance test):
  A1 total dollars of all buyers          A2 smallest buyer's dollars          A3 median buyer's dollars
  R1 median buyer's % increase in holdings        R2 smallest buyer's % increase in holdings
Plus descriptive cuts: smallest-buyer dollars >= $25k / $50k / $100k (C4 reference), median % increase < 1% / 1-10% / >= 10%,
and whether any buyer opened a new position.
Caveats: 'shares owned following' covers one holding line (direct or indirect), so a buyer's total position can be larger than
the line shows (inflating the % increase); dollar size goes with company size, so the entry price is shown per group.

Usage: python factor_size.py EVENTS.json YEAR_FOLDER RETURNS_FOLDER      |      --selftest
"""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_roles import SEED, indep, stats_line, week_boot, week_of
from refined_baseline import DEV_END, EPISODES, assert_allowed, build_primary, quarter
from removed_events_check import boot_diff

CAP = 10.0                     # a % increase above 1,000% (or a new position) is capped
NEW_POSITION = 0.0005          # holdings before below 0.05% of the shares bought = new position
MEASURES = ('A1 total dollars', 'A2 smallest buyer dollars', 'A3 median buyer dollars',
            'R1 median % increase in holdings', 'R2 smallest % increase in holdings')


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def buyer_table(lines):
    by = defaultdict(list)
    for l in lines:
        by[l['owner']].append(l)
    out = []
    for owner, ls in by.items():
        sh, pr = [num(l['shares']) for l in ls], [num(l['price']) for l in ls]
        dollars = None if None in sh or None in pr else sum(a * b for a, b in zip(sh, pr))
        dirs = [l for l in ls if (l.get('di') or '').upper() == 'D'] or ls
        dsh = [num(l['shares']) for l in dirs]
        last = max(l['date'] for l in dirs)
        after = [num(l['after']) for l in dirs if l['date'] == last]
        pct, new = None, False
        if None not in dsh and after and None not in after:
            bought, held_after = sum(dsh), max(after)
            before = held_after - bought
            if bought > 0:
                if before <= NEW_POSITION * bought:
                    pct, new = CAP, True
                else:
                    pct = min(CAP, bought / before)
        out.append({'owner': owner, 'dollars': dollars, 'pct': pct, 'new': new})
    return out


def measures(lines):
    b = buyer_table(lines)
    d = [x['dollars'] for x in b]
    p = [x['pct'] for x in b]
    m = {k: None for k in MEASURES}
    if b and None not in d:
        m[MEASURES[0]], m[MEASURES[1]], m[MEASURES[2]] = sum(d), min(d), statistics.median(d)
    if b and None not in p:
        m[MEASURES[3]], m[MEASURES[4]] = statistics.median(p), min(p)
    return m, any(x['new'] for x in b), len(b)


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    import numpy as np
    return float(np.corrcoef(ranks(x), ranks(y))[0, 1])


def perm_menu(rows, draws=10000):
    """Shuffle excess results among trades inside the same entry week; Spearman of each measure with excess."""
    import numpy as np
    rows = sorted(rows, key=week_of)
    ry = np.array(ranks([r['excess_atr'] for r in rows]))
    rx = [np.array(ranks([r['m'][k] for r in rows])) for k in MEASURES]
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in rows}))}
    wi = np.array([wk[week_of(r)] for r in rows])
    cor = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    obs = [cor(x, ry) for x in rx]
    rng = np.random.default_rng(SEED)
    single, best, obs_best = [0] * len(rx), 0, max(abs(o) for o in obs)
    for _ in range(draws):
        yp = ry[np.lexsort((rng.random(len(rows)), wi))]
        d = [cor(x, yp) for x in rx]
        for i, v in enumerate(d):
            single[i] += abs(v) >= abs(obs[i])
        best += max(abs(v) for v in d) >= obs_best
    return obs, [s / draws for s in single], best / draws, obs_best


def load(events_path, year_folder, returns_folder):
    from archive_coverage_audit import normalize_ticker
    events = json.loads(Path(events_path).read_text())
    by_key = defaultdict(list)
    for e in events:
        if e['set'] == 'refined':
            by_key[(e['issuer_cik'], normalize_ticker(e['ticker'])[0], e['entry'])].append(e)
    assert sum(len(v) for v in by_key.values()) == 5829
    ret = {}
    for p in sorted(Path(returns_folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            ret[(r['cik'], r['sym'], r['entry'])] = r
    rows = []
    for p in build_primary(year_folder):
        k = (p['cik'], p['sym'], p['entry'])
        r = ret.get(k)
        if not r or r['status'] != 'complete':
            continue
        m, new, nb = measures(by_key[k][0]['lines'])
        rows.append({**r, 'm': m, 'new_position': new, 'n_buyers_lines': nb})
    print(f'analysed {len(rows)} completed primary trades')
    return rows


def quint(rows, key):
    rs = sorted(rows, key=lambda r: r['m'][key])
    n = len(rs)
    return [rs[i * n // 5:(i + 1) * n // 5] for i in range(5)]


def fmt(key, v):
    return f'${v:,.0f}' if key.startswith('A') else f'{v:.1%}'


def main(events_path, year_folder, returns_folder):
    rows = load(events_path, year_folder, returns_folder)
    dev = [r for r in rows if r['entry'] <= DEV_END]
    pil = [r for r in rows if r['entry'] > DEV_END]
    print('\n=== A. Coverage (development): events where the measure could be computed ===')
    for k in MEASURES:
        print(f'{k}: {sum(r["m"][k] is not None for r in dev)} of {len(dev)}')
    full = [r for r in dev if all(r['m'][k] is not None for k in MEASURES)]
    print(f'all five measures available: {len(full)} of {len(dev)}; mean excess of those {statistics.fmean(r["excess_atr"] for r in full):+.3f} '
          f'vs all development {statistics.fmean(r["excess_atr"] for r in dev):+.3f}')
    print(f'new position among the buyers: {sum(r["new_position"] for r in full)} of {len(full)} events')
    print('\n=== B. Quintiles of each measure (development, complete cases), excess over SPY in ATR; median entry price shown ===')
    for k in MEASURES:
        print(f'\n{k}:')
        qs = quint(full, k)
        for i, q in enumerate(qs, 1):
            lo, hi = q[0]['m'][k], q[-1]['m'][k]
            print(f'  Q{i} [{fmt(k, lo)} to {fmt(k, hi)}]: {stats_line(q)}  median entry price ${statistics.median(r["entry_open"] for r in q):.2f}')
        lo, hi, p = boot_diff(qs[4], qs[0])
        print(f'  top fifth minus bottom fifth: {statistics.fmean(r["excess_atr"] for r in qs[4]) - statistics.fmean(r["excess_atr"] for r in qs[0]):+.3f}, '
              f'week-block 95% range {lo:+.3f} to {hi:+.3f}, share of draws <= 0 {p:.1%}')
        keep = lambda q: [r for r in q if quarter(r['entry']) not in EPISODES]
        print(f'  without the three large episodes: Q1 {stats_line(keep(qs[0]))} | Q5 {stats_line(keep(qs[4]))}')
    print('\n=== C. Chance test (excess shuffled among trades inside the same entry week, 10,000 shuffles; Spearman rank correlation) ===')
    obs, single, pbest, obs_best = perm_menu(full)
    for k, o, s in zip(MEASURES, obs, single):
        print(f'  {k}: rho {o:+.3f}, chance of |rho| this large for this measure alone {s:.1%}')
    print(f'Best of the 5 measures: largest |rho| {obs_best:.3f}; chance the best of 5 is at least that large by luck {pbest:.1%}')
    print('\n=== D. Descriptive cuts (development, complete cases) ===')
    a2, r1 = MEASURES[1], MEASURES[3]
    cuts = [('smallest buyer >= $25,000', lambda r: r['m'][a2] >= 25_000), ('smallest buyer >= $50,000 (C4 reference)', lambda r: r['m'][a2] >= 50_000),
            ('smallest buyer >= $100,000', lambda r: r['m'][a2] >= 100_000), ('smallest buyer < $25,000', lambda r: r['m'][a2] < 25_000),
            ('median % increase < 1%', lambda r: r['m'][r1] < 0.01), ('median % increase 1% to 10%', lambda r: 0.01 <= r['m'][r1] < 0.10),
            ('median % increase >= 10%', lambda r: r['m'][r1] >= 0.10), ('any buyer opened a new position', lambda r: r['new_position']),
            ('no buyer opened a new position', lambda r: not r['new_position'])]
    for name, f in cuts:
        sub = [r for r in full if f(r)]
        extra = ''
        if len(sub) > 30:
            lo, hi = week_boot(sub)
            extra = f' | mean 95% range {lo:+.3f} to {hi:+.3f}; {indep(sub)}'
        print(f'{name}: {stats_line(sub)}{extra}')
    print('\n=== E. 2026 pilot (in-sample, small): above vs below the pilot median of each measure ===')
    pf = [r for r in pil if all(r['m'][k] is not None for k in MEASURES)]
    print(f'pilot complete cases: {len(pf)} of {len(pil)}')
    for k in MEASURES:
        med = statistics.median(r['m'][k] for r in pf)
        print(f'{k}: above {stats_line([r for r in pf if r["m"][k] > med])} | at or below {stats_line([r for r in pf if r["m"][k] <= med])}')
    print('\nQuestions asked on this cohort in this entry: 5 measures (quintiles + rank correlation) plus 9 descriptive cuts.')


def selftest():
    L = lambda o, d, sh, pr, af, di='D': {'owner': o, 'date': d, 'shares': sh, 'price': pr, 'after': af, 'di': di, 'acc': 'a'}
    t = {b['owner']: b for b in buyer_table([L('1', '2020-01-02', 100, 10.0, 1100), L('1', '2020-01-03', 100, 11.0, 1200),     # held 1000 before, bought 200
                                              L('2', '2020-01-02', 500, 4.0, 500),                                              # new position
                                              L('3', '2020-01-02', 50, 20.0, 5050, 'I'), L('3', '2020-01-02', 10, 20.0, 400, 'D'),   # direct 390 before
                                              L('4', '2020-01-02', 10, 5.0, None)])}
    assert abs(t['1']['dollars'] - 2100.0) < 1e-9 and abs(t['1']['pct'] - 0.2) < 1e-9, t['1']
    assert t['2']['new'] and t['2']['pct'] == CAP
    assert abs(t['3']['pct'] - 10 / 390) < 1e-9 and abs(t['3']['dollars'] - 1200.0) < 1e-9, t['3']
    assert t['4']['pct'] is None
    m, new, nb = measures([L('1', '2020-01-02', 100, 10.0, 1100), L('2', '2020-01-02', 500, 4.0, 500)])
    assert m[MEASURES[0]] == 3000.0 and m[MEASURES[1]] == 1000.0 and m[MEASURES[2]] == 1500.0 and new and nb == 2, (m, new)
    assert m[MEASURES[3]] == statistics.median([0.1, CAP]) and m[MEASURES[4]] == 0.1
    assert measures([L('4', '2020-01-02', 10, 5.0, None)])[0][MEASURES[3]] is None
    assert ranks([3, 1, 1, 2]) == [4.0, 1.5, 1.5, 3.0]
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float((k * 7) % 5) - 1.0, 'm': {m_: float((k * (i + 3)) % 11) for i, m_ in enumerate(MEASURES)}} for k in range(120)]
    assert perm_menu(rows, 100) == perm_menu(rows, 100)
    print('factor_size self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    else:
        main(*sys.argv[1:4])
