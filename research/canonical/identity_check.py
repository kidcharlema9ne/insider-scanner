"""Ticker-to-security identity check for the four-plus-buyer events (Entry 19 'Next').

Question: when an event's ticker is matched to a MarketParquet series by symbol, is it the same company?
Test: the insiders' own weighted purchase price (Form 4) must be close to the archive close on or just before the
purchase date. A reused ticker (BBI, MON, WM) or a split-adjusted series fails this test. No return is computed:
the test compares a purchase price with a close on the SAME past date, entirely before the entry.

Also reports, for the chosen series:
  * the D-061 $3M floor re-run (15 prior bars, mean close x volume) split by identity status;
  * for -DELISTED series only, and ONLY for development entries (<= 2019-12-31) and the 2026 pilot (D-063,
    Entry 17 safeguard): where the series ends (calendar days after entry) and its last close, in price buckets.
    Sealed-period (2020-04-01 .. 2025-12-31) entries get NO terminal information at all.

Subcommands
  events    build four-plus-buyer events WITH the buyers' purchase dates and weighted prices
  year      match one entry year against the archive and write year_YYYY.json
  summary   merge the year files and print the tables
  --selftest

Status of each event's chosen series: ok (median price ratio inside 0.75..1.33), contradicted, unverifiable (no
purchase price or no close within 7 days), no_price (no bar in the 15 sessions before entry).
"""
import argparse, datetime as dt, json, statistics
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from archive_coverage_audit import DELISTED, FLOOR, WINDOW, key_date, list_dates, normalize_ticker, read_file

OK_LO, OK_HI = 0.75, 1 / 0.75
MAX_STALE_DAYS = 7
HOLD_DAYS = 31          # about 21 sessions
DEV_END, SEALED_START, SEALED_END, PILOT_START = '2019-12-31', '2020-04-01', '2025-12-31', '2026-01-01'
RANK = {'ok': 2, 'unverifiable': 1, 'contradicted': 0}


def days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def ratios_for(purchases, closes):
    """purchases: [(date, price)], closes: {date: close}. Price / last close on or before the purchase date."""
    dates = sorted(closes)
    out = []
    for d, p in purchases:
        if not p or p <= 0:
            continue
        i = bisect_right(dates, d)
        if i == 0 or days_between(dates[i - 1], d) > MAX_STALE_DAYS:
            continue
        out.append(p / closes[dates[i - 1]])
    return out


def identity_status(ratios):
    if not ratios:
        return 'unverifiable', None
    med = statistics.median(ratios)
    return ('ok' if OK_LO <= med <= OK_HI else 'contradicted'), med


def window_stats(all_dates, entry, closes, dvol):
    i = bisect_left(all_dates, entry)
    win = all_dates[max(0, i - WINDOW):i]
    vals = [dvol[d] for d in win if d in dvol]
    bars = len([d for d in win if d in closes])
    mean = sum(vals) / len(vals) if vals else None
    return bars, len(win), mean


def evaluate_event(e, all_dates, series):
    """series: {'plain': (closes, dvol), 'delisted': (closes, dvol)}. Returns the chosen-series record."""
    best = None
    for via, (closes, dvol) in series.items():
        bars, nwin, mean = window_stats(all_dates, e['entry'], closes, dvol)
        if bars == 0:
            continue
        ratios = ratios_for([tuple(p) for p in e['purchases']], closes)
        status, med = identity_status(ratios)
        cand = {'via': via, 'status': status, 'ratio': med, 'n_cmp': len(ratios), 'bars': bars,
                'liquid': bars == WINDOW and nwin == WINDOW and mean is not None and mean >= FLOOR}
        if best is None or (RANK[status], bars) > (RANK[best['status']], best['bars']):
            best = cand
    if best is None:
        return {'status': 'no_price', 'via': None, 'ratio': None, 'n_cmp': 0, 'bars': 0, 'liquid': False}
    return best


