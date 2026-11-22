"""C29 (POST HOC, Michael 9 Nov 2026): absolute results (not relative to SPY) of the deep-fall rule F: maximum adverse excursion (MAE) and maximum favorable
excursion (MFE) at one and two months, then a 20-day trailing stop and a 4 ATR trailing stop.  "Keep it" (Entry 67): the deep-fall term is F alone.

NEW CODE, PROVISIONAL.  Development entries only (D-068; exits may fall after 2020-12-31 as in Entries 43 and 62; no 2021+ ENTRY is simulated); the 2026 pilot
is not run.  No sealed return is read.  Same entry as Entry 28: the open of the entry session (day one); ATR = mean true range of the 14 sessions before entry.
Cohort and flags as Entries 66-67 (events with roles, lead63, raw252; n=1,275): F = raw252 <= -15.0 ATR; R1 = neither CEO nor CFO among the buyers;
N = lead63 <= its 20th percentile.  Groups: ALL (the cohort), F, NOT F, SF2 = at least 2 of (R1, N, F) (Entry 67 S_F >= 2).

DECLARED BEFORE RUNNING:
 A. Excursions.  H = 21 sessions ("1 month") and 42 sessions ("2 months"); sessions 1..H include the entry session.  Complete trades only (the stock still has a
    bar on session H); the count of incomplete ones is shown.
      MAE_H = (lowest LOW of sessions 1..H - entry open) / ATR  and in percent of the entry open     (a loss is negative)
      MFE_H = (highest HIGH of sessions 1..H - entry open) / ATR and in percent
      close_H = close of session H vs the entry open: stock in ATR and percent, SPY on the same window (open of the entry session to the close of session H) in
      percent and in the stock's ATR units, excess = stock - SPY in ATR (D-053), win = close_H above the entry open.
    Per group: n, mean / median / 10th / 25th / 75th / 90th percentile of MAE and MFE (ATR and percent); share of trades whose MAE reached -1, -2, -3, -4 ATR;
    MAE among trades that closed up at H vs down; share of the trades that CLOSED UP whose MAE reached -2, -3, -4 ATR (a stop that wide would have cut a winner);
    edge ratio = mean MFE / mean |MAE|; the three worst MAEs; close_H mean / median / win rate with SPY beside it; week-block 95% range of the mean close_H.
 B. Stops, simulated on the daily path, price only, 252-session maximum hold (exit at that close), a series that ends early is closed at its last close
    ('delist'); fills at the stop price, or at the open if the session opens below the stop (gap); a session whose LOW touches the stop exits that session.
      T20  = Entry 62's rule with a 20-session window: initial stop = entry open - 2 ATR from the entry session; from the second session the stop is the lowest
             LOW of the 20 completed sessions before that session (pre-entry sessions count), never lowered, never below the initial stop.  R = stock ATR / 2.
      A4   = a 4 ATR trailing stop: stop on session k = max(entry open - 4 ATR, highest HIGH of sessions 1..k-1 - 4 ATR), ATR fixed at the entry value, never lowered,
             active from the entry session.  R = stock ATR / 4.
    Per group and rule: n; mean R, median R, win rate, average win and loss in R, profit factor; stock / SPY / excess (ATR) and stock in percent; median stock
    percent; sessions held mean and median; exit reasons; share exited on a gap below the stop; worst loss in R; the same net of 0.10 ATR round-trip cost;
    week-block 95% range of the mean stock ATR; 2006-10 vs 2011-20; without 2008Q4 / 2011Q3 / 2020Q1.  Controls on the same events: close_21 and close_42
    (section A) and the 252-session no-stop hold.
 C. F by dollar-volume band (Entry 54 definition): n, median MAE_21, median MFE_21, mean close_21 in ATR and percent.
 No chance test and no variants of window or ATR multiple (the two stops are Michael's choices).  Reproduction checks printed: F close_21 excess must equal
 Entry 67 (n=269, +0.599); ALL 21-session excess must equal Entry 66 (n=1,273, +0.189).
 Cautions written in advance: F and SF2 were chosen after Entries 36-67, so nothing here is out-of-sample; daily bars hide the order of the low and the high inside
 a session, so a touched stop is filled at the stop price; the archive holds almost no wipe-outs (Entry 65), so real losses can be worse than the worst rows here;
 4 ATR is about 28% of the price for a stock with a 7% ATR; results in the 2008-09 and 2020 crashes dominate the sample (Entries 66-67); absolute results include
 the market's own move, so SPY is shown beside every stock number; anything picked because it looks best after this run is a lead, not a rule.

Usage:  python excursion_stops.py year YEAR --primary FILE --out FILE
        python excursion_stops.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER SIM_FOLDER DV_FOLDER
        python excursion_stops.py --selftest
"""
import argparse, json, statistics, sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_decline as fd
import score_scan as ss
import context_scan as cs
import drawdown_scan as dd
from refined_baseline import ATR_BARS, DEV_END, EPISODES, assert_allowed, quarter, trade_outcome, true_range
from stop_test import block_range, wk

