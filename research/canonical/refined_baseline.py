"""Baseline re-run on the refined primary set (D-064 routine exclusion, D-065 option C, split-grid identity, $3M floor).

NEW CODE, not a re-run of the Entry 8 pilot code: marked PROVISIONAL in the log. It copies the pilot's return
definition (research/recovered_20261107/liquidity_tiers.py `returns`, price_outcomes.py `atr14`):
  entry   = open of the entry session (the next regular open after the qualifying filing); entry session is day one
  exit    = close of session 21 (entry index + 20), price only, no costs
  ATR     = mean true range of the 14 completed sessions before entry (needs 15 earlier bars)
  stock   = (exit close - entry open) / ATR
  SPY     = (SPY exit close / SPY entry open - 1) * (entry open / ATR)   i.e. SPY on the same window in the stock's ATR units
  excess  = stock - SPY

SAFEGUARD (D-068): returns are computed ONLY for entries on or before 2020-12-31 and for the 2026 pilot (entries on
or after 2026-01-01). `assert_allowed` raises for any other entry, and the summary re-checks every row. Entries
from 2021-01-01 through 2025-12-31 (gap 2021Q1 and the sealed years) are never read.

Subcommands
  primary FOLDER --out FILE      rebuild the primary set from the year_*.json files of a refined-study run
                                 (refined + identity fine + liquid + option C), assert the Entry 25 counts, keep allowed entries
  year YEAR --primary FILE --out FILE   returns for one entry year (stock and SPY bars from the archive)
  summary FOLDER                 merge and print
  --selftest
"""
import argparse, json, os, random, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DEV_END = '2020-12-31'
PILOT_START = '2026-01-01'
HOLD = 21                      # entry session is day one -> exit index = entry index + HOLD - 1
ATR_BARS = 14
EXPECTED = {'2006-2025': 1844, '2026': 80}   # SHARED_LOG Entry 25, refined + option C + identity fine + $3M floor
EPISODES = ('2008Q4', '2011Q3', '2020Q1')
BASELINE_PILOT = {'trades': 91, 'excess': 0.5257, 'run': 42421461026}   # Entry 8, different code and cohort


SEALED_START, SEALED_END = '2021-04-01', '2025-12-31'   # D-068


def allowed(entry):
    # The sealed window opens ONLY for sealed_run.py, which sets SEALED_RUN=1 after research_docs/SEALED_HYPOTHESES.md is marked FROZEN (it checks that itself).
    if os.environ.get('SEALED_RUN') == '1' and SEALED_START <= entry <= SEALED_END:
        return True
    return entry <= DEV_END or entry >= PILOT_START


def assert_allowed(entry):
    if not allowed(entry):
        raise RuntimeError(f'D-068 safeguard: no returns for entry {entry}')


def quarter(iso):
    return f'{iso[:4]}Q{(int(iso[5:7]) - 1) // 3 + 1}'


# ------------------------------------------------------------------ returns
def true_range(bar, prev_close):
    o, h, l, c = bar
    return max(h - l, abs(h - prev_close), abs(l - prev_close))


def trade_outcome(dates, stock, spy, entry, hold=HOLD):
    """dates: sorted session dates. stock, spy: {date: (open, high, low, close)}. Returns a dict with a status."""
    assert_allowed(entry)
    i = bisect_left(dates, entry)
    if i >= len(dates) or dates[i] != entry:
        return {'status': 'entry_not_session'}
    if i < ATR_BARS + 1:
        return {'status': 'atr_missing'}
    window = dates[i - ATR_BARS - 1:i]
    if any(d not in stock for d in window):
        return {'status': 'atr_missing'}
    atr = sum(true_range(stock[window[k]], stock[window[k - 1]][3]) for k in range(1, len(window))) / ATR_BARS
    if atr <= 0 or entry not in stock:
        return {'status': 'atr_missing'}
    entry_open = stock[entry][0]
    j = i + hold - 1
    if j >= len(dates):
        return {'status': 'open', 'atr': atr, 'entry_open': entry_open}
    scale = entry_open / atr
    if entry not in spy or dates[j] not in spy:
        return {'status': 'spy_missing'}
    spy_atr = (spy[dates[j]][3] / spy[entry][0] - 1) * scale
    if dates[j] in stock:
        s = (stock[dates[j]][3] - entry_open) / atr
        return {'status': 'complete', 'atr': atr, 'entry_open': entry_open, 'exit': dates[j],
                'stock_atr': s, 'spy_atr': spy_atr, 'excess_atr': s - spy_atr,
                'stock_pct': stock[dates[j]][3] / entry_open - 1, 'spy_pct': spy[dates[j]][3] / spy[entry][0] - 1}
    held = [d for d in dates[i:j + 1] if d in stock]
    last = held[-1]
    s = (stock[last][3] - entry_open) / atr
    return {'status': 'incomplete', 'atr': atr, 'entry_open': entry_open, 'exit': last,
            'stock_atr': s, 'spy_atr': spy_atr, 'excess_atr': s - spy_atr,
            'stock_pct': stock[last][3] / entry_open - 1, 'spy_pct': spy[dates[j]][3] / spy[entry][0] - 1}


