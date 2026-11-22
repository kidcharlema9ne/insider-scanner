"""Counts-only audit of the full MarketParquet archive in R2, plus the D-061 liquidity-floor check.

Reads ONLY symbol, date/timestamp, close and volume (close x volume = dollar volume) and
never computes a return. Nothing here looks at open/high/low or at price changes, so it is
safe to run on the sealed years (D-061, SHARED_LOG Entry 17).

Subcommands
  events   build the four-plus-buyer events (filings only, same logic as cluster_counts_by_year.py)
  year     audit one calendar year of both feeds and classify that year's events by liquidity
  summary  combine the per-year JSON files and print the tables and the D-061 verdict
  --selftest

Event classes (ticker matched by symbol only; there is NO ticker-to-security check, so a reused
ticker can match the wrong company -- counts are an upper bound):
  liquid      15 prior bars, mean(close*volume) >= $3M
  illiquid    15 prior bars, mean below $3M
  incomplete  symbol exists but fewer than 15 bars in the 15 sessions before entry
  no_price    symbol has no bar at all in that window
"""
import argparse, io, json, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PREFIX = {'stock': 'marketparquet/stock_daily/', 'etf': 'marketparquet/etf_daily/'}
ETF_CHECK = ('SPY', 'ONEQ', 'IWM')
# MarketParquet stores delisted names as <TICKER>-DELISTED (data-quality page). A reused ticker can therefore
# exist twice: the live company under TICKER and the earlier one under TICKER-DELISTED.
DELISTED = '-DELISTED'
STOCK_BASES = ('LEH', 'LEHMQ', 'WM', 'WMI', 'WAMUQ', 'BSC', 'CFC', 'WB', 'MER', 'IMB', 'CCTYQ', 'ENRNQ', 'WCOEQ',
               'SHLDQ', 'JCPNQ', 'GMGMQ', 'BBI', 'BGPIQ', 'EKDKQ', 'WYE', 'SGP', 'ROH', 'XTO', 'TWX', 'MON')
STOCK_CHECK = tuple(x for b in STOCK_BASES for x in (b, b + DELISTED))
CLOSE_YEARS = {2007, 2008, 2009}  # keep closes of STOCK_CHECK symbols in these years only (identity check)
FLOOR = 3_000_000
WINDOW = 15
READ_COLS = ('symbol', 'close', 'volume', 'date', 'timestamp', 'asset_type')
LAST_ARCHIVE_DATE = '2026-11-06'


def normalize_ticker(raw):
    """Return (symbol, category). category: ok | blank | otc | odd. Only case/whitespace/first-of-list cleaning."""
    t = (raw or '').strip()
    if not t or t.upper() in ('NONE', 'N/A', 'NA', 'NULL'):
        return '', 'blank'
    t = t.split(',')[0].strip().upper()
    if t.endswith(('.OB', '.PK', '.OTC', '.OTCBB')):
        return t, 'otc'
    return t, 'ok'


def quarter(iso):
    return f'{iso[:4]}Q{(int(iso[5:7]) - 1) // 3 + 1}'


def nyse_sessions(year):
    import pandas_market_calendars as mcal
    days = mcal.get_calendar('NYSE').valid_days(f'{year}-01-01', f'{year}-12-31')
    out = [d.strftime('%Y-%m-%d') for d in days]
    return [d for d in out if d <= LAST_ARCHIVE_DATE]


def list_dates(s3, asset, year):
    from r2_storage import BUCKET
    keys = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=BUCKET, Prefix=f'{PREFIX[asset]}{year}'):
        for obj in page.get('Contents', []):
            keys.append(obj['Key'])
    return sorted(keys)


def key_date(key):
    return key.rsplit('/', 1)[1][:-len('.parquet')]