HORIZONS = (21, 42)
MAX_HOLD = 252
F_CUT = -15.0
COSTS = (0.10,)
RULES = {'t20': {'risk': 2.0, 'label': 'T20 (2 ATR initial, 20-session low trail)'}, 'a4': {'risk': 4.0, 'label': 'A4 (4 ATR trail below the highest high)'}}


# ------------------------------------------------------------------ path statistics
def entry_ctx(dates, stock, spy, entry):
    assert_allowed(entry)
    i = bisect_left(dates, entry)
    if i >= len(dates) or dates[i] != entry:
        return None, {'status': 'entry_not_session'}
    if i < ATR_BARS + 1:
        return None, {'status': 'atr_missing'}
    window = dates[i - ATR_BARS - 1:i]
    if any(d not in stock for d in window):
        return None, {'status': 'atr_missing'}
    atr = sum(true_range(stock[window[k]], stock[window[k - 1]][3]) for k in range(1, len(window))) / ATR_BARS
    if atr <= 0 or entry not in stock or entry not in spy:
        return None, {'status': 'atr_missing'}
    return (i, atr, stock[entry][0]), None


def path_stats(dates, stock, spy, entry, H):
    """MAE / MFE over sessions 1..H (session 1 = entry session) and the close of session H. status complete only if session H has a stock bar."""
    ctx, err = entry_ctx(dates, stock, spy, entry)
    if err:
        return err
    i, atr, op = ctx
    j = i + H - 1
    if j >= len(dates):
        return {'status': 'open', 'atr': atr, 'entry_open': op}
    days = [d for d in dates[i:j + 1] if d in stock]
    lows = [(stock[d][2], k) for k, d in enumerate(days)]
    highs = [(stock[d][1], k) for k, d in enumerate(days)]
    lo, lo_k = min(lows)
    hi, hi_k = max(highs, key=lambda t: (t[0], -t[1]))
    if dates[j] not in spy:
        return {'status': 'spy_missing'}
    last = days[-1]
    scale = op / atr
    spy_pct = spy[dates[j]][3] / spy[entry][0] - 1
    s = (stock[last][3] - op) / atr
    return {'status': 'complete' if dates[j] in stock else 'incomplete', 'atr': atr, 'entry_open': op,
            'mae_atr': (lo - op) / atr, 'mfe_atr': (hi - op) / atr, 'mae_pct': lo / op - 1, 'mfe_pct': hi / op - 1, 'mae_k': lo_k + 1, 'mfe_k': hi_k + 1,
            'close_atr': s, 'close_pct': stock[last][3] / op - 1, 'spy_pct': spy_pct, 'spy_atr': spy_pct * scale, 'excess_atr': s - spy_pct * scale}


