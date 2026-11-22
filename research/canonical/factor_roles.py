"""Candidate factor C3/C5 on the primary set: was a CEO and/or a CFO among the four-plus buyers?

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule.
Roles use the SAME patterns as ChatGPT's recovered selector (wider.py): a buyer counts as CEO / CFO when the filing
lists him as an Officer and the title matches \\b(CEO|chief executive officer)\\b / \\b(CFO|chief financial officer)\\b.
The title field is often blank, so 'neither identified' can hide a CEO or CFO; the output splits that group by
whether any officer-buyer has a blank title.

Inputs: events JSON from refined_study.py events (carries each event's buyers), the year_*.json files of a refined-study
run (to rebuild the primary set), and the returns_*.json files of a refined-baseline run (the 21-session results).
Usage: python factor_roles.py EVENTS.json YEAR_FOLDER RETURNS_FOLDER      |      --selftest
"""
import json, os, re, statistics, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, assert_allowed, build_primary, quarter

CEO_RE = re.compile(r'\b(?:CEO|chief executive officer)\b', re.I)
CFO_RE = re.compile(r'\b(?:CFO|chief financial officer)\b', re.I)
EXPECT_EVENTS = {'base': 9282, 'refined': 5829}      # Entry 25
SEED = 20261108


def roles(owners):
    """owners: [cik, relationship, title] triples. Returns dict of flags."""
    officers = [o for o in owners if 'Officer' in o[1].split(',')]
    ceo = any(CEO_RE.search(o[2]) for o in officers)
    cfo = any(CFO_RE.search(o[2]) for o in officers)
    return {'ceo': ceo, 'cfo': cfo, 'untitled_officer': any(not o[2].strip() for o in officers),
            'n_officers': len({o[0] for o in officers}), 'n_buyers': len({o[0] for o in owners})}


def stats_line(rows):
    if not rows:
        return 'n=0'
    ex = [r['excess_atr'] for r in rows]
    return (f'n={len(rows)}  stock {statistics.fmean(r["stock_atr"] for r in rows):+.3f}  SPY {statistics.fmean(r["spy_atr"] for r in rows):+.3f}  '
            f'excess {statistics.fmean(ex):+.3f}  median {statistics.median(ex):+.3f}  beat SPY {sum(x > 0 for x in ex)}/{len(rows)}')


def week_of(r):
    return date.fromisoformat(r['entry']).isocalendar()[:2]


def indep(rows):
    return f'{len({r["cik"] for r in rows})} issuers, {len({r["entry"] for r in rows})} dates, {len({week_of(r) for r in rows})} weeks'


def week_boot(rows, draws=10000):
    import random
    wk = defaultdict(lambda: [0.0, 0])
    for r in rows:
        w = wk[week_of(r)]; w[0] += r['excess_atr']; w[1] += 1
    ws = list(wk.values())
    rng = random.Random(SEED)
    ms = sorted(sum(a for a, _ in p) / sum(b for _, b in p) for p in (rng.choices(ws, k=len(ws)) for _ in range(draws)))
    return ms[int(0.025 * draws)], ms[int(0.975 * draws)]


