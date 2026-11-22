"""C24: four-insider entry managed with a 2 ATR initial stop and a 10-day trailing stop (Michael, 8 Nov 2026).

NEW CODE, PROVISIONAL. Question (Michael): "when the fourth buyer comes in, buy the stock and risk 2 ATRs and then use a 10-day trailing stop and see what happens."

Rule, declared in research_docs/CANDIDATES.md (C24) BEFORE any stop-managed return was computed:
  entry        open of the entry session of each primary-set event (next regular open after the filing that makes the fourth distinct buyer); entry session is day one
  ATR          mean true range of the 14 sessions before entry (same as Entry 28)
  1R           2 ATR
  initial stop entry open - 2 ATR, active from the entry session itself
  trailing     on each later session the stop is the lowest LOW of the 10 completed sessions before that session (pre-entry sessions count), never lowered, never below the initial stop
  exit         a session whose low touches the stop exits at the stop; if the session opens below the stop the exit is at the open (gap). No exit on the entry session at a price better than the stop.
  max hold     252 sessions (exit at that close). A stock series that ends early is closed at its last close and flagged 'delist'.
  returns      stock_atr = (exit - entry open) / ATR ; R = stock_atr / 2 ; SPY on the same window = (SPY close on the exit date / SPY open on the entry date - 1) * (entry open / ATR)
               excess_atr = stock_atr - spy_atr. Price only; costs shown as an extra column (0.10 ATR round trip).
Controls on the same events: 21-session hold (must reproduce Entry 28: development n=1,372, excess +0.154) and 252-session hold with no stop.
Development entries only (D-068). Exits may fall in 2021 (as in Entry 43); no 2021-2025 ENTRY return is computed. The 2026 pilot is not run.
No variants of stop length or risk size. Leads (FELL, Q1, BOTH) are not crossed with the stop here.

Subcommands
  year YEAR --primary FILE --out FILE   one entry year (stock + SPY bars from the archive)
  summary FOLDER                        merge and print
  --selftest
"""
import argparse, json, random, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, quarter, trade_outcome, true_range

MAX_HOLD = 252
TRAIL = 10
RISK_ATR = 2.0
COSTS = (0.10,)
SEED = 20261108


def simulate(dates, stock, spy, entry):
    """Stop-managed trade. stock, spy: {date: (open, high, low, close)}. Returns a dict with a status."""
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
    initial = entry_open - RISK_ATR * atr
    level = initial
    last_k, exit_px, exit_k, reason = None, None, None, None
    top = entry_open
    end = min(i + MAX_HOLD, len(dates))
    for k in range(i, end):
        d = dates[k]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        if k > i:
            lows = [stock[x][2] for x in dates[k - TRAIL:k] if x in stock]
            if len(lows) == TRAIL:
                level = max(level, min(lows))
        last_k = k
        if l <= level:
            exit_px = level if (k == i or o > level) else o
            exit_k = k
            reason = 'initial' if level <= initial + 1e-12 else 'trail'
            break
        top = max(top, h)
    if exit_k is None:
        if last_k is None:
            return {'status': 'no_bars'}
        if end - i >= MAX_HOLD and dates[i + MAX_HOLD - 1] in stock:
            exit_k, exit_px, reason = i + MAX_HOLD - 1, stock[dates[i + MAX_HOLD - 1]][3], 'time'
        elif i + MAX_HOLD > len(dates):
            return {'status': 'open', 'atr': atr, 'entry_open': entry_open}
        else:
            exit_k, exit_px, reason = last_k, stock[dates[last_k]][3], 'delist'
    exit_d = dates[exit_k]
    if exit_d not in spy:
        return {'status': 'spy_missing'}
    s = (exit_px - entry_open) / atr
    spy_atr = (spy[exit_d][3] / spy[entry][0] - 1) * (entry_open / atr)
    return {'status': 'ok', 'reason': reason, 'atr': atr, 'entry_open': entry_open, 'exit': exit_d,
            'sessions': exit_k - i + 1, 'stock_atr': s, 'R': s / RISK_ATR, 'spy_atr': spy_atr, 'excess_atr': s - spy_atr,
            'stock_pct': exit_px / entry_open - 1, 'spy_pct': spy[exit_d][3] / spy[entry][0] - 1,
            'mfe_atr': (top - entry_open) / atr}