def simulate_stop(dates, stock, spy, entry, rule):
    ctx, err = entry_ctx(dates, stock, spy, entry)
    if err:
        return err
    i, atr, op = ctx
    risk = RULES[rule]['risk']
    initial = op - risk * atr
    level, top = initial, op
    last_k = exit_k = exit_px = reason = None
    end = min(i + MAX_HOLD, len(dates))
    for k in range(i, end):
        d = dates[k]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        if rule == 't20':
            if k > i:
                lows = [stock[x][2] for x in dates[k - 20:k] if x in stock]
                if len(lows) == 20:
                    level = max(level, min(lows))
        else:
            level = max(level, top - 4.0 * atr)
        last_k = k
        if l <= level:
            gap = k > i and o <= level
            exit_px = o if gap else level
            exit_k = k
            reason = ('gap' if gap else 'initial' if level <= initial + 1e-12 else 'trail')
            break
        top = max(top, h)
    if exit_k is None:
        if last_k is None:
            return {'status': 'no_bars'}
        if end - i >= MAX_HOLD and dates[i + MAX_HOLD - 1] in stock:
            exit_k, exit_px, reason = i + MAX_HOLD - 1, stock[dates[i + MAX_HOLD - 1]][3], 'time'
        elif i + MAX_HOLD > len(dates):
            exit_k, exit_px, reason = last_k, stock[dates[last_k]][3], 'open'
        else:
            exit_k, exit_px, reason = last_k, stock[dates[last_k]][3], 'delist'
    exit_d = dates[exit_k]
    if exit_d not in spy:
        return {'status': 'spy_missing'}
    s = (exit_px - op) / atr
    spy_pct = spy[exit_d][3] / spy[entry][0] - 1
    return {'status': 'ok', 'reason': reason, 'atr': atr, 'entry_open': op, 'exit': exit_d, 'sessions': exit_k - i + 1, 'stock_atr': s, 'R': s / risk,
            'spy_atr': spy_pct * op / atr, 'excess_atr': s - spy_pct * op / atr, 'stock_pct': exit_px / op - 1, 'spy_pct': spy_pct}


def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C29 is development years only'
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year, year + 1, year + 2], want, 25, 30)
        spy_bars, _ = load_span(s3, 'etf', [year, year + 1, year + 2], {'SPY'}, 25, 30)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}')
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = {'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'via': e.get('via')}
            for H in HORIZONS:
                r[f'p{H}'] = path_stats(dates, series, spy, e['entry'], H)
            for rule in RULES:
                r[rule] = simulate_stop(dates, series, spy, e['entry'], rule)
            c = trade_outcome(dates, series, spy, e['entry'], MAX_HOLD)
            r['h252'] = {k: c[k] for k in ('status', 'stock_atr', 'spy_atr', 'excess_atr', 'stock_pct') if k in c}
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: p21 {dict(Counter(r["p21"]["status"] for r in rows))}; p42 {dict(Counter(r["p42"]["status"] for r in rows))}; '
          f't20 {dict(Counter(r["t20"]["status"] for r in rows))}; a4 {dict(Counter(r["a4"]["status"] for r in rows))}')