def load(events_path, year_folder, returns_folder):
    from archive_coverage_audit import normalize_ticker
    events = json.loads(Path(events_path).read_text())
    cnt = Counter(e['set'] for e in events)
    if os.environ.get('CLUSTER_WINDOW', '15') == '15':
        assert cnt['base'] == EXPECT_EVENTS['base'] and cnt['refined'] == EXPECT_EVENTS['refined'], dict(cnt)
    else:
        print(f'exploratory cluster window (C38/C39): the Entry 25 event-count check is skipped; counts {dict(cnt)}')
    primary = build_primary(year_folder)
    by_key = defaultdict(list)
    for e in events:
        if e['set'] == 'refined':
            by_key[(e['issuer_cik'], normalize_ticker(e['ticker'])[0], e['entry'])].append(e)
    ret = {}
    for p in sorted(Path(returns_folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            ret[(r['cik'], r['sym'], r['entry'])] = r
    rows, collide, nomatch, noret = [], 0, 0, 0
    for p in primary:
        k = (p['cik'], p['sym'], p['entry'])
        ev = by_key.get(k)
        if not ev:
            nomatch += 1
            continue
        collide += len(ev) > 1
        r = ret.get(k)
        if not r or r['status'] != 'complete':
            noret += 1
            continue
        rows.append({**r, **roles(ev[0]['owners']), 'owners': ev[0]['owners']})
    print(f'primary allowed {len(primary)}; matched to an event with buyers {len(primary) - nomatch}; duplicate-key events {collide}; '
          f'no complete return {noret}; analysed {len(rows)}')
    assert nomatch == 0
    return rows


def perm_test(dev, draws=10000):
    import numpy as np
    dev = sorted(dev, key=week_of)
    ex = np.array([r['excess_atr'] for r in dev])
    lab = np.array([2 * r['ceo'] + r['cfo'] for r in dev])          # 0 neither, 1 CFO only, 2 CEO only, 3 both
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in dev}))}
    wi = np.array([wk[week_of(r)] for r in dev])
    groups = {'CEO among buyers': (2, 3), 'CFO among buyers': (1, 3), 'neither CEO nor CFO': (0,), 'both CEO and CFO': (3,),
              'CEO only': (2,), 'CFO only': (1,)}

    def diffs(l):
        s, n = np.bincount(l, weights=ex, minlength=4), np.bincount(l, minlength=4).astype(float)
        out = {}
        for g, cs in groups.items():
            ni, no = n[list(cs)].sum(), n.sum() - n[list(cs)].sum()
            out[g] = (s[list(cs)].sum() / ni - (s.sum() - s[list(cs)].sum()) / no) if ni and no else 0.0
        return out
    obs = diffs(lab)
    rng = np.random.default_rng(SEED)
    cnt, best_cnt, obs_best = Counter(), 0, max(abs(v) for v in obs.values())
    for _ in range(draws):
        order = np.lexsort((rng.random(len(dev)), wi))              # shuffle labels inside each entry week
        d = diffs(lab[order])
        for g in groups:
            cnt[g] += abs(d[g]) >= abs(obs[g])
        best_cnt += max(abs(v) for v in d.values()) >= obs_best
    return obs, {g: cnt[g] / draws for g in groups}, best_cnt / draws, obs_best


