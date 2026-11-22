"""C35 (declared 9 Nov 2026, BEFORE any run; Michael: "Yeah, do the bankruptcy and delisting").  What happened, from SEC filings, to the companies behind the
signals - above all those with NO price series in the archive (the group that can hide wipe-outs).  Counts only; no return is joined; development entries only (D-068).

Population: refined events 2006-2020 (the census of Entry 38, from the year-*.json files of the refined-study run), split by archive status: 'priced' (any status
other than no_price) and 'no_price'.  Source: the SEC filing index of each company (data.sec.gov submissions, SEC_USER_AGENT, 5 requests a second).
CLASSES, first match wins, looked for in the window from the entry date (E) forward (calendar days; 59 days ~ the 42-session hold; also 120 and 365):
  1 BANKRUPTCY_OR_RECEIVERSHIP: an 8-K carrying Item 1.03.
  2 ACQUIRED: an 8-K carrying Item 2.01 (completion of acquisition), or a merger/tender document (DEFM14A, SC 14D9, SC TO-T, 425, S-4) AND a Form 15 or 25 in the window.
  3 DELISTED_OR_DEREGISTERED: an 8-K carrying Item 3.01 (delisting notice), or any Form 15 / Form 25 in the window.
  4 ACTIVE: none of the above.
Known limits: a bank closed by regulators may file none of these (its holding company often stops filing: it then shows as 3 or 4); Form 15 can follow a bankruptcy,
a buy-out, or a voluntary exit (class 3 mixes these); 8-K Item 1.03 only exists from 2005; a company can file late.  The classes are a SEC-filings proxy, not a
price outcome.  SPOT CHECK printed: up to 20 class-1 tickers with entry dates in the 59-day window, so they can be checked by eye.

THEN, a bound for the deep-fall rule (down 15+ ATR over 12 months; n=269 at plain 42 sessions excess +1.123; 2011-20 n=161, +0.600): B = number of no_price
refined events, development years, in class 1 within 59 days of entry.  Scenario: a share s (100%, 50%, 25%) of them would have passed the $3M floor AND been in the
deep-fall group (an upper-end assumption: a company bankrupt within two months has usually already collapsed, but many are too thin for the floor).  Each is a
wipe-out of -55% = about -9.0 ATR on average (Entry 65; -10.5 for 2011-20) minus the SPY leg of the same hold (+0.435), so about -9.4 ATR excess.  Implied excess =
(n * mean + m * x) / (n + m) with m = s * B (all years, and 2011-20 only).  Printed beside the break-even of Entry 65 (about 5% to 6% wipe-outs erase the edge).
This is a bound under stated assumptions, not a measurement of the deep-fall wipe-out rate.

Usage:  python delisting_check.py run YEAR_FOLDER --out CACHE.json
        python delisting_check.py --selftest
"""
import json, os, statistics, sys, time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, assert_allowed
import earnings_dates as ed

WINDOWS = (59, 120, 365)
KEEP_PREFIX = ('15', '25', 'DEFM14A', 'SC 14D9', 'SC TO-T', '425', 'S-4')


def extract(block):
    f, d, it = block.get('form', []), block.get('filingDate', []), block.get('items', [])
    out = []
    for k in range(len(f)):
        if f[k].startswith('8-K') or f[k].startswith(KEEP_PREFIX):
            out.append([d[k], f[k], it[k] if k < len(it) else ''])
    return out


def classify(entry, rows, win):
    E = date.fromisoformat(entry)
    inwin = [r for r in rows if 0 <= (date.fromisoformat(r[0]) - E).days <= win]
    items = lambda r: (r[2] or '').split(',')
    if any(r[1].startswith('8-K') and '1.03' in items(r) for r in inwin):
        return 'bankruptcy_or_receivership'
    f1525 = any(r[1].startswith(('15', '25')) for r in inwin)
    if any(r[1].startswith('8-K') and '2.01' in items(r) for r in inwin) or \
            (f1525 and any(r[1].startswith(('DEFM14A', 'SC 14D9', 'SC TO-T', '425', 'S-4')) for r in inwin)):
        return 'acquired'
    if f1525 or any(r[1].startswith('8-K') and '3.01' in items(r) for r in inwin):
        return 'delisted_or_deregistered'
    return 'active'


CLASSES = ('bankruptcy_or_receivership', 'acquired', 'delisted_or_deregistered', 'active')


def fetch_all(ciks, agent, out):
    cache, status = {}, Counter()
    for n, c in enumerate(ciks):
        time.sleep(0.2)
        js = ed.get(f'{ed.BASE}CIK{c}.json', agent)
        if js is None:
            status['not_found'] += 1
            continue
        if js == 'ERR':
            status['error'] += 1
            continue
        rows = extract(js.get('filings', {}).get('recent', {}))
        for fl in js.get('filings', {}).get('files', []):
            if fl.get('filingTo', '9999') >= '2005-01-01' and fl.get('filingFrom', '0000') <= '2022-01-01':
                time.sleep(0.2)
                extra = ed.get(ed.BASE + fl['name'], agent)
                if isinstance(extra, dict):
                    rows += extract(extra)
        cache[c] = rows
        status['ok'] += 1
        if n % 200 == 0:
            print(f'  {n}/{len(ciks)} {dict(status)}', flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(cache))
    print(f'fetch done {dict(status)}')
    return cache


