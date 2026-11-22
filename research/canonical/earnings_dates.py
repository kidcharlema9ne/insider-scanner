"""C34 (declared 9 Nov 2026, BEFORE any run; Michael: "Can you get earnings dates on all these stocks or not? Easily").  COVERAGE TEST ONLY, no returns joined.

Source: the SEC's own filing index for each company (https://data.sec.gov/submissions/CIK##########.json, plus the older-filings files it points to), read with the
SEC_USER_AGENT secret at no more than 5 requests a second.  An EARNINGS DATE here = the filing date of an 8-K that carries Item 2.02 (Results of Operations and
Financial Condition), which is how U.S. companies announce results; the fallback = the filing date of the next 10-Q or 10-K.  Known limits: Item 2.02 exists
only from August 2004 (all development entries are 2006+); the 8-K is filed the day of or after the press release, and a release made after the close is
filed the same evening, so the date can be one session late for after-close reporters; some small companies announce results only inside the 10-Q;
companies that left the SEC system early may have a thin index.  No time of day is available, so before-open versus after-close is NOT known.

Per signal (entry session E = the next open after the four-buyer filing): (a) company found in the index; (b) an Item 2.02 8-K within 130 calendar days either
side of E (proxy for 'this company announces through 8-K'); (c) days since the last Item 2.02 before E; (d) days from E to the next Item 2.02; (e) share whose
42-session hold (about 59 calendar days) contains an earnings date, by Item 2.02 and by the 10-Q/10-K fallback.  Groups: all development signals and the deep-fall
rule (down 15+ ATR over 12 months).  Development entries only (D-068).

Usage:  python earnings_dates.py fetch --primary FILE --out FILE
        python earnings_dates.py scan CACHE.json EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER
        python earnings_dates.py --selftest
"""
import json, os, statistics, sys, time, urllib.error, urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, assert_allowed

BASE = 'https://data.sec.gov/submissions/'
HOLD_DAYS = 59


def get(url, agent):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': agent, 'Accept-Encoding': 'identity'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 + 3 * attempt)
        except Exception:
            time.sleep(2 + 3 * attempt)
    return 'ERR'


def extract(block):
    """From a submissions 'recent'-style block: list of [filingDate, form, items]."""
    f, d, it = block.get('form', []), block.get('filingDate', []), block.get('items', [])
    return [[d[k], f[k], it[k] if k < len(it) else ''] for k in range(len(f)) if f[k] in ('8-K', '8-K/A', '10-Q', '10-K', '10-Q/A', '10-K/A', '10-KT')]


def fetch(primary_path, out):
    agent = os.environ['SEC_USER_AGENT'].strip()
    events = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'] <= DEV_END]
    for e in events:
        assert_allowed(e['entry'])
    ciks = sorted({str(e['cik']).zfill(10) for e in events})
    print(f'{len(events)} development signals, {len(ciks)} companies')
    cache, status = {}, {'ok': 0, 'not_found': 0, 'error': 0}
    for n, c in enumerate(ciks):
        time.sleep(0.2)
        js = get(f'{BASE}CIK{c}.json', agent)
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
                extra = get(BASE + fl['name'], agent)
                if isinstance(extra, dict):
                    rows += extract(extra)
        cache[c] = rows
        status['ok'] += 1
        if n % 100 == 0:
            print(f'  {n}/{len(ciks)} {status}', flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(cache))
    print(f'fetch done {status}')


def d(s):
    return date.fromisoformat(s)


def earnings(rows):
    e202 = sorted(r[0] for r in rows if r[1].startswith('8-K') and '2.02' in (r[2] or '').split(','))
    per = sorted(r[0] for r in rows if r[1].startswith(('10-Q', '10-K')))
    return e202, per