# ------------------------------------------------------------------ primary set
def build_primary(folder):
    from refined_study import FINE, collapse
    from cluster_counts_by_year import sessions
    cal = sessions()
    idx_of = lambda d: bisect_left(cal, d)
    years = [json.loads(p.read_text()) for p in sorted(Path(folder).glob('year_*.json'))]
    refined = [r for y in years for r in y['results'] if r['set'] == 'refined']
    tradable = [r for r in refined if r['status'] in FINE and r['liquid']]
    primary = collapse(tradable, idx_of)
    n_hist = sum('2006' <= e['entry'][:4] <= '2025' for e in primary)
    n_pilot = sum(e['entry'][:4] == '2026' for e in primary)
    print(f'primary set rebuilt: 2006-2025 {n_hist} (expected {EXPECTED["2006-2025"]}), 2026 pilot {n_pilot} (expected {EXPECTED["2026"]})')
    if os.environ.get('CLUSTER_WINDOW', '15') == '15' and not os.environ.get('DATE_RULE'):
        assert n_hist == EXPECTED['2006-2025'] and n_pilot == EXPECTED['2026'], 'primary set does not match Entry 25'
    else:
        print('exploratory variant (C38 window or C41 date rule): the Entry 25 count check is skipped; only development entries are used downstream')
    keep = [e for e in primary if allowed(e['entry'])]
    print(f'allowed under D-068 (entry <= {DEV_END} or >= {PILOT_START}): {len(keep)} '
          f'({sum(e["entry"] <= DEV_END for e in keep)} development, {sum(e["entry"] >= PILOT_START for e in keep)} pilot); '
          f'withheld {len(primary) - len(keep)}')
    return keep


# ------------------------------------------------------------------ archive
OHLC = ('open', 'high', 'low', 'close')


def read_ohlc(s3, key, want):
    import io
    import pyarrow.parquet as pq
    from r2_storage import BUCKET
    body = s3.get_object(Bucket=BUCKET, Key=key)['Body'].read()
    pf = pq.ParquetFile(io.BytesIO(body))
    names = pf.schema_arrow.names
    miss = [c for c in ('symbol',) + OHLC if c not in names]
    if miss:
        raise RuntimeError(f'{key}: columns {names} lack {miss}')
    t = pf.read(columns=['symbol', *OHLC]).to_pydict()
    out = {}
    for s, o, h, l, c in zip(t['symbol'], *(t[k] for k in OHLC)):
        if s in want and None not in (o, h, l, c) and c > 0 and o > 0:
            out[s] = (float(o), float(h), float(l), float(c))
    return out


def load_span(s3, asset, years, want, head, tail_n):
    """Bars for `want` symbols over `years`, plus the last `head` files before and first `tail_n` files after."""
    from concurrent.futures import ThreadPoolExecutor
    from archive_coverage_audit import key_date, list_dates
    keys = list_dates(s3, asset, years[0] - 1)[-head:] + [k for y in years for k in list_dates(s3, asset, y)] + \
        list_dates(s3, asset, years[-1] + 1)[:tail_n]
    bars = defaultdict(dict)
    dates = []
    with ThreadPoolExecutor(8) as pool:
        for start in range(0, len(keys), 32):
            chunk = keys[start:start + 32]
            for k, got in zip(chunk, pool.map(lambda k: read_ohlc(s3, k, want), chunk)):
                day = key_date(k)
                dates.append(day)
                for s, b in got.items():
                    bars[s][day] = b
    return bars, sorted(set(dates))