def terminal_bucket(last_close):
    for hi, name in ((0.5, '<0.50'), (1, '0.50-1'), (5, '1-5'), (20, '5-20')):
        if last_close < hi:
            return name
    return '>=20'


def terminal_allowed(entry):
    return entry <= DEV_END or entry >= PILOT_START


# ---------------------------------------------------------------- events
def find_events_priced(rows, cal):
    """Same crossing logic as cluster_counts_by_year.find_events, plus the purchases behind each event."""
    from cluster_counts_by_year import usable
    by_security = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not usable(row):
            continue
        i = bisect_right(cal, row['filing_date'])
        if i >= len(cal):
            continue
        by_security[(row['issuer_cik'], row['ticker_at_filing'], row['security_title'].upper())][i].append(row)
    events = []
    for key, by_idx in by_security.items():
        if len({r['owners'][0]['cik'] for rs in by_idx.values() for r in rs}) < 4:
            continue
        seen = []
        for i in sorted(by_idx):
            entry, start = cal[i], cal[max(0, i - WINDOW)]
            ok = lambda r: any(start <= d < entry for d in r['transaction_dates'])
            seen = [r for r in seen if ok(r)]
            before = {r['owners'][0]['cik'] for r in seen}
            seen.extend(r for r in by_idx[i] if ok(r))
            after = {r['owners'][0]['cik'] for r in seen}
            if len(before) < 4 <= len(after):
                purchases = []
                for r in seen:
                    price = float(r['insider_weighted_price']) if r.get('insider_weighted_price') else None
                    purchases += [(d, price) for d in r['transaction_dates'] if start <= d < entry]
                events.append({'issuer_cik': key[0], 'ticker': key[1], 'entry': entry, 'buyers': len(after),
                               'purchases': purchases})
    return events


def build_events(out):
    import tempfile
    from cluster_counts_by_year import fetch_db, find_events, load_rows, sessions
    with tempfile.TemporaryDirectory() as tmp:
        rows = list(load_rows(fetch_db(tmp)))
        cal = sessions()
        events = find_events_priced(rows, cal)
        base = find_events(rows, cal)
    k = lambda ev: sorted((e['issuer_cik'], e['ticker'], e['entry'], e['buyers']) for e in ev)
    assert k(events) == k(base), 'priced events differ from the Entry 15/19 events'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(events))
    priced = sum(1 for e in events if any(p for _, p in e['purchases']))
    print(f'events: {len(events)} (identical to cluster_counts_by_year.find_events); with at least one purchase price: {priced}')


# ---------------------------------------------------------------- year job
def load_year(s3, year, need_close, need_term):
    keys = list_dates(s3, 'stock', year)
    closes, dvol, term = defaultdict(dict), defaultdict(dict), {}
    with ThreadPoolExecutor(8) as pool:
        for start in range(0, len(keys), 32):
            for key, _, t in pool.map(lambda k: read_file(s3, k), keys[start:start + 32]):
                day = key_date(key)
                for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                    if c is None or c <= 0:
                        continue
                    if s in need_close:
                        closes[s][day] = c
                        if v is not None and v >= 0:
                            dvol[s][day] = c * v
                    if s in need_term:
                        term[s] = (day, c)
    return closes, dvol, term, [key_date(k) for k in keys]