def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C24 is development years only'
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
            r = simulate(dates, series, spy, e['entry'])
            c21 = trade_outcome(dates, series, spy, e['entry'], 21)
            c252 = trade_outcome(dates, series, spy, e['entry'], MAX_HOLD)
            r['h21'] = {k: c21[k] for k in ('status', 'stock_atr', 'spy_atr', 'excess_atr') if k in c21}
            r['h252'] = {k: c252[k] for k in ('status', 'stock_atr', 'spy_atr', 'excess_atr') if k in c252}
            r.update({'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'via': e.get('via')})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: ' + str(dict(Counter(r['status'] for r in rows))))


# ------------------------------------------------------------------ summary
def wk(entry):
    return date.fromisoformat(entry).isocalendar()[:2]


def block_range(rows, key, draws=10000, seed=SEED):
    weeks = defaultdict(list)
    for r in rows:
        weeks[wk(r['entry'])].append(r[key])
    tot = [(sum(v), len(v)) for v in weeks.values()]
    rng = random.Random(seed)
    means = sorted(sum(a for a, _ in p) / sum(b for _, b in p) for p in (rng.choices(tot, k=len(tot)) for _ in range(draws)))
    return means[int(0.025 * draws)], means[int(0.975 * draws)], sum(m <= 0 for m in means) / draws


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
            f'avg win {statistics.fmean(win) if win else 0:+.2f}R  avg loss {statistics.fmean(los) if los else 0:+.2f}R  profit factor {pf:.2f}  '
            f'| stock {statistics.fmean(r["stock_atr"] for r in rows):+.3f}  SPY {statistics.fmean(r["spy_atr"] for r in rows):+.3f}  '
            f'excess {statistics.fmean(ex):+.3f} (median {statistics.median(ex):+.3f}, beat SPY {sum(x > 0 for x in ex)}/{n})  '
            f'| sessions held mean {statistics.fmean(r["sessions"] for r in rows):.1f} median {statistics.median(r["sessions"] for r in rows):.0f}')


def clipped(vals, lo=0.01, hi=0.99):
    s = sorted(vals)
    a, b = s[int(lo * (len(s) - 1))], s[int(hi * (len(s) - 1))]
    return statistics.fmean(min(max(v, a), b) for v in vals)