def classify(dates, entry, dv):
    """dates: sorted price-file dates; dv: {date: dollar_volume} for one symbol. Returns (class, mean or None, n_bars)."""
    i = bisect_left(dates, entry)
    window = dates[max(0, i - WINDOW):i]
    vals = [dv[d] for d in window if d in dv]
    if not vals:
        return 'no_price', None, 0
    mean = sum(vals) / len(vals)
    if len(window) < WINDOW or len(vals) < WINDOW:
        return 'incomplete', mean, len(vals)
    return ('liquid' if mean >= FLOOR else 'illiquid'), mean, len(vals)


def read_file(s3, key):
    import pyarrow.parquet as pq
    from r2_storage import BUCKET
    body = s3.get_object(Bucket=BUCKET, Key=key)['Body'].read()
    pf = pq.ParquetFile(io.BytesIO(body))
    names = pf.schema_arrow.names
    use = [c for c in READ_COLS if c in names]
    return key, names, pf.read(columns=use).to_pydict()


def audit_feed(s3, asset, year, need, collect_dv):
    keys = list_dates(s3, asset, year)
    dates = [key_date(k) for k in keys]
    expected = nyse_sessions(year)
    rep = {'files': len(keys), 'expected_sessions': len(expected),
           'missing_sessions': [d for d in expected if d not in set(dates)][:40],
           'extra_dates': [d for d in dates if d not in set(expected)][:40]}
    rows_per_file, columns, symbols = [], Counter(), set()
    bad_rows = dup_files = date_mismatch = timestamp_files = 0
    asset_types = Counter()
    check = ETF_CHECK if asset == 'etf' else STOCK_CHECK
    present = defaultdict(list)
    closes = defaultdict(dict)
    dv = defaultdict(dict) if collect_dv else None
    with ThreadPoolExecutor(8) as pool:
        for start in range(0, len(keys), 32):
            for key, names, t in pool.map(lambda k: read_file(s3, k), keys[start:start + 32]):
                day = key_date(key)
                columns[','.join(sorted(names))] += 1
                dcol = 'date' if 'date' in t else 'timestamp'
                timestamp_files += dcol == 'timestamp'
                if {str(v)[:10] for v in t[dcol]} != {day}:
                    date_mismatch += 1
                syms, close, vol = t['symbol'], t['close'], t['volume']
                rows_per_file.append(len(syms))
                if len(set(syms)) != len(syms):
                    dup_files += 1
                symbols.update(syms)
                if 'asset_type' in t:
                    asset_types.update(t['asset_type'])
                for s, c, v in zip(syms, close, vol):
                    if c is None or v is None or c <= 0 or v < 0:
                        bad_rows += 1
                        continue
                    if s in check:
                        present[s].append(day)
                        if asset == 'stock' and year in CLOSE_YEARS:
                            closes[s][day] = c
                    if dv is not None and s in need:
                        dv[s][day] = c * v
    rep.update({'rows_min': min(rows_per_file, default=0), 'rows_median': int(statistics.median(rows_per_file or [0])),
                'rows_max': max(rows_per_file, default=0), 'distinct_symbols': len(symbols), 'symbols': sorted(symbols) if asset == 'stock' else [], 'delisted_suffix_symbols': sum(x.endswith(DELISTED) for x in symbols),
                'column_sets': dict(columns), 'timestamp_column_files': timestamp_files,
                'date_mismatch_files': date_mismatch, 'files_with_duplicate_symbols': dup_files,
                'bad_rows': bad_rows, 'asset_types': dict(asset_types),
                'present_dates': {s: present.get(s, []) for s in check}, 'closes': dict(closes)})
    return rep, dates, dv