def facts(entry, e202, per):
    E = d(entry)
    near = [x for x in e202 if abs((d(x) - E).days) <= 130]
    before = [(E - d(x)).days for x in e202 if d(x) <= E]
    after = [(d(x) - E).days for x in e202 if d(x) >= E]
    pafter = [(d(x) - E).days for x in per if d(x) >= E]
    return {'near': bool(near), 'since': min(before) if before else None, 'next': min(after) if after else None,
            'span202': bool(after) and min(after) <= HOLD_DAYS, 'spanper': bool(pafter) and min(pafter) <= HOLD_DAYS,
            'span_any': (bool(after) and min(after) <= HOLD_DAYS) or (bool(pafter) and min(pafter) <= HOLD_DAYS)}


def table(name, rows, cache):
    n = len(rows)
    found = [r for r in rows if str(r['cik']).zfill(10) in cache]
    fs = []
    for r in found:
        e202, per = earnings(cache[str(r['cik']).zfill(10)])
        fs.append(facts(r['entry'], e202, per))
    near = [f for f in fs if f['near']]
    nxt = [f['next'] for f in fs if f['next'] is not None]
    since = [f['since'] for f in fs if f['since'] is not None]
    pct = lambda a, b: f'{a / b:.0%}' if b else 'n/a'
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))] if v else float('nan')
    print(f'\n=== {name}: signals {n} ===')
    print(f'  company found in the SEC index: {len(found)} ({pct(len(found), n)})')
    print(f'  Item 2.02 8-K within 130 days either side of entry: {len(near)} ({pct(len(near), n)} of all signals; {pct(len(near), len(found))} of found)')
    print(f'  days since the last Item 2.02 before entry: median {statistics.median(since) if since else float("nan")}, 90th pct {q(since, .9)}  (n={len(since)})')
    print(f'  days from entry to the next Item 2.02: median {statistics.median(nxt) if nxt else float("nan")}, 90th pct {q(nxt, .9)}  (n={len(nxt)})')
    print(f'  42-session hold (~{HOLD_DAYS} days) contains an earnings date: by Item 2.02 {sum(f["span202"] for f in fs)} ({pct(sum(f["span202"] for f in fs), len(fs))}); '
          f'by the next 10-Q/10-K only {sum(f["spanper"] for f in fs)} ({pct(sum(f["spanper"] for f in fs), len(fs))}); by either {sum(f["span_any"] for f in fs)} ({pct(sum(f["span_any"] for f in fs), len(fs))})')
    nofound = [r for r in rows if str(r['cik']).zfill(10) not in cache]
    print(f'  not found or error: {len(nofound)} e.g. ' + ', '.join(f'{r["sym"]}' for r in nofound[:15]))


def scan(cache_path, events, years, decl, regime, ret):
    import score_scan as ss
    cache = json.loads(Path(cache_path).read_text())
    dev = ss.build(events, years, decl, regime, ret)
    for r in dev:
        r['F'] = r['raw252'] <= -15.0
    table('All development signals with features', dev, cache)
    table('Deep-fall rule (down 15+ ATR over 12 months)', [r for r in dev if r['F']], cache)
    print('\nCoverage test only; the date is the SEC filing date of the 8-K (can be one session after an after-close release); no time of day.')


def selftest():
    blk = {'form': ['8-K', '8-K', '10-Q', '4'], 'filingDate': ['2010-05-03', '2010-06-01', '2010-05-10', '2010-05-11'], 'items': ['2.02,9.01', '5.02', '', '']}
    rows = extract(blk)
    assert len(rows) == 3
    e202, per = earnings(rows)
    assert e202 == ['2010-05-03'] and per == ['2010-05-10']
    f = facts('2010-04-20', e202, per)
    assert f['next'] == 13 and f['span202'] and f['near'] and f['since'] is None, f
    f = facts('2010-07-01', e202, per)
    assert f['next'] is None and not f['span_any'] and f['since'] == 59, f
    print('selftest ok: extraction, Item 2.02 detection, windows')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    if sys.argv[1] == 'fetch':
        a = sys.argv[2:]
        fetch(a[a.index('--primary') + 1], a[a.index('--out') + 1])
    elif sys.argv[1] == 'scan':
        scan(*sys.argv[2:])