def year_job(year, primary_path, out, hold=HOLD):
    from r2_storage import client
    from archive_coverage_audit import DELISTED, normalize_ticker
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        # Longer holds (HOLD != 21, Entry 43) need the following year's bars; the default 21-session path is unchanged.
        span = [year] if hold == HOLD else [year, year + 1]
        stock_bars, dates = load_span(s3, 'stock', span, want, 25, 30)
        spy_bars, _ = load_span(s3, 'etf', span, {'SPY'}, 25, 30)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = trade_outcome(dates, series, spy, e['entry'], hold)
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'via': e.get('via')})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year} (hold {hold} sessions): ' + str(dict(Counter(r['status'] for r in rows))))


# ------------------------------------------------------------------ summary
def stats(rows):
    n = len(rows)
    if not n:
        return 'n=0'
    ex = [r['excess_atr'] for r in rows]
    return (f'n={n}  stock {statistics.fmean(r["stock_atr"] for r in rows):+.3f}  SPY {statistics.fmean(r["spy_atr"] for r in rows):+.3f}'
            f'  excess {statistics.fmean(ex):+.3f}  median {statistics.median(ex):+.3f}  beat SPY {sum(x > 0 for x in ex)}/{n}')


def independence(rows):
    wk = lambda r: date.fromisoformat(r['entry']).isocalendar()[:2]
    return (f'{len({r["cik"] for r in rows})} issuers, {len({r["entry"] for r in rows})} entry dates, '
            f'{len({wk(r) for r in rows})} entry weeks')


def week_bootstrap(rows, draws=10000, seed=20261108):
    weeks = defaultdict(list)
    for r in rows:
        weeks[date.fromisoformat(r['entry']).isocalendar()[:2]].append(r['excess_atr'])
    tot = [(sum(v), len(v)) for v in weeks.values()]
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        pick = rng.choices(tot, k=len(tot))
        means.append(sum(a for a, _ in pick) / sum(b for _, b in pick))
    means.sort()
    return means[int(0.025 * draws)], means[int(0.975 * draws)], sum(m <= 0 for m in means) / draws


def summary(folder):
    rows = [r for p in sorted(Path(folder).glob('returns_*.json')) for r in json.loads(p.read_text())['rows']]
    for r in rows:
        assert_allowed(r['entry'])
    print(f'=== A. Outcome status (primary set, allowed entries): {len(rows)} entries ===')
    for label, sel in (('development (<= 2020-12-31)', lambda r: r['entry'] <= DEV_END), ('2026 pilot', lambda r: r['entry'] >= PILOT_START)):
        print(f'{label}: {dict(Counter(r["status"] for r in rows if sel(r)))}')
    done = [r for r in rows if r['status'] == 'complete']
    dev = [r for r in done if r['entry'] <= DEV_END]
    pil = [r for r in done if r['entry'] >= PILOT_START]
    print('\n=== B. Completed 21-session trades, price only, excess over same-window SPY in the stock ATR (ATR units) ===')
    for label, sel in (('all', done), ('development 2006-2020', dev), ('2026 pilot (in-sample)', pil)):
        print(f'{label}: {stats(sel)}')
        if sel:
            print(f'    independence: {independence(sel)}')
    print(f'Reference, NOT comparable (Entry 8, run {BASELINE_PILOT["run"]}, other code, other cohort): '
          f'{BASELINE_PILOT["trades"]} liquid pilot trades, excess {BASELINE_PILOT["excess"]:+.4f}')
    print('\n=== C. By entry year (completed) ===')
    byy = defaultdict(list)
    for r in done:
        byy[r['entry'][:4]].append(r)
    for y in sorted(byy):
        print(f'{y}: {stats(byy[y])}')
    print('\n=== D. Episodes (completed; development only) ===')
    for q in EPISODES:
        sub = [r for r in dev if quarter(r['entry']) == q]
        print(f'{q}: {stats(sub)}')
    for q in EPISODES:
        print(f'development without {q}: {stats([r for r in dev if quarter(r["entry"]) != q])}')
    print(f'development without all three: {stats([r for r in dev if quarter(r["entry"]) not in EPISODES])}')
    print('\n=== E. Concentration (completed, all) ===')
    ranked = sorted(done, key=lambda r: -r['excess_atr'])
    tot = sum(r['excess_atr'] for r in done)
    for k in (1, 3, 5, 10):
        rest = ranked[k:]
        print(f'mean excess without top {k}: {statistics.fmean(r["excess_atr"] for r in rest):+.3f}')
    print('top 10: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["excess_atr"]:+.2f}' for r in ranked[:10]) + f'  (sum of top 10 = {sum(r["excess_atr"] for r in ranked[:10]) / tot:.0%} of total {tot:.1f})')
    print('bottom 5: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["excess_atr"]:+.2f}' for r in ranked[-5:]))
    print('\n=== F. Week-block bootstrap of the mean excess (10,000 draws, seed 20261108) ===')
    for label, sel in (('all', done), ('development', dev), ('pilot', pil)):
        if len(sel) > 1:
            lo, hi, p = week_bootstrap(sel)
            print(f'{label}: mean {statistics.fmean(r["excess_atr"] for r in sel):+.3f}, 95% range {lo:+.3f} to {hi:+.3f}, share of draws <= 0 {p:.1%}')
    print('\n=== G. Sensitivity: delisted-in-window trades (series ended before day 21; last close used; NOT in B) ===')
    inc = [r for r in rows if r['status'] == 'incomplete']
    print(f'incomplete: {stats(inc)}')
    print(f'completed + incomplete: {stats(done + inc)}')
    print('\n=== H. Costs (price-only above; costs run about 0.10 to 0.30 ATR per Entry 12 notes) ===')
    if done:
        m = statistics.fmean(r['excess_atr'] for r in done)
        print(f'mean excess {m:+.3f}; after 0.10 {m - 0.10:+.3f}; after 0.30 {m - 0.30:+.3f}')