def year_job(year, events_path, out):
    from r2_storage import client
    s3 = client()
    allev = json.loads(Path(events_path).read_text())
    for e in allev:
        e['sym'], e['tcat'] = normalize_ticker(e['ticker'])
    events = [e for e in allev if e['entry'].startswith(str(year)) and e['tcat'] == 'ok']
    need_close = {x for e in events for x in (e['sym'], e['sym'] + DELISTED)}
    need_term = {e['sym'] + DELISTED for e in allev if e['tcat'] == 'ok'}
    closes, dvol, term, dates = load_year(s3, year, need_close, need_term)
    tail = list_dates(s3, 'stock', year - 1)[-WINDOW - 10:]
    tail_dates = []
    with ThreadPoolExecutor(8) as pool:
        for key, _, t in pool.map(lambda k: read_file(s3, k), tail):
            day = key_date(key)
            tail_dates.append(day)
            for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                if s in need_close and c and c > 0:
                    closes[s][day] = c
                    if v is not None and v >= 0:
                        dvol[s][day] = c * v
    all_dates = sorted(set(tail_dates) | set(dates))
    results = []
    for e in events:
        series = {'plain': (closes.get(e['sym'], {}), dvol.get(e['sym'], {})),
                  'delisted': (closes.get(e['sym'] + DELISTED, {}), dvol.get(e['sym'] + DELISTED, {}))}
        r = evaluate_event(e, all_dates, series)
        r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['issuer_cik']})
        results.append(r)
    skipped = Counter(e['tcat'] for e in allev if e['entry'].startswith(str(year)) and e['tcat'] != 'ok')
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'results': results, 'skipped_ticker': dict(skipped),
                                     'terminal': {s: list(v) for s, v in term.items()}}))
    print(f"{year}: events {len(events)} {dict(Counter(r['status'] for r in results))}")


def diagnose_year(year, events_path):
    """Print raw purchase prices beside archive closes for contradicted events (SYBT, GABC, low and high ratios).
    Read-only; prints only prices on past purchase dates and series ends, never anything after entry."""
    from r2_storage import client
    s3 = client()
    allev = json.loads(Path(events_path).read_text())
    for e in allev:
        e['sym'], e['tcat'] = normalize_ticker(e['ticker'])
    events = [e for e in allev if e['entry'].startswith(str(year)) and e['tcat'] == 'ok']
    need = {x for e in events for x in (e['sym'], e['sym'] + DELISTED)}
    closes, dvol, _, dates = load_year(s3, year, need, set())
    tail = list_dates(s3, 'stock', year - 1)[-WINDOW - 10:]
    tail_dates = []
    with ThreadPoolExecutor(8) as pool:
        for key, _, t in pool.map(lambda k: read_file(s3, k), tail):
            day = key_date(key)
            tail_dates.append(day)
            for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                if s in need and c and c > 0:
                    closes[s][day] = c
                    if v is not None and v >= 0:
                        dvol[s][day] = c * v
    all_dates = sorted(set(tail_dates) | set(dates))
    per_issuer = Counter(e['issuer_cik'] for e in events)
    shown = Counter()
    for e in events:
        series = {'plain': (closes.get(e['sym'], {}), dvol.get(e['sym'], {})),
                  'delisted': (closes.get(e['sym'] + DELISTED, {}), dvol.get(e['sym'] + DELISTED, {}))}
        r = evaluate_event(e, all_dates, series)
        if r['status'] != 'contradicted':
            continue
        kind = 'SYBT/GABC' if e['sym'] in ('SYBT', 'GABC') else 'low' if r['ratio'] < 0.25 else 'high' if r['ratio'] > 2 else None
        if kind is None or shown[kind] >= {'SYBT/GABC': 3, 'low': 6, 'high': 3}[kind]:
            continue
        shown[kind] += 1
        cl = closes[e['sym'] if r['via'] == 'plain' else e['sym'] + DELISTED]
        ds = sorted(cl)
        pts = []
        for d, p in e['purchases'][:3]:
            i = bisect_right(ds, d)
            pts.append((d, p, ds[i - 1] if i else None, cl[ds[i - 1]] if i else None))
        print(f"DIAG {year} {kind} {e['sym']} via={r['via']} cik={e['issuer_cik']} entry={e['entry']} buyers={e['buyers']} "
              f"ratio={r['ratio']:.3f} n_cmp={r['n_cmp']} purchases(date,price,close_date,close)={pts} "
              f"series_in_year first={ds[0]}:{cl[ds[0]]:.2f} last={ds[-1]}:{cl[ds[-1]]:.2f}")
    print(f'DIAG {year} events per issuer top: {per_issuer.most_common(5)}')