def year_job(year, events_path, out):
    from r2_storage import client
    s3 = client()
    events = [e for e in json.loads(Path(events_path).read_text()) if e['entry'].startswith(str(year))]
    for e in events:
        e['sym'], e['tcat'] = normalize_ticker(e['ticker'])
    need = {x for e in events if e['tcat'] == 'ok' for x in (e['sym'], e['sym'] + DELISTED)}
    stock, dates, dv = audit_feed(s3, 'stock', year, need, True)
    etf, _, _ = audit_feed(s3, 'etf', year, set(), False)
    # trailing files from the prior year so January entries have a 15-session window
    tail = list_dates(s3, 'stock', year - 1)[-WINDOW - 5:]
    tail_dates = [key_date(k) for k in tail]
    with ThreadPoolExecutor(8) as pool:
        for key, _, t in pool.map(lambda k: read_file(s3, k), tail):
            day = key_date(key)
            for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                if s in need and c and v is not None and c > 0 and v >= 0:
                    dv[s][day] = c * v
    all_dates = sorted(set(tail_dates) | set(dates))
    cls, liquid_q, events_q, unmatched = Counter(), Counter(), Counter(), Counter()
    liquid_ge10 = 0
    no_price_syms = []
    matched_via = Counter()
    for e in events:
        if e['tcat'] != 'ok':
            c, mean, bars = 'unusable_ticker_' + e['tcat'], None, 0
        else:
            a = classify(all_dates, e['entry'], dv.get(e['sym'], {}))
            b = classify(all_dates, e['entry'], dv.get(e['sym'] + DELISTED, {}))
            if a[0] != 'no_price' and b[0] != 'no_price':
                matched_via['both_series_in_window'] += 1
                (c, mean, bars), via = (a, 'plain') if a[2] >= b[2] else (b, 'delisted_suffix')
            elif b[0] != 'no_price':
                (c, mean, bars), via = b, 'delisted_suffix'
            else:
                (c, mean, bars), via = a, 'plain'
            if c != 'no_price':
                matched_via[via] += 1
        cls[c] += 1
        events_q[quarter(e['entry'])] += 1
        liquid_q[quarter(e['entry'])] += c == 'liquid'
        liquid_ge10 += (c in ('liquid', 'incomplete') and bars >= 10 and mean >= FLOOR)
        if c == 'no_price':
            unmatched[e['sym']] += 1
            no_price_syms.append(e['sym'])
    report = {'year': year, 'stock': stock, 'etf': etf,
              'events': {'total': len(events), 'classes': dict(cls), 'liquid_ge10_bars_sensitivity': liquid_ge10,
                         'by_quarter': dict(events_q), 'liquid_by_quarter': dict(liquid_q),
                         'matched_via': dict(matched_via),
                         'sample_no_price_tickers': [t for t, _ in unmatched.most_common(15)],
                         'no_price_symbols': no_price_syms}}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report))
    s = report['stock']
    print(f"{year}: stock files {s['files']}/{s['expected_sessions']} symbols {s['distinct_symbols']} "
          f"events {len(events)} {dict(cls)}")


def build_events(out):
    import os, tempfile
    from cluster_counts_by_year import fetch_db, find_events, load_rows, sessions
    with tempfile.TemporaryDirectory() as tmp:
        events = find_events(load_rows(fetch_db(tmp)), sessions())
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(events))
    print(f'events: {len(events)} (filings only, no price data read)')


def share_table(liquid_q):
    """Sealed share of 2006-2025 liquid events for candidate quarter cuts. Returns list of (cut, sealed, total, share)."""
    quarters = sorted(q for q in liquid_q if '2006' <= q[:4] <= '2025')
    total = sum(liquid_q[q] for q in quarters)
    rows = []
    for y in range(2012, 2024):
        for n in (1, 2, 3, 4):
            cut = f'{y}Q{n}'
            sealed = sum(liquid_q[q] for q in quarters if q >= cut)
            rows.append((cut, sealed, total, sealed / total if total else 0.0))
    return rows


def verdict(rows, preferred='2020Q1'):
    by = {r[0]: r for r in rows}
    cur = by[preferred]
    if 0.20 <= cur[3] <= 0.30:
        return preferred, 'keep'
    ok = [r for r in rows if 0.20 <= r[3] <= 0.30]
    if not ok:
        return None, 'no quarter boundary reaches 20-30%'
    pos = lambda c: int(c[:4]) * 4 + int(c[-1])
    best = min(ok, key=lambda r: abs(pos(r[0]) - pos(preferred)))
    return best[0], 'move'