# ------------------------------------------------------------------ self-test
def selftest():
    dates = [f'2020-02-{d:02d}' for d in range(1, 29)] + [f'2020-03-{d:02d}' for d in range(1, 32)]
    flat = {d: (100.0, 102.0, 98.0, 100.0) for d in dates}          # true range 4 every session
    spy = {d: (400.0, 401.0, 399.0, 400.0) for d in dates}
    entry = dates[20]
    j = 20 + HOLD - 1
    flat[dates[j]] = (100.0, 110.0, 98.0, 108.0)
    spy[dates[j]] = (400.0, 405.0, 399.0, 404.0)
    r = trade_outcome(dates, flat, spy, entry)
    assert r['status'] == 'complete' and abs(r['atr'] - 4.0) < 1e-9, r
    assert abs(r['stock_atr'] - 2.0) < 1e-9 and abs(r['spy_atr'] - 0.25) < 1e-9 and abs(r['excess_atr'] - 1.75) < 1e-9, r
    assert r['exit'] == dates[j]
    short = {d: b for d, b in flat.items() if d < dates[j - 2]}                      # delisted before day 21
    r2 = trade_outcome(dates, short, spy, entry)
    assert r2['status'] == 'incomplete' and r2['exit'] == dates[j - 3], r2
    gap = {d: b for d, b in flat.items() if d != dates[10]}                          # a missing ATR bar
    assert trade_outcome(dates, gap, spy, entry)['status'] == 'atr_missing'
    assert trade_outcome(dates, flat, spy, dates[5])['status'] == 'atr_missing'
    assert trade_outcome(dates, flat, spy, dates[-3])['status'] == 'open'
    assert trade_outcome(dates, flat, spy, '2020-04-15')['status'] == 'entry_not_session'
    for bad in ('2021-01-04', '2021-03-31', '2023-06-01', '2025-12-31'):
        try:
            trade_outcome(dates, flat, spy, bad)
        except RuntimeError:
            continue
        raise AssertionError(f'guard let {bad} through')
    r3 = trade_outcome(dates, flat, spy, entry, hold=5)
    assert r3['status'] == 'complete' and r3['exit'] == dates[24] and abs(r3['stock_pct']) < 1e-12, r3
    assert abs(r['stock_pct'] - 0.08) < 1e-12 and abs(r['spy_pct'] - 0.01) < 1e-12, r
    assert allowed('2020-12-31') and allowed('2026-01-02') and allowed('2008-10-10') and not allowed('2021-01-01')
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float(k % 5) - 1.0} for k in range(60)]
    assert week_bootstrap(rows, 200) == week_bootstrap(rows, 200)
    assert quarter('2020-03-31') == '2020Q1' and quarter('2008-10-01') == '2008Q4'
    print('refined_baseline self-test passed')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['primary', 'year', 'summary'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    ap.add_argument('--hold', type=int, default=HOLD)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if a.selftest:
        selftest()
    elif a.cmd == 'primary':
        keep = build_primary(a.arg)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(keep))
    elif a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out, a.hold)
    elif a.cmd == 'summary':
        summary(a.arg)
    else:
        ap.error('give a subcommand or --selftest')