def probe(symbol, start, end):
    """Print symbol, date, close, volume for one symbol over a past date range (split-adjustment probe; no returns)."""
    from r2_storage import client
    s3 = client()
    keys = [k for y in range(int(start[:4]), int(end[:4]) + 1) for k in list_dates(s3, 'stock', y) if start <= key_date(k) <= end]
    for key in keys:
        _, _, t = read_file(s3, key)
        for s, c, v in zip(t['symbol'], t['close'], t['volume']):
            if s == symbol:
                print(f'PROBE {symbol} {key_date(key)} close={c} volume={v}')


# ---------------------------------------------------------------- summary
def summary(folder):
    years = sorted((json.loads(p.read_text()) for p in Path(folder).glob('year_*.json')), key=lambda r: r['year'])
    results = [r for y in years for r in y['results']]
    terminal = {}
    for y in years:
        for s, (d, c) in y['terminal'].items():
            if s not in terminal or d >= terminal[s][0]:
                terminal[s] = (d, c)
    print(f'=== A. Identity status of the chosen series (symbol match, then purchase-price test): {len(results)} events with a usable ticker ===')
    print('overall:', dict(Counter(r['status'] for r in results)))
    print('by series:', {v: dict(Counter(r['status'] for r in results if r['via'] == v)) for v in ('plain', 'delisted')})
    print('year: ok / contradicted / unverifiable / no_price')
    for y in years:
        c = Counter(r['status'] for r in y['results'])
        print(f"{y['year']}: {c['ok']} / {c['contradicted']} / {c['unverifiable']} / {c['no_price']}")
    matched = [r for r in results if r['status'] != 'no_price']
    d = sum(r['via'] == 'delisted' for r in matched)
    dok = sum(r['via'] == 'delisted' and r['status'] == 'ok' for r in matched)
    print(f'-DELISTED share of matched events: {d} of {len(matched)} = {d / max(1, len(matched)):.1%}; of identity-ok events: '
          f'{dok} of {sum(r["status"] == "ok" for r in matched)} = {dok / max(1, sum(r["status"] == "ok" for r in matched)):.1%}')
    print('\n=== B. Median purchase-price / archive-close ratio (identity-tested events) ===')
    edges = [0, 0.25, 0.5, 0.75, 0.9, 1.1, 1.33, 2, 4, 1e9]
    h = Counter()
    for r in results:
        if r['ratio'] is not None:
            for lo, hi in zip(edges, edges[1:]):
                if lo <= r['ratio'] < hi:
                    h[f'{lo}-{hi}'] += 1
    print(dict(h))
    print('\n=== C. Symbols with the most contradicted events (reused tickers, wrong company, or split-adjusted series) ===')
    bad = Counter((r['sym'], r['via']) for r in results if r['status'] == 'contradicted')
    print(bad.most_common(30))
    print('\n=== D. $3M floor re-run by identity status (15 full prior bars, mean close x volume >= $3M); counts only ===')
    for label, keep in (('identity ok only', {'ok'}), ('ok + unverifiable', {'ok', 'unverifiable'}),
                        ('all matched (Entry 19 style)', {'ok', 'unverifiable', 'contradicted'})):
        liq = [r for r in results if r['status'] in keep and r['liquid']]
        lq = Counter(f"{r['entry'][:4]}Q{(int(r['entry'][5:7]) - 1) // 3 + 1}" for r in liq if '2006' <= r['entry'][:4] <= '2025')
        tot = sum(lq.values())
        sealed = sum(v for q, v in lq.items() if q >= '2020Q2')
        sealed1 = sum(v for q, v in lq.items() if q >= '2020Q1')
        print(f'{label}: liquid {len(liq)} (2006-2025: {tot}; sealed from 2020Q2: {sealed} = {sealed / max(1, tot):.1%}; from 2020Q1: {sealed1} = {sealed1 / max(1, tot):.1%}; 2026: {sum(r["entry"][:4] == "2026" for r in liq)})')
    print('\n=== E. Where -DELISTED series end (development entries <= 2019-12-31 and 2026 pilot ONLY; counts, no returns) ===')
    pool_ = [r for r in results if r['via'] == 'delisted' and r['status'] != 'contradicted' and terminal_allowed(r['entry'])]
    cls = Counter()
    for r in pool_:
        t = terminal.get(r['sym'] + DELISTED)
        if not t:
            cls['no terminal info'] += 1
            continue
        gap = days_between(r['entry'], t[0])
        key = ('ends within ~21 sessions of entry' if gap <= HOLD_DAYS else 'ends later') + f" | last close {terminal_bucket(t[1])}"
        cls[key] += 1
    for k in sorted(cls):
        print(f'  {k}: {cls[k]}')
    print(f'  events in this table: {len(pool_)} (sealed 2020-2025 entries excluded by design)')
    print('  Reading guide: a last close under $1 is typical of failure/penny-stock exits; $5+ is typical of acquisitions. A heuristic, not a delisting reason.')


