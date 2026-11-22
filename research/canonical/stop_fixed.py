"""C25: four-insider entry with a FIXED 2 ATR stop and a time exit at 1, 2, 3 and 6 months (Michael, 8 Nov 2026).

NEW CODE, PROVISIONAL. Question (Michael): "the 2ATR should be the initial stop ... let's use a 2ATR stop and hold it for 2 months and 1 month ... and also 6 months and 3 months."

Rule, declared in research_docs/CANDIDATES.md (C25) BEFORE any fixed-stop return was computed:
  entry      open of the entry session of each primary-set event (unchanged from Entry 28); entry session is session 1
  ATR        mean true range of the 14 sessions before entry (unchanged)
  1R         2 ATR
  stop       entry open - 2 ATR, set at entry, never moved (no trailing)
  exit       a session whose low touches the stop (low <= stop) exits at the stop; if it opens below the stop, at the open (gap)
             otherwise exit at the close of session H, H in {21, 42, 63, 126} = 1, 2, 3, 6 months
             a stock series that ends early is closed at its last close and flagged 'delist'
  returns    stock_atr = (exit - entry open) / ATR ; R = stock_atr / 2 ; SPY on the same window = (SPY close on the exit date / SPY open on entry - 1) * (entry open / ATR)
             excess_atr = stock_atr - spy_atr. Price only; costs shown as an extra column (0.10 ATR round trip).
Controls on the same events: the same horizon with NO stop (trade_outcome). The 21-session one must reproduce Entry 28 (n=1,372, excess +0.154).
Development entries only (D-068). Exits may fall in 2021 (as in Entry 43); no 2021-2025 ENTRY return is computed. The 2026 pilot is not run.
No variants of stop size, no trailing stop. Leads (FELL, Q1, BOTH) are not crossed with the stop.

Subcommands
  year YEAR --primary FILE --out FILE
  summary FOLDER
  --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, quarter, trade_outcome, true_range
from stop_test import block_range, clipped, wk

HORIZONS = (21, 42, 63, 126)
RISK_ATR = 2.0
COSTS = (0.10,)


def simulate_fixed(dates, stock, spy, entry, horizons=HORIZONS):
    """Returns {'status':..., 'by_h': {H: result}} ; each result mirrors stop_test.simulate fields."""
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
    if atr <= 0 or entry not in stock or entry not in spy:
        return {'status': 'atr_missing'}
    entry_open = stock[entry][0]
    stop = entry_open - RISK_ATR * atr
    hmax = max(horizons)
    hit_k, hit_px = None, None
    for k in range(i, min(i + hmax, len(dates))):
        d = dates[k]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        if l <= stop:
            hit_k, hit_px = k, (stop if (k == i or o > stop) else o)
            break
    out = {}
    for H in horizons:
        if hit_k is not None and hit_k <= i + H - 1:
            exit_k, exit_px, reason = hit_k, hit_px, 'stop'
        elif i + H > len(dates):
            out[H] = {'status': 'open'}
            continue
        else:
            idx = [k for k in range(i, i + H) if dates[k] in stock]
            if not idx:
                out[H] = {'status': 'no_bars'}
                continue
            exit_k = idx[-1]
            exit_px = stock[dates[exit_k]][3]
            reason = 'time' if exit_k == i + H - 1 else 'delist'
        exit_d = dates[exit_k]
        if exit_d not in spy:
            out[H] = {'status': 'spy_missing'}
            continue
        s = (exit_px - entry_open) / atr
        spy_atr = (spy[exit_d][3] / spy[entry][0] - 1) * (entry_open / atr)
        out[H] = {'status': 'ok', 'reason': reason, 'sessions': exit_k - i + 1, 'stock_atr': s, 'R': s / RISK_ATR,
                  'spy_atr': spy_atr, 'excess_atr': s - spy_atr, 'stock_pct': exit_px / entry_open - 1}
    return {'status': 'ok', 'atr': atr, 'entry_open': entry_open, 'by_h': out}


def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C25 is development years only'
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year, year + 1], want, 25, 30)
        spy_bars, _ = load_span(s3, 'etf', [year, year + 1], {'SPY'}, 25, 30)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = simulate_fixed(dates, series, spy, e['entry'])
            r['ctl'] = {}
            for H in HORIZONS:
                c = trade_outcome(dates, series, spy, e['entry'], H)
                r['ctl'][H] = {k: c[k] for k in ('status', 'stock_atr', 'spy_atr', 'excess_atr') if k in c}
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'via': e.get('via')})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))))


def line(label, rows):
    n = len(rows)
    if not n:
        return f'{label}: n=0'
    R = [r['R'] for r in rows]
    ex = [r['excess_atr'] for r in rows]
    win = [x for x in R if x > 0]
    los = [x for x in R if x <= 0]
    pf = (sum(win) / -sum(los)) if los and sum(los) < 0 else float('inf')
    return (f'{label}: n={n}  meanR {statistics.fmean(R):+.3f}  medianR {statistics.median(R):+.3f}  win {len(win) / n:.0%}  '
            f'avg win {statistics.fmean(win) if win else 0:+.2f}R  avg loss {statistics.fmean(los) if los else 0:+.2f}R  PF {pf:.2f}  '
            f'| stock {statistics.fmean(r["stock_atr"] for r in rows):+.3f}  SPY {statistics.fmean(r["spy_atr"] for r in rows):+.3f}  '
            f'excess {statistics.fmean(ex):+.3f} (median {statistics.median(ex):+.3f}, beat SPY {sum(x > 0 for x in ex)}/{n})  '
            f'| held mean {statistics.fmean(r["sessions"] for r in rows):.1f} median {statistics.median(r["sessions"] for r in rows):.0f}')


def summary(folder):
    raw = [r for p in sorted(Path(folder).glob('returns_*.json')) for r in json.loads(p.read_text())['rows']]
    for r in raw:
        assert_allowed(r['entry'])
        assert r['entry'] <= DEV_END
    print(f'=== A. Census: {len(raw)} development entries; status {dict(Counter(r["status"] for r in raw))} ===')
    good = [r for r in raw if r['status'] == 'ok']
    for H in HORIZONS:
        rows = []
        for r in good:
            x = r['by_h'][str(H)]
            if x.get('status') == 'ok':
                rows.append({**x, 'entry': r['entry'], 'sym': r['sym'], 'cik': r['cik'], 'ctl': r['ctl'][str(H)]})
        months = {21: 1, 42: 2, 63: 3, 126: 6}[H]
        print(f'\n################ HORIZON {months} month(s) = {H} sessions, fixed 2 ATR stop ################')
        print(f'exit reasons: {dict(Counter(r["reason"] for r in rows))}   share stopped out {sum(r["reason"] == "stop" for r in rows) / len(rows):.1%}')
        print(line('STOP version, ALL', rows))
        clean = [r for r in rows if r['reason'] != 'delist']
        print(line('  excluding delist exits', clean))
        stopped = [r for r in rows if r['reason'] == 'stop']
        held = [r for r in rows if r['reason'] != 'stop']
        print('  ' + line('stopped out', stopped))
        print('  ' + line('survived to the time exit', held))
        gaps = [r for r in rows if r['R'] < -1.0 - 1e-9]
        print(f'  losses worse than -1R (gaps): {len(gaps)} of {len(rows)} ({len(gaps) / len(rows):.1%}); worst R {min(r["R"] for r in rows):+.2f}')
        lo, hi, p = block_range(rows, 'excess_atr')
        print(f'  week-block 95% range of mean excess: {lo:+.3f} to {hi:+.3f}; draws <= 0: {p:.1%}')
        lo, hi, p = block_range(rows, 'R')
        print(f'  week-block 95% range of mean R: {lo:+.3f} to {hi:+.3f}; draws <= 0: {p:.1%}')
        both = [r for r in rows if r['ctl'].get('status') == 'complete']
        if both:
            m = lambda f: statistics.fmean(f(r) for r in both)
            print(f'  CONTROL, same {len(both)} events, same horizon, NO stop: stock {m(lambda r: r["ctl"]["stock_atr"]):+.3f}  SPY {m(lambda r: r["ctl"]["spy_atr"]):+.3f}  excess {m(lambda r: r["ctl"]["excess_atr"]):+.3f}')
            print(f'  stop version on those events:                  stock {m(lambda r: r["stock_atr"]):+.3f}  SPY {m(lambda r: r["spy_atr"]):+.3f}  excess {m(lambda r: r["excess_atr"]):+.3f}  (held {m(lambda r: r["sessions"]):.1f} sessions)')
            cl = [r['ctl']['stock_atr'] for r in both]
            print(f'  control no-stop mean stock ATR clipped at 1st/99th: {clipped(cl):+.3f}; stop version clipped {clipped([r["stock_atr"] for r in both]):+.3f}')
        base = statistics.fmean(r['excess_atr'] for r in rows)
        for c in COSTS:
            print(f'  cost {c:.2f} ATR: mean excess {base - c:+.3f}; mean R {statistics.fmean(r["R"] for r in rows) - c / RISK_ATR:+.3f}')
        print('  ' + line('2006-2010', [r for r in rows if r['entry'] < '2011']))
        print('  ' + line('2011-2020', [r for r in rows if r['entry'] >= '2011']))
        for q in EPISODES:
            print('  ' + line(f'episode {q}', [r for r in rows if quarter(r['entry']) == q]))
        print('  ' + line('without the three episodes', [r for r in rows if quarter(r['entry']) not in EPISODES]))
        byy = defaultdict(list)
        for r in rows:
            byy[r['entry'][:4]].append(r['R'])
        print('  mean R by year: ' + ' '.join(f'{y[2:]}:{statistics.fmean(v):+.2f}' for y, v in sorted(byy.items())) +
              f'  (positive in {sum(statistics.fmean(v) > 0 for v in byy.values())} of {len(byy)})')
        ranked = sorted(rows, key=lambda r: -r['R'])
        print('  mean R without top 1/3/10: ' + ' / '.join(f'{statistics.fmean(r["R"] for r in ranked[k:]):+.3f}' for k in (1, 3, 10)) +
              '; excess ' + ' / '.join(f'{statistics.fmean(r["excess_atr"] for r in ranked[k:]):+.3f}' for k in (1, 3, 10)))
        print(f'  mean R clipped {clipped([r["R"] for r in rows]):+.3f}; excess clipped {clipped([r["excess_atr"] for r in rows]):+.3f}')
        print('  top 5: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["R"]:+.1f}R' for r in ranked[:5]) + '   bottom 3: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["R"]:+.1f}R' for r in ranked[-3:]))
    print('\nIndependence: entries in the same weeks share market moves, and the four horizons use the same events, so they are one family, not four separate confirmations. Nothing here tests a frozen rule.')


def selftest():
    import datetime as dt
    d0 = dt.date(2010, 1, 4)
    dates, d = [], d0
    while len(dates) < 330:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    ei = 20
    entry = dates[ei]
    bars = lambda fn: {x: fn(k) for k, x in enumerate(dates)}
    spy = bars(lambda k: (100.0, 101.0, 99.0, 100.0))
    flat = lambda k: (50.0, 51.0, 49.0, 50.0)          # ATR 2 -> stop 46
    quiet = lambda k: (50.0, 51.0, 49.0, 50.0)
    # (a) day-one stop at 46 -> -1R for every horizon
    s = bars(flat); s[entry] = (50.0, 50.5, 45.0, 47.0)
    r = simulate_fixed(dates, s, spy, entry)
    for H in HORIZONS:
        x = r['by_h'][H]
        assert x['reason'] == 'stop' and abs(x['R'] + 1.0) < 1e-9 and x['sessions'] == 1, (H, x)
    # (b) gap on session 3: exit at the open 40 -> (40-50)/2 = -5 ATR
    s = bars(flat); s[dates[ei + 2]] = (40.0, 41.0, 39.0, 40.0)
    r = simulate_fixed(dates, s, spy, entry)
    x = r['by_h'][21]
    assert x['reason'] == 'stop' and abs(x['stock_atr'] + 5.0) < 1e-9 and x['sessions'] == 3, x
    # (c) stop hit on session 30: the 21-session horizon exits on time at the close, longer horizons are stopped
    s = bars(flat); s[dates[ei + 29]] = (50.0, 50.0, 45.5, 48.0)
    r = simulate_fixed(dates, s, spy, entry)
    assert r['by_h'][21]['reason'] == 'time' and r['by_h'][21]['sessions'] == 21, r['by_h'][21]
    for H in (42, 63, 126):
        assert r['by_h'][H]['reason'] == 'stop' and r['by_h'][H]['sessions'] == 30 and abs(r['by_h'][H]['stock_atr'] + 2.0) < 1e-9, (H, r['by_h'][H])
    # (d) no stop touched: low 49 > 46 always -> time exits at session H close, exit price 50 -> 0 ATR
    s = bars(quiet)
    r = simulate_fixed(dates, s, spy, entry)
    for H in HORIZONS:
        x = r['by_h'][H]
        assert x['reason'] == 'time' and x['sessions'] == H and abs(x['stock_atr']) < 1e-9, (H, x)
    # (e) delist at session 31
    s = {k: v for k, v in bars(quiet).items() if k <= dates[ei + 30]}
    r = simulate_fixed(dates, s, spy, entry)
    assert r['by_h'][63]['reason'] == 'delist' and r['by_h'][63]['sessions'] == 31, r['by_h'][63]
    # (f) open: series of dates too short for 126
    r = simulate_fixed(dates[:ei + 100], {k: v for k, v in bars(quiet).items() if k in dates[:ei + 100]}, spy, entry)
    assert r['by_h'][126]['status'] == 'open' and r['by_h'][63]['status'] == 'ok', r['by_h']
    # (g) D-068 guard
    try:
        simulate_fixed(dates, bars(quiet), spy, '2022-03-01')
        raise SystemExit('guard failed')
    except RuntimeError:
        pass
    print('selftest ok: day-one stop, gap fill, stop after the 1-month horizon, time exits, delist, open, D-068 guard')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.out)
    elif a.cmd == 'summary':
        summary(a.arg)
    else:
        ap.error('give a subcommand or --selftest')