def summary(folder):
    years = sorted((json.loads(p.read_text()) for p in Path(folder).glob('year_*.json')), key=lambda r: r['year'])
    print('=== A. Feed coverage (files vs NYSE sessions) ===')
    for feed in ('stock', 'etf'):
        print(f'-- {feed}_daily: year files/expected missing extra rows(min/med/max) symbols ts-files date-mismatch dup-files bad-rows')
        for r in years:
            f = r[feed]
            print(f"{r['year']} {f['files']}/{f['expected_sessions']} miss={len(f['missing_sessions'])} extra={len(f['extra_dates'])} "
                  f"rows={f['rows_min']}/{f['rows_median']}/{f['rows_max']} sym={f['distinct_symbols']} ts={f['timestamp_column_files']} "
                  f"mis={f['date_mismatch_files']} dup={f['files_with_duplicate_symbols']} bad={f['bad_rows']}")
        for r in years:
            f = r[feed]
            if f['missing_sessions'] or f['extra_dates']:
                print(f"   {r['year']} missing={f['missing_sessions']} extra={f['extra_dates']}")
    print('column sets seen:', sorted({k for r in years for k in r['stock']['column_sets']} | {k for r in years for k in r['etf']['column_sets']}))
    print('asset_type values (stock feed):', {r['year']: r['stock']['asset_types'] for r in years if r['stock']['asset_types']})
    print('\n=== B. Benchmark ETFs: dates present per year / ETF files that year ===')
    for sym in ETF_CHECK:
        print(sym, {r['year']: f"{len(r['etf']['present_dates'][sym])}/{r['etf']['files']}" for r in years})
    print('\n=== C. Lehman / Washington Mutual identity check (stock feed) ===')
    allp = defaultdict(list)
    closes = defaultdict(dict)
    for r in years:
        for s, d in r['stock']['present_dates'].items():
            allp[s] += d
        for s, c in r['stock']['closes'].items():
            closes[s].update(c)
    missing = []
    for s in STOCK_CHECK:
        d = sorted(allp[s])
        if not d:
            missing.append(s)
            continue
        gaps = [(d[i], d[i + 1]) for i in range(len(d) - 1) if _span(d[i], d[i + 1]) > 10]
        c = closes[s]
        pts = [(k, round(c[k], 2)) for k in ('2008-09-12', '2008-09-25', '2008-10-01') if k in c]
        print(f'{s}: first {d[0]} last {d[-1]} bars {len(d)} gaps>10d {gaps[:3]} closes {pts}')
    print('NOT FOUND in any year:', missing)
    print('Probe names were all US-listed and later acquired, merged or bankrupt (some symbols were reused by later companies).')
    print('(WM: Washington Mutual was about $1-3 in Sept 2008; a price near $30 means the series is Waste Management.)')
    print('\n=== D. Events by liquidity class (entry year); filings-only events matched to prices by symbol ===')
    liquid_q, events_q = Counter(), Counter()
    tot = Counter()
    for r in years:
        e = r['events']
        if not e['total']:
            continue
        print(f"{r['year']}: total {e['total']} {e['classes']} liquid>=10bars {e['liquid_ge10_bars_sensitivity']}")
        tot.update(e['classes'])
        liquid_q.update(e['liquid_by_quarter'])
        events_q.update(e['by_quarter'])
    print('all years:', dict(tot))
    mv = Counter()
    for r in years:
        mv.update(r['events'].get('matched_via', {}))
    print('matched via:', dict(mv))
    print('-DELISTED symbols in the stock feed by year:', {r['year']: r['stock']['delisted_suffix_symbols'] for r in years})
    print('liquid share of price-matched events (liquid / (liquid+illiquid)) by year:',
          {r['year']: round(r['events']['classes'].get('liquid', 0) / max(1, r['events']['classes'].get('liquid', 0) + r['events']['classes'].get('illiquid', 0)), 2) for r in years if r['events']['total']})
    every = set()
    for r in years:
        every.update(r['stock']['symbols'])
    print('\n-- no_price events: is the (cleaned) symbol anywhere in the stock archive in any year? --')
    for r in years:
        syms = r['events']['no_price_symbols']
        if not syms:
            continue
        never = sum(1 for x in syms if x not in every and x + DELISTED not in every)
        print(f"{r['year']}: no_price {len(syms)} -> symbol never appears in any year {never}, appears in some year but not in the 15-session window {len(syms) - never}")
    print('sample unmatched tickers:', {r['year']: r['events']['sample_no_price_tickers'][:8] for r in years if r['events']['sample_no_price_tickers']})
    print('\n=== E. D-061 condition: sealed share of 2006-2025 liquid events (counts only, no returns) ===')
    rows = share_table(liquid_q)
    for cut, s, t, sh in rows:
        if cut[:4] in ('2018', '2019', '2020', '2021'):
            print(f'cut {cut}: sealed {s} of {t} = {sh:.1%}')
    pref = {r[0]: r for r in rows}['2020Q1']
    raw_total = sum(v for q, v in events_q.items() if '2006' <= q[:4] <= '2025')
    raw_sealed = sum(v for q, v in events_q.items() if '2020' <= q[:4] <= '2025')
    print(f'raw (no floor) sealed share: {raw_sealed} of {raw_total} = {raw_sealed / raw_total:.1%}' if raw_total else 'no events')
    cut, action = verdict(rows)
    print(f'preferred cut 2020Q1 liquid share {pref[3]:.1%} -> {action}: {cut}')
    pilot = sum(v for q, v in liquid_q.items() if q[:4] == '2026')
    print(f'2026 pilot-year liquid events (all, incl. incomplete outcomes): {pilot}')


