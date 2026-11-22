"""Do the events removed by the D-064 routine-purchase exclusion behave differently from the events kept?

DIAGNOSTIC on development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068 guard in refined_baseline).
Groups (all require identity fine and the $3M floor, same as the primary set):
  kept_C      refined events after option C   (= the primary set, Entry 25)
  removed_raw base events with no refined event on the same issuer and entry date, no option C
  removed_C   the same removed events after option C (first per issuer, then wait out 21 sessions)
Returns come from refined_baseline.year_job (same definition as Entry 28). Nothing here changes D-064.

Subcommands
  select FOLDER --out FILE      build the unique event list and the group file from year_*.json (refined-study run)
  summary RETURNS_FOLDER GROUPS compare the groups
  --selftest
"""
import argparse, json, random, statistics, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, allowed, assert_allowed, quarter, EPISODES


def split_groups(base, refined, fine, collapse, idx_of):
    rkeys = {(e['cik'], e['entry']) for e in refined}
    ok = lambda e: e['status'] in fine and e['liquid']
    kept_c = collapse([e for e in refined if ok(e)], idx_of)
    removed = [e for e in base if (e['cik'], e['entry']) not in rkeys and ok(e)]
    removed_c = collapse(removed, idx_of)
    return {'kept_C': kept_c, 'removed_raw': removed, 'removed_C': removed_c}


def select(folder, out):
    from refined_study import FINE, collapse
    from cluster_counts_by_year import sessions
    cal = sessions()
    idx_of = lambda d: bisect_left(cal, d)
    years = [json.loads(p.read_text()) for p in sorted(Path(folder).glob('year_*.json'))]
    res = lambda s: [r for y in years for r in y['results'] if r['set'] == s]
    groups = split_groups(res('base'), res('refined'), FINE, collapse, idx_of)
    unique, member = {}, defaultdict(list)
    for g, items in groups.items():
        for e in items:
            if not allowed(e['entry']):
                continue
            k = f"{e['sym']}|{e['entry']}|{e['cik']}"
            unique[k] = {'sym': e['sym'], 'entry': e['entry'], 'cik': e['cik'], 'via': e.get('via')}
            member[k].append(g)
    for g, items in groups.items():
        print(f'{g}: {len(items)} tradable events 2006-2026; allowed under D-068: {sum(g in v for v in member.values())}')
    assert sum('kept_C' in v for v in member.values()) == 1453, 'kept_C must equal the 1,453 allowed primary entries (Entry 28)'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'events': list(unique.values()), 'groups': member}))
    Path(out).with_name('events_to_price.json').write_text(json.dumps(list(unique.values())))
    print(f'unique events to price: {len(unique)}')


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


def boot_diff(a, b, draws=10000, seed=20261108):
    """Week-block bootstrap of mean(a) - mean(b), resampling weeks from the union."""
    wk = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r in a:
        w = wk[week_of(r)]; w[0] += r['excess_atr']; w[1] += 1
    for r in b:
        w = wk[week_of(r)]; w[2] += r['excess_atr']; w[3] += 1
    weeks = list(wk.values())
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        pick = rng.choices(weeks, k=len(weeks))
        na, nb = sum(w[1] for w in pick), sum(w[3] for w in pick)
        if na and nb:
            out.append(sum(w[0] for w in pick) / na - sum(w[2] for w in pick) / nb)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))], sum(d <= 0 for d in out) / len(out)


def issuer_mean(rows):
    per = defaultdict(list)
    for r in rows:
        per[r['cik']].append(r['excess_atr'])
    return statistics.fmean(statistics.fmean(v) for v in per.values()), len(per)