def main(events_path, year_folder, returns_folder):
    rows = load(events_path, year_folder, returns_folder)
    dev = [r for r in rows if r['entry'] <= DEV_END]
    pil = [r for r in rows if r['entry'] > DEV_END]
    off = [o for r in rows for o in r['owners'] if 'Officer' in o[1].split(',')]
    print(f'\nTitle coverage: {len(off)} officer-buyer entries, {sum(not o[2].strip() for o in off)} with a blank title '
          f'({sum(not o[2].strip() for o in off) / len(off):.0%}); events with at least one blank-title officer: '
          f'{sum(r["untitled_officer"] for r in rows)} of {len(rows)} ({sum(r["untitled_officer"] for r in rows) / len(rows):.0%})')
    print(f'Roles found (all): CEO {sum(r["ceo"] for r in rows)}, CFO {sum(r["cfo"] for r in rows)}, both {sum(r["ceo"] and r["cfo"] for r in rows)}, '
          f'neither {sum(not r["ceo"] and not r["cfo"] for r in rows)}')
    cuts = [('CEO among the buyers', lambda r: r['ceo']), ('no CEO identified', lambda r: not r['ceo']),
            ('CFO among the buyers', lambda r: r['cfo']), ('no CFO identified', lambda r: not r['cfo']),
            ('neither CEO nor CFO identified', lambda r: not r['ceo'] and not r['cfo']),
            ('  of which: every officer-buyer has a title', lambda r: not r['ceo'] and not r['cfo'] and not r['untitled_officer']),
            ('  of which: some officer-buyer has a blank title', lambda r: not r['ceo'] and not r['cfo'] and r['untitled_officer']),
            ('CEO and CFO both', lambda r: r['ceo'] and r['cfo']), ('CEO only', lambda r: r['ceo'] and not r['cfo']),
            ('CFO only', lambda r: r['cfo'] and not r['ceo'])]
    for title, rs in (('A. DEVELOPMENT 2006-2020 (entries <= 2020-12-31)', dev), ('B. 2026 PILOT (in-sample, small)', pil)):
        print(f'\n=== {title}: excess over same-window SPY, ATR units, price only ===')
        print(f'all: {stats_line(rs)}')
        for name, f in cuts:
            sub = [r for r in rs if f(r)]
            extra = ''
            if len(sub) > 30 and rs is dev:
                lo, hi = week_boot(sub)
                extra = f'  | mean 95% range {lo:+.3f} to {hi:+.3f}; {indep(sub)}'
            print(f'{name}: {stats_line(sub)}{extra}')
    print('\n=== C. Development without the three large episodes (2008Q4, 2011Q3, 2020Q1) ===')
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    print(f'all: {stats_line(d2)}')
    for name, f in cuts[:5] + cuts[7:]:
        print(f'{name}: {stats_line([r for r in d2 if f(r)])}')
    print('\n=== D. By entry year, development: excess (n)   CEO | CFO | neither ===')
    for y in sorted({r['entry'][:4] for r in dev}):
        cell = lambda f: (lambda s: f'{statistics.fmean(r["excess_atr"] for r in s):+.2f} ({len(s)})' if s else 'none')([r for r in dev if r['entry'][:4] == y and f(r)])
        print(f'{y}: {cell(lambda r: r["ceo"])} | {cell(lambda r: r["cfo"])} | {cell(lambda r: not r["ceo"] and not r["cfo"])}')
    print('\n=== E. Chance test: labels shuffled among trades inside the same entry week (10,000 shuffles, development only) ===')
    obs, p1, pbest, obs_best = perm_test(dev)
    print('group vs everyone else: observed difference in mean excess (ATR), chance of a difference this large (two-sided, this question alone)')
    for g in obs:
        print(f'  {g}: {obs[g]:+.3f}, chance {p1[g]:.1%}')
    print(f'Best of this menu of 6 splits: largest observed |difference| {obs_best:.3f}; chance the best of 6 is at least that large by luck {pbest:.1%}')
    print('Questions asked on this cohort in this entry: 6 splits (CEO, CFO, neither, both, CEO only, CFO only) plus their complements.')


def selftest():
    o = [['1', 'Director,Officer', 'Chief Executive Officer'], ['2', 'Director', ''], ['3', 'Officer', 'SVP'], ['4', 'Director', '']]
    r = roles(o)
    assert r['ceo'] and not r['cfo'] and not r['untitled_officer'] and r['n_buyers'] == 4 and r['n_officers'] == 2, r
    r = roles([['1', 'Officer', 'CFO & Treasurer'], ['2', 'Officer', ''], ['3', 'Director', ''], ['4', 'Director', '']])
    assert r['cfo'] and not r['ceo'] and r['untitled_officer']
    r = roles([['1', 'Director', 'Chief Financial Officer'], ['2', 'Director', ''], ['3', 'Director', ''], ['4', 'Director', '']])
    assert not r['cfo'], 'a title on a director-only filing is not counted (same as the recovered selector)'
    assert not roles([['1', 'Officer', 'President']])['ceo']
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float(k % 5) - 1.0, 'stock_atr': 0.0, 'spy_atr': 0.0, 'cik': str(k),
             'ceo': k % 2 == 0, 'cfo': k % 3 == 0} for k in range(80)]
    a = perm_test(rows, 200)
    b = perm_test(rows, 200)
    assert a == b
    print('factor_roles self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    else:
        main(*sys.argv[1:4])