def selftest():
    d = [f'2020-03-{x:02d}' for x in range(2, 21)]
    closes = {x: 10.0 for x in d}
    assert identity_status(ratios_for([('2020-03-10', 10.4)], closes)) == ('ok', 10.4 / 10.0)
    assert identity_status(ratios_for([('2020-03-10', 25.0)], closes))[0] == 'contradicted'
    assert identity_status(ratios_for([('2020-03-10', None)], closes))[0] == 'unverifiable'
    assert identity_status(ratios_for([('2020-04-30', 10.0)], closes))[0] == 'unverifiable'   # close more than 7 days stale
    assert identity_status(ratios_for([('2020-02-01', 10.0)], closes))[0] == 'unverifiable'   # before the series starts
    assert identity_status(ratios_for([('2020-03-10', 10.0), ('2020-03-11', 30.0), ('2020-03-12', 10.0)], closes))[0] == 'ok'  # median
    e = {'entry': '2020-03-18', 'purchases': [['2020-03-10', 10.1]]}
    liq = {x: 5_000_000 for x in d}
    r = evaluate_event(e, d, {'plain': ({x: 400.0 for x in d}, liq), 'delisted': (closes, liq)})
    assert r['via'] == 'delisted' and r['status'] == 'ok', r        # reused ticker: plain series is a different company
    r = evaluate_event(e, d, {'plain': ({}, {}), 'delisted': ({}, {})})
    assert r['status'] == 'no_price'
    r = evaluate_event(e, d, {'plain': ({x: 400.0 for x in d}, liq), 'delisted': ({}, {})})
    assert r['status'] == 'contradicted' and r['via'] == 'plain'
    assert evaluate_event({'entry': '2020-03-12', 'purchases': []}, d, {'plain': (closes, liq), 'delisted': ({}, {})})['liquid'] is False  # only 8 bars before entry
    assert terminal_bucket(0.2) == '<0.50' and terminal_bucket(0.5) == '0.50-1' and terminal_bucket(30) == '>=20'
    assert terminal_allowed('2019-12-31') and not terminal_allowed('2020-01-02') and not terminal_allowed('2025-12-31') and terminal_allowed('2026-02-02')
    print('selftest ok')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['events', 'year', 'summary', 'diagnose', 'probe'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--events', default='reports/events_priced.json')
    ap.add_argument('--out')
    ap.add_argument('--start')
    ap.add_argument('--end')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'events':
        build_events(a.out or 'reports/events_priced.json')
    elif a.cmd == 'year':
        year_job(int(a.arg), a.events, a.out or f'reports/year_{a.arg}.json')
    elif a.cmd == 'probe':
        probe(a.arg, a.start, a.end)
    elif a.cmd == 'diagnose':
        diagnose_year(int(a.arg), a.events)
    elif a.cmd == 'summary':
        summary(a.arg or 'reports')
    else:
        ap.error('give a subcommand or --selftest')