def _span(a, b):
    import datetime as dt
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def selftest():
    dates = [f'2020-02-{d:02d}' for d in range(3, 29) if d not in (8, 9, 15, 16, 22, 23)]  # 20 weekdays
    dv_hi = {d: 5_000_000 for d in dates}
    assert classify(dates, dates[17], dv_hi)[0] == 'liquid'
    assert classify(dates, dates[17], {d: 1_000_000 for d in dates})[0] == 'illiquid'
    assert classify(dates, dates[17], {})[0] == 'no_price'
    assert classify(dates, dates[10], dv_hi)[0] == 'incomplete'       # only 10 bars before entry
    partial = dict(list(dv_hi.items())[5:])
    assert classify(dates, dates[17], partial)[0] == 'incomplete'
    assert classify(dates, dates[17], {d: (3_000_000 if i % 2 else 3_000_000) for i, d in enumerate(dates)})[0] == 'liquid'  # exactly $3M counts
    lq = Counter({f'{y}Q{n}': 10 for y in range(2006, 2026) for n in range(1, 5)})
    rows = share_table(lq)
    assert abs({r[0]: r for r in rows}['2020Q1'][3] - 24 / 80) < 1e-9  # 24 of 80 quarters = 30.0%, inside 20-30%
    assert verdict(rows) == ('2020Q1', 'keep')
    thin = Counter({f'{y}Q{n}': (5 if y >= 2020 else 10) for y in range(2006, 2026) for n in range(1, 5)})
    cut, action = verdict(share_table(thin))  # sealed share 17.6% -> must move earlier, to a boundary that reaches 20%
    assert action == 'move' and cut < '2020Q1', (cut, action)
    assert verdict(share_table(Counter({'2010Q1': 1}))) [1] != 'keep'
    assert 'LEH-DELISTED' in STOCK_CHECK and 'WM' in STOCK_CHECK
    print('selftest ok')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['events', 'year', 'summary'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--events', default='reports/events.json')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'events':
        build_events(a.out or 'reports/events.json')
    elif a.cmd == 'year':
        year_job(int(a.arg), a.events, a.out or f'reports/year_{a.arg}.json')
    elif a.cmd == 'summary':
        summary(a.arg or 'reports')
    else:
        ap.error('give a subcommand or --selftest')