def run(year_dir, out):
    agent = os.environ['SEC_USER_AGENT'].strip()
    ev = []
    for fn in sorted(Path(year_dir).glob('year_*.json')):
        for r in json.loads(Path(fn).read_text())['results']:
            if r['set'] != 'refined' or r['entry'] > DEV_END:
                continue
            assert_allowed(r['entry'])
            ev.append({'cik': str(r['cik']).zfill(10), 'entry': r['entry'], 'sym': r['sym'], 'priced': r['status'] != 'no_price'})
    print(f'refined development events {len(ev)}; priced {sum(e["priced"] for e in ev)}; no_price {sum(not e["priced"] for e in ev)}')
    ciks = sorted({e['cik'] for e in ev})
    print(f'{len(ciks)} companies to fetch')
    cache = fetch_all(ciks, agent, out)
    for e in ev:
        rows = cache.get(e['cik'])
        e['found'] = rows is not None
        for w in WINDOWS:
            e[f'c{w}'] = classify(e['entry'], rows, w) if rows is not None else 'not_in_index'
    report(ev)


def report(ev):
    pct = lambda a, b: f'{a / b:.1%}' if b else 'n/a'
    for name, g in (('PRICED events (in the archive)', [e for e in ev if e['priced']]), ('NO-PRICE events (missing from the archive)', [e for e in ev if not e['priced']])):
        print(f'\n=== {name}: n={len(g)}; company found in the SEC index {sum(e["found"] for e in g)} ({pct(sum(e["found"] for e in g), len(g))}) ===')
        for w in WINDOWS:
            c = Counter(e[f'c{w}'] for e in g)
            print(f'  within {w:3d} days of entry: ' + ', '.join(f'{k} {c.get(k, 0)} ({pct(c.get(k, 0), len(g))})' for k in CLASSES) + (f', not in index {c.get("not_in_index", 0)}' if c.get('not_in_index') else ''))
    print('\n=== NO-PRICE events by entry year: n | bankruptcy/receivership within 59 / 365 days | acquired within 365 | delisted/deregistered within 365 | active at 365 ===')
    yrs = sorted({e['entry'][:4] for e in ev})
    for y in yrs:
        g = [e for e in ev if not e['priced'] and e['entry'][:4] == y]
        if g:
            print(f'  {y}: {len(g):4d} | {sum(e["c59"] == CLASSES[0] for e in g):3d} / {sum(e["c365"] == CLASSES[0] for e in g):3d} | {sum(e["c365"] == CLASSES[1] for e in g):3d} | {sum(e["c365"] == CLASSES[2] for e in g):3d} | {sum(e["c365"] == CLASSES[3] for e in g):3d}')
    print('\n=== PRICED events by entry year (for comparison): n | bankruptcy/receivership within 59 / 365 days ===')
    for y in yrs:
        g = [e for e in ev if e['priced'] and e['entry'][:4] == y]
        if g:
            print(f'  {y}: {len(g):4d} | {sum(e["c59"] == CLASSES[0] for e in g):3d} / {sum(e["c365"] == CLASSES[0] for e in g):3d}')
    b59 = [e for e in ev if not e['priced'] and e['c59'] == CLASSES[0]]
    print('\nSPOT CHECK, no-price events in class 1 within 59 days: ' + ', '.join(f'{e["sym"]} {e["entry"]}' for e in sorted(b59, key=lambda e: e['entry'])[:20]))
    pb59 = [e for e in ev if e['priced'] and e['c59'] == CLASSES[0]]
    print('SPOT CHECK, PRICED events in class 1 within 59 days (the archive does hold these): ' + ', '.join(f'{e["sym"]} {e["entry"]}' for e in sorted(pb59, key=lambda e: e['entry'])[:20]))
    B_all = len(b59)
    B_1120 = len([e for e in b59 if e['entry'] >= '2011-01-01'])
    print(f'\n=== Bound for the deep-fall rule: B = no-price events bankrupt within 59 days: all years {B_all}, 2011-20 {B_1120} ===')
    for label, n, mean, B, L in (('2006-2020', 269, 1.123, B_all, -9.0), ('2011-2020', 161, 0.600, B_1120, -10.5)):
        x = L - 0.435
        for s in (1.0, 0.5, 0.25):
            m = s * B
            new = (n * mean + m * x) / (n + m)
            print(f'  {label}: n={n}, mean {mean:+.3f}; if {s:.0%} of the {B} would be extra deep-fall wipe-outs (m={m:.1f}, {m / (n + m):.1%} of trades, x={x:+.1f} ATR): implied excess {new:+.3f}')
    print('\nCounts from SEC filings only (a proxy, not a price outcome); the bound rests on stated assumptions; no return was joined.')


def selftest():
    rows = [['2009-03-02', '8-K', '1.03,9.01'], ['2009-03-20', '15-12G', ''], ['2010-01-05', '8-K', '2.01']]
    assert classify('2009-02-20', rows, 59) == 'bankruptcy_or_receivership'
    assert classify('2009-02-20', rows, 5) == 'active'
    assert classify('2009-10-01', rows, 120) == 'acquired'
    assert classify('2009-03-10', [['2009-03-20', '15-12G', '']], 59) == 'delisted_or_deregistered'
    assert classify('2009-03-10', [['2009-03-15', 'DEFM14A', ''], ['2009-03-20', '15-12G', '']], 59) == 'acquired'
    assert classify('2009-03-10', [['2009-03-15', '8-K', '3.01']], 59) == 'delisted_or_deregistered'
    assert classify('2009-03-10', [['2009-03-01', '8-K', '1.03']], 59) == 'active'
    blk = {'form': ['8-K', '4', '15-12G', 'SC 14D9'], 'filingDate': ['2010-05-03', '2010-05-04', '2010-05-05', '2010-05-06'], 'items': ['1.03', '', '', '']}
    assert len(extract(blk)) == 3
    print('selftest ok: classes, windows, extraction')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    if sys.argv[1] == 'run':
        run(sys.argv[2], sys.argv[sys.argv.index('--out') + 1])
