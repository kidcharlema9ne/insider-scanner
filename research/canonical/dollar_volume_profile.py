"""Dollar-volume profile of the deep-fall groups (POST HOC, asked by Michael 8 Nov 2026; follow-up to Entry 52).

Question: in the 12+ ATR (6 and 9 month) trades, what was the average dollar volume (shares traded x price)?

Measure (the D-061 floor's own definition, `archive_coverage_audit` / `identity_check.window_stats`): for each primary entry, the mean of
close x volume over the 15 completed sessions before the entry session, from the full MarketParquet archive (closes and volumes both
split-adjusted, so their product is unaffected, Entry 23). Also the median of those 15 daily values (less sensitive to one huge day), and
the entry day's own open is NOT used. Only sessions strictly before the entry are read. Series choice as in `refined_baseline.year_job`
(plain ticker, else the -DELISTED series). Events with fewer than 15 priced bars in the window are reported as incomplete and excluded from
the averages (they cannot be in the primary set anyway: the $3M floor needs 15 bars).

Cohort: the Entry 28 / Entry 52 development cohort (entries <= 2020-12-31, D-068; no sealed return read; pilot not used), joined to the
Entry 36 + Entry 49 features and the Entry 28 returns exactly as `decline_buckets.load` does. Groups: all events; D >= 10, 12, 15, 20 ATR for
the 6-month (126) and 9-month (189) falls, and the 12-15, 15-20 bands. Per group: n, mean and median of the per-event 15-session mean dollar
volume (USD), quartiles, share under $5M and under $10M, and also the mean of the per-event MEDIAN daily dollar volume. Dollars only; no
share counts and no position-size or market-impact modelling.

Descriptive only; no chance test. The $3M floor already removes thinner names, so every number is conditional on passing it.

Usage:  python dollar_volume_profile.py year YEAR --primary FILE --out FILE   |   scan DECLINE_FOLDER F189_FOLDER RETURNS_FOLDER DV_FOLDER   |   --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import assert_allowed

WINDOW = 15
GROUPS = [('all events', None, None), ('>=10 ATR', 10, None), ('>=12 ATR', 12, None), ('>=15 ATR', 15, None), ('>=20 ATR', 20, None),
          ('12-15 ATR', 12, 15), ('15-20 ATR', 15, 20)]


def window_values(all_dates, entry, dvol):
    """Daily dollar volumes of the 15 sessions strictly before entry; returns (list of values, number of sessions in the window)."""
    i = bisect_left(all_dates, entry)
    win = all_dates[max(0, i - WINDOW):i]
    return [dvol[d] for d in win if d in dvol], len(win)


def year_job(year, primary_path, out):
    from r2_storage import client
    from archive_coverage_audit import DELISTED, key_date, list_dates, read_file
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
    rows = []
    if entries:
        want = {x for e in entries for x in (e['sym'], e['sym'] + DELISTED)}
        keys = list_dates(s3, 'stock', year - 1)[-(WINDOW + 10):] + list_dates(s3, 'stock', year)
        dvol, dates = defaultdict(dict), []
        with ThreadPoolExecutor(8) as pool:
            for start in range(0, len(keys), 32):
                chunk = keys[start:start + 32]
                for key, _, t in pool.map(lambda k: read_file(s3, k), chunk):
                    day = key_date(key)
                    dates.append(day)
                    for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                        if s in want and c and c > 0 and v is not None and v >= 0:
                            dvol[s][day] = c * v
        dates = sorted(set(dates))
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded (incl. tail of {year - 1})')
        for e in entries:
            series = dict(dvol.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **dvol.get(e['sym'] + DELISTED, {})}
            vals, nwin = window_values(dates, e['entry'], series)
            r = {'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'bars': len(vals), 'nwin': nwin}
            if vals:
                r['dv_mean'] = sum(vals) / len(vals)
                r['dv_median'] = statistics.median(vals)
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: {len(rows)} rows, {sum(r["bars"] == WINDOW for r in rows)} with all {WINDOW} bars')


def quant(v, p):
    s = sorted(v)
    if not s:
        return float('nan')
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def m(x):
    return f'${x / 1e6:,.1f}M'


def describe(rs):
    if not rs:
        return 'n=0'
    v = [r['dv_mean'] for r in rs]
    md = [r['dv_median'] for r in rs]
    return (f'n={len(rs):4d} | 15-session average dollar volume: mean {m(statistics.fmean(v))}, median {m(statistics.median(v))}, '
            f'quartiles {m(quant(v, .25))} / {m(quant(v, .75))}, p10 {m(quant(v, .1))}, p90 {m(quant(v, .9))}; under $5M {sum(x < 5e6 for x in v) / len(v):.0%}, '
            f'under $10M {sum(x < 10e6 for x in v) / len(v):.0%}; mean of per-event median day {m(statistics.fmean(md))}')


def scan(decl, f189, ret, dvf):
    import decline_buckets as db
    dev, _ = db.load(decl, f189, ret)
    dv = {}
    for p in sorted(Path(dvf).glob('*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            dv[(r['cik'], r['sym'], r['entry'])] = r
    joined, miss = [], 0
    for r in dev:
        d = dv.get((r['cik'], r['sym'], r['entry']))
        if d is None or d['bars'] < WINDOW or 'dv_mean' not in d:
            miss += 1
            continue
        joined.append({**r, 'dv_mean': d['dv_mean'], 'dv_median': d['dv_median']})
    print(f'development events {len(dev)}; with all {WINDOW} dollar-volume bars {len(joined)}; without {miss}')
    for W, lab in ((126, '6m'), (189, '9m')):
        print(f'\n=== {lab} fall (D = decline in entry-ATR units over {W} sessions) ===')
        for name, lo, hi in GROUPS:
            g = [r for r in joined if lo is None or (r.get(f'raw{W}') is not None and -r[f'raw{W}'] >= lo and (hi is None or -r[f'raw{W}'] < hi))]
            if lo is None and W != 126:
                continue
            print(f'-- {name} --\n   {describe(g)}')
    print('\nStatus: descriptive, post hoc; every group already passed the $3M floor; survivorship as in Entries 38/40/44.')


def selftest():
    dates = [f'2010-01-{d:02d}' for d in range(1, 29)]
    dvol = {d: 1e6 * (i + 1) for i, d in enumerate(dates)}
    vals, nwin = window_values(dates, '2010-01-20', dvol)
    assert nwin == 15 and len(vals) == 15 and vals[-1] == 19e6 and vals[0] == 5e6      # sessions 5..19 before the entry; entry day excluded
    vals2, nwin2 = window_values(dates, '2010-01-05', dvol)
    assert nwin2 == 4 and len(vals2) == 4
    assert quant([1, 2, 3, 4], .5) == 2.5 and m(2.5e6) == '$2.5M'
    rs = [{'dv_mean': 4e6 + 1e6 * k, 'dv_median': 3e6 + 1e6 * k} for k in range(10)]
    assert 'n=  10' in describe(rs) and 'under $5M 10%' in describe(rs)
    try:
        assert_allowed('2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    print('dollar_volume_profile self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('arg3', nargs='?')
    ap.add_argument('arg4', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'scan':
        scan(a.arg, a.arg2, a.arg3, a.arg4)
    else:
        raise SystemExit(__doc__)