def summary(folder, groups_path):
    g = json.loads(Path(groups_path).read_text())['groups']
    rows = {}
    for p in sorted(Path(folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            rows[f"{r['sym']}|{r['entry']}|{r['cik']}"] = r
    by = {name: [rows[k] for k, v in g.items() if name in v and k in rows and rows[k]['status'] == 'complete']
          for name in ('kept_C', 'removed_raw', 'removed_C')}
    miss = {name: sum(1 for k, v in g.items() if name in v and (k not in rows or rows[k]['status'] != 'complete')) for name in by}
    print('=== A. Completed 21-session trades by group, excess over same-window SPY in ATR (price only) ===')
    for name, rs in by.items():
        print(f'{name}: {stats_line(rs)}   [not completed: {miss[name]}]')
        print(f'    independence: {indep(rs)}')
    print('\n=== B. Development years only (entries <= 2020-12-31) ===')
    dev = {n: [r for r in rs if r['entry'] <= DEV_END] for n, rs in by.items()}
    for name, rs in dev.items():
        m, ni = issuer_mean(rs)
        print(f'{name}: {stats_line(rs)}')
        print(f'    equal weight per issuer: {m:+.3f} over {ni} issuers')
    print('\n=== C. Removed vs kept: difference in mean excess, week-block bootstrap (10,000 draws, seed 20261108) ===')
    for label, a, b in (('removed_C minus kept_C (development)', dev['removed_C'], dev['kept_C']),
                        ('removed_raw minus kept_C (development)', dev['removed_raw'], dev['kept_C'])):
        d = statistics.fmean(r['excess_atr'] for r in a) - statistics.fmean(r['excess_atr'] for r in b)
        lo, hi, p = boot_diff(a, b)
        print(f'{label}: {d:+.3f}, 95% range {lo:+.3f} to {hi:+.3f}, share of draws <= 0 {p:.1%}')
    print('\n=== D. Concentration of the removed events (development, removed_raw) ===')
    cnt = defaultdict(list)
    for r in dev['removed_raw']:
        cnt[r['cik']].append(r['excess_atr'])
    top = sorted(cnt.items(), key=lambda kv: -len(kv[1]))[:8]
    tot = len(dev['removed_raw'])
    print(f'top 8 issuers hold {sum(len(v) for _, v in top)} of {tot} events ({sum(len(v) for _, v in top) / tot:.0%}); '
          + '; '.join(f'{c} n={len(v)} mean {statistics.fmean(v):+.2f}' for c, v in top))
    print('\n=== E. By entry year, development: excess (n)  kept_C | removed_C ===')
    for y in sorted({r['entry'][:4] for r in dev['kept_C'] + dev['removed_C']}):
        f = lambda rs: (f'{statistics.fmean(r["excess_atr"] for r in rs if r["entry"][:4] == y):+.2f} ({sum(r["entry"][:4] == y for r in rs)})'
                        if any(r['entry'][:4] == y for r in rs) else 'none')
        print(f'{y}: {f(dev["kept_C"])} | {f(dev["removed_C"])}')
    print('\n=== F. Without the three large episodes (development) ===')
    for name in ('kept_C', 'removed_C'):
        print(f'{name}: {stats_line([r for r in dev[name] if quarter(r["entry"]) not in EPISODES])}')
    print('\n=== G. 2026 pilot, in-sample ===')
    for name, rs in by.items():
        print(f'{name}: {stats_line([r for r in rs if r["entry"] >= "2026-01-01"])}')


def selftest():
    fine = {'ok'}
    mk = lambda cik, entry, st='ok', liq=True, s='base': {'cik': cik, 'entry': entry, 'sym': 'X' + cik, 'status': st, 'liquid': liq, 'set': s}
    collapse = lambda items, idx_of: sorted(items, key=lambda e: (e['cik'], e['entry']))[:99]
    base = [mk('1', '2010-01-04'), mk('2', '2010-01-05'), mk('3', '2010-01-06'), mk('4', '2010-01-07', liq=False), mk('5', '2010-01-08', st='mismatch')]
    refined = [mk('1', '2010-01-04', s='refined'), mk('6', '2010-02-01', s='refined')]
    g = split_groups(base, refined, fine, collapse, None)
    assert [e['cik'] for e in g['kept_C']] == ['1', '6']
    assert [e['cik'] for e in g['removed_raw']] == ['2', '3'], g['removed_raw']
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float(k % 5) - 1.0, 'cik': str(k)} for k in range(40)]
    assert boot_diff(rows[:20], rows[20:], 200) == boot_diff(rows[:20], rows[20:], 200)
    print('removed_events_check self-test passed')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['select', 'summary'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'select':
        select(a.arg, a.out)
    elif a.cmd == 'summary':
        summary(a.arg, a.arg2)
    else:
        ap.error('give a subcommand or --selftest')