def summary(folder):
    rows = [r for p in sorted(Path(folder).glob('returns_*.json')) for r in json.loads(p.read_text())['rows']]
    for r in rows:
        assert_allowed(r['entry'])
        assert r['entry'] <= DEV_END
    print(f'=== A. Census: {len(rows)} development entries; status {dict(Counter(r["status"] for r in rows))} ===')
    ok = [r for r in rows if r['status'] == 'ok']
    print(f'exit reasons (stop-managed): {dict(Counter(r["reason"] for r in ok))}')
    clean = [r for r in ok if r['reason'] != 'delist']
    print('\n=== B. Stop-managed result, price only (R = stock ATR / 2; excess over same-window SPY in ATR) ===')
    print(line('ALL (incl. delist exits)', ok))
    print(line('excluding delist exits', clean))
    for reason in ('initial', 'trail', 'time', 'delist'):
        print('  ' + line(f'exit by {reason}', [r for r in ok if r['reason'] == reason]))
    gaps = [r for r in ok if r['R'] < -1.0 - 1e-9]
    print(f'losses worse than -1R (gaps through the stop): {len(gaps)} of {len(ok)} ({len(gaps) / len(ok):.1%}); worst R {min(r["R"] for r in ok):+.2f}')
    lo, hi, p = block_range(ok, 'excess_atr')
    print(f'week-block 95% range of mean excess (10,000 draws): {lo:+.3f} to {hi:+.3f}; share of draws <= 0: {p:.1%}')
    lo, hi, p = block_range(ok, 'R')
    print(f'week-block 95% range of mean R: {lo:+.3f} to {hi:+.3f}; share of draws <= 0: {p:.1%}')
    print(f'independence: {len({r["cik"] for r in ok})} issuers, {len({r["entry"] for r in ok})} entry dates, {len({wk(r["entry"]) for r in ok})} entry weeks')
    print('\n=== C. Controls on the SAME events (price only; constant cohort = h21, h252 and stop all available) ===')
    both = [r for r in ok if r['h21'].get('status') == 'complete' and r['h252'].get('status') in ('complete', 'incomplete')]
    h21 = [r for r in rows if r['h21'].get('status') == 'complete']
    print(f'21-session hold, all complete (reproduction check; Entry 28 development n=1,372, excess +0.154): n={len(h21)}  stock {statistics.fmean(r["h21"]["stock_atr"] for r in h21):+.3f}  '
          f'SPY {statistics.fmean(r["h21"]["spy_atr"] for r in h21):+.3f}  excess {statistics.fmean(r["h21"]["excess_atr"] for r in h21):+.3f}')
    if both:
        n = len(both)
        mean = lambda f: statistics.fmean(f(r) for r in both)
        hold_days = statistics.fmean(r['sessions'] for r in both)
        print(f'constant cohort n={n}')
        print(f'  21-session hold:   stock {mean(lambda r: r["h21"]["stock_atr"]):+.3f}  SPY {mean(lambda r: r["h21"]["spy_atr"]):+.3f}  excess {mean(lambda r: r["h21"]["excess_atr"]):+.3f}  (21 sessions)')
        print(f'  252-session hold:  stock {mean(lambda r: r["h252"]["stock_atr"]):+.3f}  SPY {mean(lambda r: r["h252"]["spy_atr"]):+.3f}  excess {mean(lambda r: r["h252"]["excess_atr"]):+.3f}  (252 sessions, no stop; ALL mean can be distorted by data errors, see G/H)')
        print(f'  stop-managed:      stock {mean(lambda r: r["stock_atr"]):+.3f}  SPY {mean(lambda r: r["spy_atr"]):+.3f}  excess {mean(lambda r: r["excess_atr"]):+.3f}  ({hold_days:.1f} sessions average)')
        print(f'  excess per 21 sessions of capital tied up: 21-hold {mean(lambda r: r["h21"]["excess_atr"]):+.3f}; stop {mean(lambda r: r["excess_atr"]) / (hold_days / 21):+.3f}')
    print('\n=== D. Costs (extra columns, ATR round trip; R = ATR / 2) ===')
    base = statistics.fmean(r['excess_atr'] for r in ok)
    for c in COSTS:
        print(f'cost {c:.2f} ATR: mean excess {base - c:+.3f}; mean R {statistics.fmean(r["R"] for r in ok) - c / RISK_ATR:+.3f}')
    print('\n=== E. Eras, episodes, years ===')
    print(line('2006-2010', [r for r in ok if r['entry'] < '2011']))
    print(line('2011-2020', [r for r in ok if r['entry'] >= '2011']))
    for q in EPISODES:
        print(line(f'episode {q}', [r for r in ok if quarter(r['entry']) == q]))
    print(line('without the three episodes', [r for r in ok if quarter(r['entry']) not in EPISODES]))
    byy = defaultdict(list)
    for r in ok:
        byy[r['entry'][:4]].append(r)
    for y in sorted(byy):
        print(line(y, byy[y]))
    print('\n=== F. Concentration ===')
    ranked = sorted(ok, key=lambda r: -r['R'])
    for k in (1, 3, 5, 10):
        print(f'mean R without top {k}: {statistics.fmean(r["R"] for r in ranked[k:]):+.3f}; mean excess {statistics.fmean(r["excess_atr"] for r in ranked[k:]):+.3f}')
    print('top 10 by R: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["R"]:+.1f}R ({r["sessions"]}d {r["reason"]})' for r in ranked[:10]))
    print('bottom 8 by R: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r["R"]:+.1f}R ({r["sessions"]}d {r["reason"]})' for r in ranked[-8:]))
    print(f'mean R clipped at 1st/99th percentile: {clipped([r["R"] for r in ok]):+.3f} (unclipped {statistics.fmean(r["R"] for r in ok):+.3f}); '
          f'mean excess clipped {clipped([r["excess_atr"] for r in ok]):+.3f}')
    print(f'trades with |stock %| over 1,000%: {sum(abs(r["stock_pct"]) > 10 for r in ok)}')
    print('\n=== G. Trade counts and capital ===')
    years = len(byy)
    print(f'events per year {len(ok) / years:.1f}; average open positions = events per year x mean sessions held / 252 = {len(ok) / years * statistics.fmean(r["sessions"] for r in ok) / 252:.1f}')
    print('\nOverlap/independence note: entries in the same weeks share market moves; the week-block range narrows this only partly. Nothing here is a test of a frozen rule.')