# ------------------------------------------------------------------ summary
def load_sim(folder, dev):
    sim = {}
    for p in sorted(Path(folder).glob('exc_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            sim[(r['cik'], r['sym'], r['entry'])] = r
    out, miss = [], 0
    for r in dev:
        s = sim.get((r['cik'], r['sym'], r['entry']))
        if s is None:
            miss += 1
            continue
        out.append({**r, **{k: s[k] for k in ('p21', 'p42', 't20', 'a4', 'h252')}})
    print(f'cohort {len(dev)}; with simulated paths {len(out)}; missing {miss}')
    return out


def q(vals, p):
    import numpy as np
    return float(np.quantile(vals, p))


def f3(x):
    return f'{x:+.2f}'


def pctl(vals, scale=1.0, fmt='{:+.2f}'):
    return ' / '.join(fmt.format(q(vals, p) * scale) for p in (0.1, 0.25, 0.5, 0.75, 0.9))


def excursions(label, rows, H):
    comp = [r for r in rows if r[f'p{H}']['status'] == 'complete']
    inc = len(rows) - len(comp)
    if not comp:
        print(f'  [{label}] H={H}: n=0')
        return
    P = [r[f'p{H}'] for r in comp]
    mae, mfe = [p['mae_atr'] for p in P], [p['mfe_atr'] for p in P]
    up = [p for p in P if p['close_atr'] > 0]
    dn = [p for p in P if p['close_atr'] <= 0]
    n = len(P)
    print(f'  [{label}] H={H} sessions: n={n} complete ({inc} incomplete, not used)')
    print(f'     MAE ATR mean {statistics.fmean(mae):+.2f} | 10/25/50/75/90th pct {pctl(mae)} | percent {pctl([p["mae_pct"] for p in P], 100, "{:+.0f}%")}')
    print(f'     MFE ATR mean {statistics.fmean(mfe):+.2f} | 10/25/50/75/90th pct {pctl(mfe)} | percent {pctl([p["mfe_pct"] for p in P], 100, "{:+.0f}%")}')
    print('     MAE reached -1 / -2 / -3 / -4 ATR: ' + ' / '.join(f'{sum(m <= -t for m in mae) / n:.0%}' for t in (1, 2, 3, 4)) +
          f' | edge ratio mean MFE / mean |MAE| {statistics.fmean(mfe) / -statistics.fmean(mae):.2f}')
    print(f'     closed up {len(up)} ({len(up) / n:.0%}), down {len(dn)}: median MAE of up-closers {statistics.median(p["mae_atr"] for p in up) if up else float("nan"):+.2f}, '
          f'of down-closers {statistics.median(p["mae_atr"] for p in dn) if dn else float("nan"):+.2f}; share of the UP-closers whose MAE reached -2 / -3 / -4 ATR: '
          + ' / '.join(f'{(sum(p["mae_atr"] <= -t for p in up) / len(up)) if up else float("nan"):.0%}' for t in (2, 3, 4)))
    worst = sorted(comp, key=lambda r: r[f'p{H}']['mae_atr'])[:3]
    print('     worst MAEs: ' + '; '.join(f'{r["sym"]} {r["entry"]} {r[f"p{H}"]["mae_atr"]:+.1f} ATR ({r[f"p{H}"]["mae_pct"]:+.0%}), closed {r[f"p{H}"]["close_pct"]:+.0%}' for r in worst))
    cl = [p['close_atr'] for p in P]
    rg = block_range([{'entry': r['entry'], 'x': r[f'p{H}']['close_atr']} for r in comp], 'x')
    print(f'     close_{H}: stock {statistics.fmean(cl):+.3f} ATR, mean {statistics.fmean(p["close_pct"] for p in P):+.1%}, median {statistics.median(p["close_pct"] for p in P):+.1%} '
          f'(median {statistics.median(cl):+.2f} ATR), win {len(up) / n:.0%} | SPY {statistics.fmean(p["spy_atr"] for p in P):+.3f} ATR, mean {statistics.fmean(p["spy_pct"] for p in P):+.1%} '
          f'| excess {statistics.fmean(p["excess_atr"] for p in P):+.3f} | week-block 95% range of the mean stock ATR [{rg[0]:+.3f}, {rg[1]:+.3f}]')


def stop_line(label, rows, rule):
    S = [r[rule] for r in rows if r[rule]['status'] == 'ok']
    n = len(S)
    if not n:
        return f'  {label}: n=0'
    R = [s['R'] for s in S]
    win, los = [x for x in R if x > 0], [x for x in R if x <= 0]
    pf = (sum(win) / -sum(los)) if los and sum(los) < 0 else float('inf')
    sa = [s['stock_atr'] for s in S]
    rs = Counter(s['reason'] for s in S)
    rg = block_range([{'entry': r['entry'], 'x': r[rule]['stock_atr']} for r in rows if r[rule]['status'] == 'ok'], 'x')
    return (f'  {label}: n={n}  meanR {statistics.fmean(R):+.3f}  medianR {statistics.median(R):+.3f}  win {len(win) / n:.0%}  avg win {statistics.fmean(win) if win else 0:+.2f}R  '
            f'avg loss {statistics.fmean(los) if los else 0:+.2f}R  PF {pf:.2f}  worst {min(R):+.2f}R\n'
            f'      stock {statistics.fmean(sa):+.3f} ATR ({statistics.fmean(s["stock_pct"] for s in S):+.1%}, median {statistics.median(s["stock_pct"] for s in S):+.1%})  '
            f'SPY {statistics.fmean(s["spy_atr"] for s in S):+.3f} ({statistics.fmean(s["spy_pct"] for s in S):+.1%})  excess {statistics.fmean(s["excess_atr"] for s in S):+.3f}  '
            f'| net of cost 0.10 ATR: {statistics.fmean(sa) - 0.10:+.3f}  | stock range [{rg[0]:+.3f}, {rg[1]:+.3f}]\n'
            f'      held mean {statistics.fmean(s["sessions"] for s in S):.1f} median {statistics.median(s["sessions"] for s in S):.0f} sessions; exits ' +
            ', '.join(f'{k} {v}' for k, v in rs.most_common()))


def scan(events, years, decl, regime, ret, sim_folder, dv_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    rows = load_sim(sim_folder, dev0)
    for r in rows:
        r['F'] = r['raw252'] <= F_CUT
        r['SF2'] = (int(r['R1']) + int(r['N']) + int(r['F'])) >= 2
    groups = [('ALL', rows), ('F', [r for r in rows if r['F']]), ('NOT F', [r for r in rows if not r['F']]), ('SF2 (>= 2 of R1, N, F)', [r for r in rows if r['SF2']])]
    print('\n=== Reproduction ===')
    for nm, g in groups[:2]:
        c = [r['p21'] for r in g if r['p21']['status'] == 'complete']
        print(f'  {nm}: close_21 n={len(c)} excess {statistics.fmean(p["excess_atr"] for p in c):+.3f} (stock {statistics.fmean(p["close_atr"] for p in c):+.3f}, SPY {statistics.fmean(p["spy_atr"] for p in c):+.3f})'
              + ('  [Entry 66: n=1,273, +0.189]' if nm == 'ALL' else '  [Entry 67: n=269, +0.599]'))
    print(f'  groups: ' + ', '.join(f'{nm} n={len(g)}' for nm, g in groups))
    print('\n=== A. Excursions and absolute close results at 1 month (21 sessions) and 2 months (42 sessions) ===')
    for nm, g in groups:
        for H in HORIZONS:
            excursions(nm, g, H)
    print('\n=== B. Stops (price only; 252-session maximum; fills at the stop or the open on a gap) ===')
    for nm, g in groups:
        print(f'\n [{nm}] (n={len(g)}); controls on the same events:')
        for H in HORIZONS:
            c = [r[f'p{H}'] for r in g if r[f'p{H}']['status'] == 'complete']
            print(f'   no-stop close_{H}: n={len(c)} stock {statistics.fmean(p["close_atr"] for p in c):+.3f} ATR ({statistics.fmean(p["close_pct"] for p in c):+.1%}), SPY {statistics.fmean(p["spy_atr"] for p in c):+.3f}, win {sum(p["close_atr"] > 0 for p in c) / len(c):.0%}')
        h = [r['h252'] for r in g if r['h252'].get('status') == 'complete']
        if h:
            print(f'   no-stop 252-session hold: n={len(h)} stock {statistics.fmean(x["stock_atr"] for x in h):+.3f} ATR ({statistics.fmean(x["stock_pct"] for x in h):+.1%}), SPY {statistics.fmean(x["spy_atr"] for x in h):+.3f}')
        for rule in RULES:
            print(stop_line(RULES[rule]['label'], g, rule))
            e1 = [r for r in g if r['entry'] < '2011-01-01']
            e2 = [r for r in g if r['entry'] >= '2011-01-01']
            ne = [r for r in g if quarter(r['entry']) not in EPISODES]
            m = lambda rs: (statistics.fmean(r[rule]['stock_atr'] for r in rs if r[rule]['status'] == 'ok') if any(r[rule]['status'] == 'ok' for r in rs) else float('nan'))
            print(f'      2006-10 {m(e1):+.3f} (n={len(e1)}) | 2011-20 {m(e2):+.3f} (n={len(e2)}) | no episodes {m(ne):+.3f} (n={len(ne)})')
    print('\n=== C. F by dollar-volume band (Entry 54 definition) ===')
    fr = cs.load_dv(dv_folder, [r for r in rows if r['F']])
    for bn, lo, hi in cs.DV_BANDS:
        g = [r for r in cs.band_rows(fr, lo, hi) if r['p21']['status'] == 'complete']
        if not g:
            print(f'  {bn}: n=0')
            continue
        P = [r['p21'] for r in g]
        print(f'  {bn:15s} n={len(g):3d}  median MAE_21 {statistics.median(p["mae_atr"] for p in P):+.2f} ATR ({statistics.median(p["mae_pct"] for p in P):+.0%})  '
              f'median MFE_21 {statistics.median(p["mfe_atr"] for p in P):+.2f} ({statistics.median(p["mfe_pct"] for p in P):+.0%})  close_21 mean {statistics.fmean(p["close_atr"] for p in P):+.3f} ATR ({statistics.fmean(p["close_pct"] for p in P):+.1%}), SPY {statistics.fmean(p["spy_atr"] for p in P):+.3f}')
    print('\nPOST HOC; no chance test; two named stop rules only.')


# ------------------------------------------------------------------ self test
def selftest():
    from datetime import date, timedelta
    d0, dates = date(2010, 1, 4), []
    k = 0
    while len(dates) < 400:
        x = d0 + timedelta(days=k)
        k += 1
        if x.weekday() < 5:
            dates.append(x.isoformat())
    stock, spy = {}, {}
    for n, d in enumerate(dates):
        spy[d] = (100.0, 101.0, 99.0, 100.0 + 0.1 * n)
        stock[d] = (10.0, 10.5, 9.5, 10.0)                       # true range 1.0 -> ATR 1.0
    i = 60
    entry = dates[i]
    # session 3 (i+2): low 8.0; session 5 (i+4): high 14.0; session 21: close 12.0
    stock[dates[i + 2]] = (10.0, 10.5, 8.0, 9.0)
    stock[dates[i + 4]] = (10.0, 14.0, 9.5, 13.0)
    stock[dates[i + 20]] = (11.0, 12.5, 10.5, 12.0)
    p = path_stats(dates, stock, spy, entry, 21)
    assert p['status'] == 'complete' and abs(p['mae_atr'] + 2.0) < 1e-9 and abs(p['mfe_atr'] - 4.0) < 1e-9 and abs(p['close_atr'] - 2.0) < 1e-9, p
    assert p['mae_k'] == 3 and p['mfe_k'] == 5 and abs(p['mae_pct'] + 0.2) < 1e-9 and abs(p['mfe_pct'] - 0.4) < 1e-9
    assert abs(p['spy_pct'] - (100.0 + 0.1 * (i + 20)) / 100.0 + 1) < 1e-9
    p42 = path_stats(dates, stock, spy, entry, 42)
    assert p42['status'] == 'complete' and abs(p42['mae_atr'] + 2.0) < 1e-9
    assert path_stats(dates, stock, spy, entry, 600)['status'] == 'open'
    # A4: initial 10 - 4 = 6; after the session-5 high of 14 the stop is 10; a later session that touches 10 exits at 10
    s = simulate_stop(dates, stock, spy, entry, 'a4')
    # session 3 low 8.0 > 6 no exit; session 5 high 14 -> level 10 from session 6; session 6 low 9.5 <= 10 and open 10 > 10? open == level -> gap branch (o <= level) -> exit at the open 10.0
    assert s['status'] == 'ok' and s['reason'] == 'gap' and abs(s['stock_atr']) < 1e-9 and s['sessions'] == 6, s
    # gap below: session 7 opens at 7.0 below the level 10 -> exit at the open
    stock2 = dict(stock)
    stock2[dates[i + 5]] = (10.0, 10.4, 10.2, 10.3)             # session 6 stays above 10
    stock2[dates[i + 6]] = (7.0, 7.5, 6.5, 7.0)
    s2 = simulate_stop(dates, stock2, spy, entry, 'a4')
    assert s2['reason'] == 'gap' and abs(s2['stock_atr'] + 3.0) < 1e-9 and s2['sessions'] == 7 and abs(s2['R'] + 0.75) < 1e-9, s2
    # T20: initial 8.0; lows of the 20 sessions before are 9.5 (and 8.0 on session 3) so the 20-session low is 8.0 until session 3 leaves the window
    t = simulate_stop(dates, stock, spy, entry, 't20')
    assert t['status'] == 'ok' and t['reason'] in ('trail', 'initial', 'gap') and t['sessions'] >= 1, t
    flat = {d: (10.0, 10.5, 9.5, 10.0) for d in dates}
    t2 = simulate_stop(dates, flat, spy, entry, 't20')
    assert t2['reason'] == 'trail' and t2['sessions'] >= 2, t2     # the 9.5 lows trail up to the stop level and touch it
    print('selftest ok: MAE / MFE / close, A4 trail and gap, T20 trail')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'year':
        year_job(int(a.args[0]), a.primary, a.out)
    elif a.cmd == 'scan':
        scan(*a.args)