def selftest():
    import datetime as dt
    d0 = dt.date(2010, 1, 4)
    dates, d = [], d0
    while len(dates) < 330:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    entry_i = 20
    entry = dates[entry_i]

    def bars(fn):
        return {dt_: fn(k) for k, dt_ in enumerate(dates)}
    spy = bars(lambda k: (100.0, 101.0, 99.0, 100.0))
    # flat pre-entry bars: range 2 around 50 -> ATR 2 (prior close 50)
    flat = lambda k: (50.0, 51.0, 49.0, 50.0)
    # (a) stop hit on day one: low 45 <= initial 46 -> exit at 46 -> -2 ATR -> -1R
    s = bars(flat); s[entry] = (50.0, 50.5, 45.0, 47.0)
    r = simulate(dates, s, spy, entry)
    assert r['status'] == 'ok' and r['reason'] == 'initial' and abs(r['R'] + 1.0) < 1e-9 and r['sessions'] == 1, r
    # (b) gap down on day 3 below the initial stop: exit at the open
    s = bars(flat)
    for k in range(entry_i, entry_i + 2):
        s[dates[k]] = (50.0, 51.0, 49.5, 50.5)
    s[dates[entry_i + 2]] = (40.0, 41.0, 39.0, 40.0)
    r = simulate(dates, s, spy, entry)
    # the 10-session low (49) is above the initial stop (46), so the trail is the active stop and the gap fill is at the open (40)
    assert r['reason'] == 'trail' and abs(r['stock_atr'] - (40.0 - 50.0) / 2.0) < 1e-9 and r['R'] < -1.0 and r['sessions'] == 3, r
    # (c) rally then trail: closes rise 1 per day for 15 sessions, then drop
    s = bars(flat)
    px = 50.0
    for k in range(entry_i, entry_i + 15):
        px += 1.0
        s[dates[k]] = (px - 0.5, px + 0.5, px - 0.6, px)
    for k in range(entry_i + 15, len(dates)):
        s[dates[k]] = (px - 5, px - 4, px - 6, px - 5)   # sharp drop and flat
    r = simulate(dates, s, spy, entry)
    # the drop to ~60 does not touch the 10-session low (55.4) at once; the trail climbs to 59 and a later low of 59 exits there: (59 - 50.5) / 2 = 4.25 ATR
    assert r['reason'] == 'trail' and r['sessions'] == 20 and abs(r['stock_atr'] - 4.25) < 1e-9 and r['R'] > 0, r
    # trailing stop never lowered: level after rally is the 10-session low
    # (d) time exit: sideways quiet stock above the stops for 252 sessions
    s = bars(lambda k: (50.0, 50.6 + 0.001 * k, 49.4 + 0.001 * k, 50.0))   # lows rise a little each day, so no session touches the 10-session low
    for k in range(0, entry_i):
        s[dates[k]] = (50.0, 51.0, 49.0, 50.0)
    r = simulate(dates, s, spy, entry)
    assert r['reason'] == 'time' and r['sessions'] == MAX_HOLD, r
    # (e) delist: series ends at session 30 with no stop touched
    s = bars(lambda k: (50.0, 50.6 + 0.001 * k, 49.4 + 0.001 * k, 50.0))   # lows rise a little each day, so no session touches the 10-session low
    for k in range(0, entry_i):
        s[dates[k]] = (50.0, 51.0, 49.0, 50.0)
    s = {k: v for k, v in s.items() if k <= dates[entry_i + 30]}
    r = simulate(dates, s, spy, entry)
    assert r['reason'] == 'delist' and r['sessions'] == 31, r
    # D-068 guard
    try:
        simulate(dates, s, spy, '2022-03-01')
        raise SystemExit('guard failed')
    except RuntimeError:
        pass
    assert abs(clipped([1, 2, 3, 100]) - clipped([1, 2, 3, 100])) < 1e-12
    print('selftest ok: day-one stop, gap fill, trailing exit, time exit, delist exit, D-068 guard')


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
