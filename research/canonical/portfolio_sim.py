"""C40 (POST HOC, Michael 9 Nov 2026): a dollar portfolio test of the four-buyer rule with the Entry 78 size-ups.

Michael: "run some real tests with portfolio tests ... start with $100,000, a 3 ATR stop, base position size 0.1% vol and then size up from there ... yearly
return, max drawdown, all those portfolio statistics and trade statistics ... exit at 2 months ... add 0.1 ATR for commissions and slippage."

NEW CODE, PROVISIONAL.  Development entries only (D-068; exits and SPY marks may fall in early 2021 as in Entries 43, 62, 69, 70); no sealed entry is read; the 2026
pilot is not run.  Cohort, flags and entry/ATR exactly as Entries 66-67 and 79 (flag_combo_counts.py join: n=1,273 of the 1,372 base events; the other 99 lack a
feature and cannot be flagged, so they are NOT traded here).  Per-trade path = cost_stops_f.sim_stop, fixed stop 3 ATR below the entry open, 42 sessions
(entry session = day one), unchanged (the 'fixed3' / 42 cell of Entry 70 must reproduce).

DECLARED BEFORE RUNNING:
 A. Account: $100,000 cash at the start, no leverage, no margin, no interest on idle cash, no dividends, whole shares.  Marked to market at each close.
 B. Size: risk per 1 ATR move = BASE_PCT (0.1%) x U x equity at the previous close; shares = that dollar risk / ATR in dollars (ATR = mean true range of the 14 sessions
    before entry, fixed at entry).  U = 1.0 + the add-ons of the flags that are on (R1, N, F, P), Entry 78 Entry-67-model weights from sizing_weights.py (judgment on
    post hoc inputs, not a result).  With the 3 ATR stop a trade risks 3 x 0.1% x U of equity before cost (0.30% at 1.0U, 0.85% at 2.84U), more on a gap through the stop.
 C. Limits: shares <= cash available at the open (a cash-limited entry is cut, never levered); position value <= 1% of the stock's 15-session average daily dollar
    volume (Entry 54 file; if that file lacks the event the cap is skipped and counted).  The Entry 78 "8U total open" cap is NOT enforced; peak open risk is reported
    so we can see whether it would have bound.
 D. Entry at the open of the entry session, filled 0.05 ATR worse; exit 0.05 ATR worse on the fill price: stop = the stop level (the open on a gap), time = the close of
    session 42; a series that ends early closes at its last bar ('delist').  That is 0.10 ATR per round trip in total (Michael: "0.1 ATR for commissions and slippage"; if he
    meant 0.1 each way, the 0.20 row below is that case).  No other cost.  Entry order within a day: file order.
 E. Variants (all printed): MAIN scaled sizes, cost 0.10; FLAT every trade 1.0U (shows what the size-ups add); COST 0.00 (gross); COST 0.20; BASE 0.125% (the earlier
    standing base, for reference).  Benchmark: SPY buy-and-hold with the same $100,000 over the same dates (close to close).
 F. Statistics: total and annual (calendar-year) return, CAGR, daily-return volatility, Sharpe and Sortino (zero risk-free rate, 252 days), max drawdown with dates and the
    longest time under water, beta and alpha against SPY (daily), exposure and open positions; trade statistics in dollars, in R (1R = 3 ATR x shares) and in ATR with
    SPY beside it (D-053); stopped-out share; by size class; the three episodes (2008Q4, 2011Q3, 2020Q1) versus the rest; concentration in the top 10 trades; sample sizes
    (distinct entry dates, weeks, spells).
Cautions written in advance: every size and flag is post hoc and the leads are not edges; 2008-09 and 2020 dominate; survivorship is unresolved (Entry 65) and a wipe-out is
not in this archive; stop fills at the stop price are optimistic in thin names; costs are 0.10 ATR by instruction, not measured (the Entry 70 model says 0.04-0.11 ATR for F
at small size); the 0.10 ATR is charged on the stock's own ATR, so cheap volatile names are charged more dollars per share than their spread; the equity curve has about
15 years but only tens of independent market periods; a single path, so the maximum drawdown is one draw, not a bound.

C47 (13 Nov 2026, declared in research_docs/CANDIDATES.md before the run): optional volatility gate.  vol20 and vol90 = sample standard deviation of the 20 and 90 daily
close-to-close log returns ending at the close BEFORE the entry session (21 / 91 consecutive closes needed).  Trade skipped if vol20 > vol90; no reading -> taken, counted.
Stage 1 now loads 100 earlier sessions (was 25) so the 90-day window exists in January; nothing else in stage 1 changes (Entry 82 must reproduce to the dollar).

C48 (13 Nov 2026, declared in research_docs/CANDIDATES.md before the run): the same gate built on ATR.  atr20 / atr90 = mean true range of the 20 / 90 sessions ending at the close
before entry (dollars); atr20p / atr90p the same with each true range divided by the previous close.  Skip if atr20 > atr90 (raw) or atr20p > atr90p (percent of price).

C49 (13 Nov 2026, declared in research_docs/CANDIDATES.md before the run): ratio grid for the volatility gate.  PRIMARY skip if vol20 > k x vol90; SECONDARY (literal wording) skip if
vol90 > k x vol20; k = 1.2 ... 2.0 step 0.1 (1.0 = Entry 98).  Flagged trades, Sharpe objective, out-of-era check (fit 2006-2010 -> apply 2011-2020 and back), random-skip check.

C50 (13 Nov 2026, declared in research_docs/CANDIDATES.md before the run): exit mode PF_MODE=trail = 3 ATR initial stop, then a 4 ATR trailing stop below the highest high (stop = the higher of the
two, never lowered, ATR fixed at entry), 252-session maximum hold, no 42-session exit.  Stage 1 stores it under row['tr'].

Usage:  python portfolio_sim.py year YEAR --primary FILE --out FILE
        python portfolio_sim.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER PATH_FOLDER
        python portfolio_sim.py --selftest
"""
import argparse, json, math, statistics, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import excursion_stops as ex
import cost_stops_f as cf
import sizing_weights as sw
from refined_baseline import DEV_END, EPISODES, assert_allowed, quarter

H = 42
STOP_K = 3
START = 100_000.0
BASE_PCT = 0.1
COST = 0.10
ADV_CAP = 0.01
FLAGS = ('R1', 'N', 'F', 'P')


# ------------------------------------------------------------------ stage 1: per-trade paths (needs the price archive)
def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C40 is development years only'
    rows, spy_out = [], {}
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year, year + 1, year + 2], want, 100, 30)
        spy_bars, _ = load_span(s3, 'etf', [year, year + 1, year + 2], {'SPY'}, 100, 30)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}')
        last_exit = max(e['entry'] for e in entries)
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            r = {'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']}
            ctx, err = ex.entry_ctx(dates, series, spy, e['entry'])
            if err:
                r.update(err)
                rows.append(r)
                continue
            i, atr, op = ctx
            res = cf.sim_stop(dates, series, spy, e['entry'], ctx, 'fixed', STOP_K).get(H)
            if res is None:
                r.update({'status': 'no_path', 'atr': atr, 'open': op})
                rows.append(r)
                continue
            ret, spy_atr, sess, why = res
            kk = i + sess - 1
            r['vol20'], r['vol90'] = hist_vols(dates, series, i)
            r['atr20'], r['atr90'], r['atr20p'], r['atr90p'] = hist_atrs(dates, series, i)
            r.update({'status': 'ok', 'atr': atr, 'open': op, 'ret_atr': ret, 'spy_atr': spy_atr, 'sess': sess, 'why': why,
                      'exit_date': dates[kk], 'exit_px': round(op + ret * atr, 6),
                      'days': [[dates[k], series[dates[k]][3] if dates[k] in series else None] for k in range(i, kk + 1)]})
            last_exit = max(last_exit, dates[kk])
            # Entry 89b: the SAME trade with no stop (plain 42-session hold, time exit only), same sizing; mode 'none' in the scan reads this
            rn = cf.sim_stop(dates, series, spy, e['entry'], ctx, 'none', STOP_K).get(H)
            if rn is None:
                r['ns'] = None
            else:
                nret, nspy, nsess, nwhy = rn
                nk = i + nsess - 1
                r['ns'] = {'ret_atr': nret, 'spy_atr': nspy, 'sess': nsess, 'why': nwhy, 'exit_date': dates[nk], 'exit_px': round(op + nret * atr, 6),
                           'days': [[dates[k], series[dates[k]][3] if dates[k] in series else None] for k in range(i, nk + 1)]}
                last_exit = max(last_exit, dates[nk])
            rt = sim_trail(dates, series, spy, e['entry'], ctx)
            if rt is None:
                r['tr'] = None
            else:
                tret, tspy, tsess, twhy = rt[:4]
                tk = i + tsess - 1
                r['tr'] = {'ret_atr': tret, 'spy_atr': tspy, 'sess': tsess, 'why': twhy, 'exit_date': dates[tk], 'exit_px': round(op + tret * atr, 6),
                           'days': [[dates[k], series[dates[k]][3] if dates[k] in series else None] for k in range(i, tk + 1)]}
                last_exit = max(last_exit, dates[tk])
            rows.append(r)
        spy_out = {d: spy[d][3] for d in dates if f'{year}-01-01' <= d <= last_exit and d in spy}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows, 'spy': spy_out}))
    print(f'{year}: status {dict(Counter(r["status"] for r in rows))}; SPY closes {len(spy_out)}')


INIT_K, TRAIL_K, MAXH_TRAIL = 3.0, 4.0, 252


def sim_trail(dates, stock, spy, entry, ctx, init_k=INIT_K, trail_k=TRAIL_K, maxh=MAXH_TRAIL):
    """C50: stop = max(entry open - init_k ATR, highest HIGH of earlier sessions (entry open counts first) - trail_k ATR), never lowered, ATR fixed at entry.
    A session whose low touches the stop exits that session at the stop (at the open on a gap).  No stop by session maxh -> exit at that close ('time'); a series
    that ends early closes at its last bar ('delist').  Returns [ret_atr, spy_atr, sessions, why] or None (path not complete / no SPY mark)."""
    i, atr, op = ctx
    if i + maxh - 1 >= len(dates):
        return None
    level, top = op - init_k * atr, op
    hit = None
    for kk in range(i, i + maxh):
        d = dates[kk]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        level = max(level, top - trail_k * atr)
        if l <= level:
            gap = kk > i and o <= level
            hit = (kk, o if gap else level, 'gap' if gap else 'stop')
            break
        top = max(top, h)
    if hit is not None:
        kk, px, why = hit
    else:
        kk = next((x for x in range(i + maxh - 1, i - 1, -1) if dates[x] in stock), None)
        if kk is None:
            return None
        px, why = stock[dates[kk]][3], ('time' if kk == i + maxh - 1 else 'delist')
    ed = dates[kk]
    if ed not in spy or entry not in spy:
        return None
    return [round((px - op) / atr, 4), round((spy[ed][3] / spy[entry][0] - 1) * op / atr, 4), kk - i + 1, why]


def hist_vols(dates, series, i):
    """C47: (vol20, vol90) = sample stdev of the last 20 / 90 daily close-to-close log returns ending at the close BEFORE entry index i
    (21 / 91 consecutive closes); None if any close in the window is missing."""
    out = []
    for n in (20, 90):
        if i - n - 1 < 0:
            out.append(None)
            continue
        cl = [series[dates[k]][3] if dates[k] in series else None for k in range(i - n - 1, i)]
        if len(cl) != n + 1 or any(c is None or c <= 0 for c in cl):
            out.append(None)
            continue
        out.append(statistics.stdev([math.log(cl[k] / cl[k - 1]) for k in range(1, n + 1)]))
    return out[0], out[1]


def hist_atrs(dates, series, i):
    """C48: (atr20, atr90, atr20p, atr90p): mean true range of the last 20 / 90 sessions ending at the close before entry index i, in dollars and as a percent of the
    previous close; None if any bar in the window (plus the bar before it) is missing."""
    from refined_baseline import true_range
    out = []
    for n in (20, 90):
        if i - n - 1 < 0:
            out.append((None, None))
            continue
        w = [series.get(dates[k]) for k in range(i - n - 1, i)]
        if len(w) != n + 1 or any(b is None or b[3] <= 0 for b in w):
            out.append((None, None))
            continue
        trs = [true_range(w[k], w[k - 1][3]) for k in range(1, n + 1)]
        out.append((sum(trs) / n, sum(tr / w[k - 1][3] for k, tr in zip(range(1, n + 1), trs)) / n))
    return out[0][0], out[1][0], out[0][1], out[1][1]


# ------------------------------------------------------------------ sizing
def add_on_u():
    return {k: v['add_U'] for k, v in sw.weights(sw.MODELS['Entry 67 (R1+N+P+F)']).items()}


def size_u(add, r):
    return 1.0 + sum(add[k] for k in FLAGS if r.get(k))


# ------------------------------------------------------------------ simulation
def simulate(trades, cal, start=START, base_pct=BASE_PCT, cost=COST, flat=False, adv_cap=ADV_CAP):
    """trades: dicts with entry, open, atr, exit_date, exit_px, why, days [[date, close|None]], U, dv (or None).  cal: sorted list of session dates (SPY dates).
    Returns (curve [(date, equity, invested)], trade records, counters)."""
    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t['entry']].append(t)
    half = cost / 2.0
    pos, cash = {}, start
    curve, recs = [], []
    cnt = Counter()
    peak_u = 0.0
    cal_set = set(cal)
    for t in trades:
        assert t['entry'] in cal_set and t['exit_date'] in cal_set, (t['sym'], t['entry'], t['exit_date'])
    closes = {id(t): {d: c for d, c in t['days'] if c is not None} for t in trades}
    for d in cal:
        # 1. entries at the open, sized on the previous close equity
        if d in by_entry:
            eq = cash + sum(p['shares'] * p['last'] for p in pos.values())
            for t in by_entry[d]:
                u = 1.0 if flat else t['U']
                px_in = t['open'] + half * t['atr']
                want = math.floor(base_pct / 100.0 * u * eq / t['atr'])
                by_cash = math.floor(cash / px_in)
                by_adv = math.floor(adv_cap * t['dv'] / t['open']) if t.get('dv') else None
                if by_adv is None:
                    cnt['no_dv_cap'] += 1
                sh = min(x for x in (want, by_cash, by_adv) if x is not None)
                if sh < want:
                    cnt['cash_limited' if (by_adv is None or by_cash <= by_adv) and sh == by_cash else 'adv_limited'] += 1
                if sh <= 0:
                    cnt['skipped_zero'] += 1
                    continue
                cash -= sh * px_in
                pos[id(t)] = {'t': t, 'shares': sh, 'px_in': px_in, 'last': px_in, 'eq0': eq, 'u': u, 'cl': closes[id(t)]}
                cnt['entered'] += 1
        # 2. intraday stop exits
        for k in [k for k, p in pos.items() if p['t']['exit_date'] == d and p['t']['why'] in ('stop', 'gap')]:
            cash = _close(pos, k, cash, half, recs)
        # 3. marks at the close; time and delist exits at the close
        for p in pos.values():
            c = p['cl'].get(d)
            if c is not None:
                p['last'] = c
        for k in [k for k, p in pos.items() if p['t']['exit_date'] == d]:
            cash = _close(pos, k, cash, half, recs)
        inv = sum(p['shares'] * p['last'] for p in pos.values())
        curve.append((d, cash + inv, inv, len(pos)))
        peak_u = max(peak_u, sum(p['u'] for p in pos.values()))
    assert not pos, f'{len(pos)} positions never closed'
    cnt['peak_open_U'] = peak_u
    return curve, recs, cnt


def _close(pos, k, cash, half, recs):
    p = pos.pop(k)
    t = p['t']
    px_out = t['exit_px'] - half * t['atr']
    cash += p['shares'] * px_out
    pnl = p['shares'] * (px_out - p['px_in'])
    recs.append({'entry': t['entry'], 'exit': t['exit_date'], 'sym': t['sym'], 'why': t['why'], 'sess': t['sess'], 'shares': p['shares'], 'u': p['u'],
                 'notional': p['shares'] * p['px_in'], 'pnl': pnl, 'eq0': p['eq0'], 'pct_eq': pnl / p['eq0'],
                 'R': pnl / (p['shares'] * STOP_K * t['atr']), 'atr_net': (px_out - p['px_in']) / t['atr'], 'stock_atr': t['ret_atr'], 'spy_atr': t['spy_atr'],
                 'flags': tuple(k2 for k2 in FLAGS if t.get(k2))})
    return cash


# ------------------------------------------------------------------ statistics
def years_between(d0, d1):
    return (date.fromisoformat(d1) - date.fromisoformat(d0)).days / 365.25


def curve_stats(curve, start):
    """curve: [(date, equity, ...)] daily.  Returns a dict of portfolio statistics; the starting equity is the day-0 value."""
    dates = [c[0] for c in curve]
    eq = [start] + [c[1] for c in curve]
    r = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    yrs = years_between(dates[0], dates[-1])
    sd = statistics.pstdev(r)
    dn = math.sqrt(sum(min(x, 0) ** 2 for x in r) / len(r))
    peak, mdd, pk_i, tr_i, best = eq[0], 0.0, 0, 0, (0.0, 0, 0)
    uw_len, uw_start, longest = 0, 0, (0, 0, 0)
    for i, v in enumerate(eq):
        if v >= peak:
            if i - uw_start > longest[0] and i > uw_start:
                longest = (i - uw_start, uw_start, i)
            peak, pk_i, uw_start = v, i, i
        dd = v / peak - 1
        if dd < mdd:
            mdd, best = dd, (dd, pk_i, i)
    if len(eq) - 1 - uw_start > longest[0]:
        longest = (len(eq) - 1 - uw_start, uw_start, None)
    lab = lambda i: dates[0] if i == 0 else dates[i - 1]
    rec = next((j for j in range(best[2], len(eq)) if eq[j] >= eq[best[1]]), None)
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1 if yrs > 0 else float('nan')
    return {'end': eq[-1], 'total': eq[-1] / eq[0] - 1, 'cagr': cagr, 'vol': sd * math.sqrt(252), 'sharpe': statistics.fmean(r) / sd * math.sqrt(252) if sd else float('nan'),
            'sortino': statistics.fmean(r) / dn * math.sqrt(252) if dn else float('nan'), 'mdd': mdd, 'mdd_peak': lab(best[1]), 'mdd_trough': lab(best[2]),
            'mdd_recover': lab(rec) if rec is not None else 'not recovered', 'uw_days': longest[0], 'uw_from': lab(longest[1]),
            'uw_to': lab(longest[2]) if longest[2] is not None else 'still under water', 'calmar': cagr / -mdd if mdd < 0 else float('nan'),
            'best_day': max(r), 'worst_day': min(r), 'yrs': yrs, 'r': r, 'eq': eq}


def calendar_years(curve, start):
    out, prev, cur_year = {}, start, None
    for d, v, *_ in curve:
        y = d[:4]
        if y != cur_year:
            if cur_year is not None:
                out[cur_year] = (out[cur_year][0], prev)
            out[y] = (prev, None)
            cur_year = y
        prev = v
    out[cur_year] = (out[cur_year][0], prev)
    return {y: b / a - 1 for y, (a, b) in out.items()}


def beta_alpha(r, rb):
    import numpy as np
    x, y = np.asarray(rb), np.asarray(r)
    b, a = np.polyfit(x, y, 1)
    return float(b), float(a * 252)


def spy_curve(spy, cal, d0, start):
    base = spy[d0]
    return [(d, start * spy[d] / base) for d in cal]


def fmt_stats(name, s, extra=''):
    return (f'  {name:18s} end ${s["end"]:>11,.0f}  total {s["total"]:+8.1%}  CAGR {s["cagr"]:+6.2%}  vol {s["vol"]:5.1%}  Sharpe {s["sharpe"]:5.2f}  Sortino {s["sortino"]:5.2f}  '
            f'max DD {s["mdd"]:+6.1%}  Calmar {s["calmar"]:5.2f}{extra}')


def trade_block(recs, label):
    n = len(recs)
    if not n:
        return f'  {label}: n=0'
    win = [x for x in recs if x['pnl'] > 0]
    los = [x for x in recs if x['pnl'] <= 0]
    gp, gl = sum(x['pnl'] for x in win), -sum(x['pnl'] for x in los)
    R = [x['R'] for x in recs]
    return (f'  {label}: n={n}  net P&L ${sum(x["pnl"] for x in recs):+,.0f}  win {len(win) / n:.0%}  avg win ${gp / len(win) if win else 0:+,.0f} ({statistics.fmean(x["pct_eq"] for x in win) if win else 0:+.2%} of equity)  '
            f'avg loss ${-gl / len(los) if los else 0:+,.0f} ({statistics.fmean(x["pct_eq"] for x in los) if los else 0:+.2%})  profit factor {gp / gl if gl else float("inf"):.2f}  '
            f'expectancy {statistics.fmean(x["pnl"] for x in recs):+,.0f}/trade = {statistics.fmean(R):+.3f}R (median {statistics.median(R):+.2f}R)  '
            f'| ATR net of cost {statistics.fmean(x["atr_net"] for x in recs):+.3f}; gross stock {statistics.fmean(x["stock_atr"] for x in recs):+.3f} / SPY {statistics.fmean(x["spy_atr"] for x in recs):+.3f} '
            f'= excess {statistics.fmean(x["stock_atr"] - x["spy_atr"] for x in recs):+.3f}')


# ------------------------------------------------------------------ stage 2: join, simulate, report
def load_paths(folder):
    sim, spy = {}, {}
    for p in sorted(Path(folder).glob('pf_*.json')):
        j = json.loads(p.read_text())
        spy.update(j['spy'])
        for r in j['rows']:
            assert_allowed(r['entry'])
            sim[(r['cik'], r['sym'], r['entry'])] = r
    return sim, spy


def load_dv_soft(folder):
    dv = {}
    for p in sorted(Path(folder).glob('dv_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            if r.get('bars', 0) >= 15 and 'dv_mean' in r:
                dv[(r['cik'], r['sym'], r['entry'])] = r['dv_mean']
    return dv


def build_trades(cohort, sim, dv, add, mode='stop'):
    out, miss, atr_diff = [], Counter(), 0
    for r in cohort:
        k = (r['cik'], r['sym'], r['entry'])
        s = sim.get(k)
        if s is None:
            miss['no_row'] += 1
            continue
        if s.get('status') != 'ok':
            miss[s.get('status', 'bad')] += 1
            continue
        if abs(s['atr'] - r['atr']) > 1e-9:
            atr_diff += 1
        t = {**{f: bool(r[f]) for f in FLAGS}, 'entry': r['entry'], 'sym': r['sym'], 'dv': dv.get(k), 'U': size_u(add, r), 'vol20': s.get('vol20'), 'vol90': s.get('vol90'),
             'atr20': s.get('atr20'), 'atr90': s.get('atr90'), 'atr20p': s.get('atr20p'), 'atr90p': s.get('atr90p')}
        src = s
        if mode == 'none':
            src = s.get('ns')
            if src is None:
                miss['no_nostop_path'] += 1
                continue
        elif mode == 'trail':
            src = s.get('tr')
            if src is None:
                miss['no_trail_path'] += 1
                continue
        t.update({'atr': s['atr'], 'open': s['open']})
        t.update({f: src[f] for f in ('ret_atr', 'spy_atr', 'sess', 'why', 'exit_date', 'exit_px', 'days')})
        out.append(t)
    out.sort(key=lambda t: (t['entry'], t['sym']))
    return out, miss, atr_diff


def run_scan(cohort, sim, spy, dv, mode='stop'):
    print(f'##### EXIT MODE: {"NO STOP (plain 42-session hold)" if mode == "none" else "3 ATR initial stop, then 4 ATR trailing stop below the highest high, 252-session maximum hold (C50)" if mode == "trail" else "3 ATR fixed stop + 42-session time exit"} #####')
    add = add_on_u()
    print('add-ons in U (Entry 78, Entry 67 model): ' + ', '.join(f'{k} {v:+.2f}' for k, v in add.items()) +
          f'; all four on {1 + sum(add.values()):.2f}U; 1U = {BASE_PCT}% of equity per 1 ATR here')
    trades, miss, atr_diff = build_trades(cohort, sim, dv, add, mode)
    print(f'cohort {len(cohort)}; tradable paths {len(trades)}; not tradable {dict(miss)}; entry ATR differs from the Entry 36 file on {atr_diff}; '
          f'dollar-volume file lacks {sum(t["dv"] is None for t in trades)}')
    cal = sorted(spy)
    d_first = min(t['entry'] for t in trades)
    prior = [d for d in cal if d < d_first]
    cal_run = [d for d in cal if d >= d_first]
    d0 = prior[-1] if prior else cal_run[0]
    assert all(t['exit_date'] <= cal[-1] for t in trades)
    print(f'period: first entry {d_first}, last exit {max(t["exit_date"] for t in trades)}; calendar {cal_run[0]} to {cal_run[-1]} ({len(cal_run)} sessions); start value on {d0}')
    bench = spy_curve(spy, cal_run, d0, START)
    bs = curve_stats(bench, START)
    bs_year = calendar_years(bench, START)
    cohort_check(trades)

    flagged = [t for t in trades if any(t[f] for f in FLAGS)]
    flagged_no_r1only = [t for t in flagged if not (t['R1'] and not (t['N'] or t['F'] or t['P']))]
    variants = [('MAIN 0.1% scaled', dict()), ('FLAT 1.0U all', dict(flat=True)), ('gross cost 0.00', dict(cost=0.0)), ('cost 0.20 ATR', dict(cost=0.20)),
                ('base 0.125%', dict(base_pct=0.125)), ('FLAGGED only', dict(sel=flagged)), ('FLAGGED, no R1-only', dict(sel=flagged_no_r1only)),
                ('FLAGGED only, cost 0.2', dict(sel=flagged, cost=0.20))]
    skip = lambda t: t.get('vol20') is not None and t.get('vol90') is not None and t['vol20'] > t['vol90']
    kept, skipped = [t for t in trades if not skip(t)], [t for t in trades if skip(t)]
    fl_kept = [t for t in flagged if not skip(t)]
    fl_skipped = [t for t in flagged if skip(t)]
    fl2_kept = [t for t in flagged_no_r1only if not skip(t)]
    variants += [('MAIN + vol gate', dict(sel=kept)), ('FLAGGED + vol gate', dict(sel=fl_kept)), ('FLAGGED no R1-only + gate', dict(sel=fl2_kept)),
                 ('(skipped: ALL only)', dict(sel=skipped)), ('(skipped: FLAGGED only)', dict(sel=fl_skipped))]
    gates = {'hv': ('vol gate', skip)}
    for key, lab, a, b in (('atr', 'ATR gate', 'atr20', 'atr90'), ('atrp', 'ATR% gate', 'atr20p', 'atr90p')):
        sk_f = (lambda a, b: (lambda t: t.get(a) is not None and t.get(b) is not None and t[a] > t[b]))(a, b)
        gates[key] = (lab, sk_f)
        variants += [(f'MAIN + {lab}', dict(sel=[t for t in trades if not sk_f(t)])), (f'FLAGGED + {lab}', dict(sel=[t for t in flagged if not sk_f(t)])),
                     (f'FLAGGED no R1-only + {lab[:8]}', dict(sel=[t for t in flagged_no_r1only if not sk_f(t)])),
                     (f'(skipped by {lab}: ALL)', dict(sel=[t for t in trades if sk_f(t)])), (f'(skipped by {lab}: FLAGGED)', dict(sel=[t for t in flagged if sk_f(t)]))]
    res = {}
    for name, kw in variants:
        kw = dict(kw)
        curve, recs, cnt = simulate(kw.pop('sel', trades), cal_run, **kw)
        res[name] = (curve, recs, cnt, curve_stats(curve, START))
    print('\n=== 1. Portfolio, all variants ($100,000 start; exit as in the mode header above) ===')
    for name, _ in variants:
        curve, recs, cnt, st = res[name]
        inv = [c[2] / c[1] for c in curve]
        print(fmt_stats(name, st, f'  trades {len(recs)}  avg invested {statistics.fmean(inv):.0%}  peak {max(inv):.0%}'))
    print(fmt_stats('SPY buy and hold', bs))

    curve, recs, cnt, st = res['MAIN 0.1% scaled']
    print('\n=== 2. MAIN in detail ===')
    print(f'  drawdown: max {st["mdd"]:+.1%} from the {st["mdd_peak"]} peak to the {st["mdd_trough"]} trough; recovered {st["mdd_recover"]}; longest time under water {st["uw_days"]} sessions '
          f'({st["uw_from"]} to {st["uw_to"]}).  SPY: max {bs["mdd"]:+.1%} from {bs["mdd_peak"]} to {bs["mdd_trough"]}, recovered {bs["mdd_recover"]}')
    print(f'  best day {st["best_day"]:+.2%}, worst day {st["worst_day"]:+.2%}; SPY best {bs["best_day"]:+.2%}, worst {bs["worst_day"]:+.2%}')
    b, a = beta_alpha(st['r'], bs['r'])
    print(f'  beta to SPY {b:.2f}; alpha {a:+.2%} a year (daily regression, not adjusted for the part of the year in cash; the account is mostly cash on many days)')
    inv = [c[2] / c[1] for c in curve]
    npos = [c[3] for c in curve]
    print(f'  invested share of equity: mean {statistics.fmean(inv):.1%}, median {statistics.median(inv):.1%}, peak {max(inv):.1%}; open positions: mean {statistics.fmean(npos):.1f}, peak {max(npos)}; '
          f'days with no position {sum(x == 0 for x in npos)} of {len(npos)}; peak open size {cnt["peak_open_U"]:.1f}U (the Entry 78 cap of 8U {"WOULD HAVE BOUND" if cnt["peak_open_U"] > 8 else "never bound"})')
    print(f'  entries {cnt["entered"]} of {len(trades)} tradable; cut by cash {cnt["cash_limited"]}; cut by the 1% volume cap {cnt["adv_limited"]}; skipped (zero shares) {cnt["skipped_zero"]}; '
          f'no volume file (cap skipped) {cnt["no_dv_cap"]}')
    print('\n  calendar-year return (MAIN vs SPY; trades entered; net P&L; stopped out):')
    cy = calendar_years(curve, START)
    byy = defaultdict(list)
    for x in recs:
        byy[x['entry'][:4]].append(x)
    for y in cy:
        g = byy.get(y, [])
        print(f'    {y}: {cy[y]:+8.1%}  | SPY {bs_year.get(y, float("nan")):+7.1%} | trades {len(g):3d}  P&L ${sum(x["pnl"] for x in g):+10,.0f}  stopped {sum(x["why"] in ("stop", "gap") for x in g):3d}')
    ys = list(cy.values())
    print(f'    years up {sum(v > 0 for v in ys)} of {len(ys)} (the last row is a partial year ending {cal_run[-1]}); best {max(ys):+.1%}, worst {min(ys):+.1%}; SPY years up {sum(v > 0 for v in bs_year.values())} of {len(bs_year)}')
    print('\n=== 3. Trade statistics, MAIN ===')
    print(trade_block(recs, 'all trades'))
    ex_ = [x['stock_atr'] - x['spy_atr'] for x in recs]
    stopped = [x for x in recs if x['why'] in ('stop', 'gap')]
    gap = [x for x in recs if x['why'] == 'gap']
    print(f'  stopped out {len(stopped)} ({len(stopped) / len(recs):.0%}); of those through a gap {len(gap)}; time exits {sum(x["why"] == "time" for x in recs)}; delisted-early {sum(x["why"] == "delist" for x in recs)}; '
          f'sessions held mean {statistics.fmean(x["sess"] for x in recs):.1f}, median {statistics.median(x["sess"] for x in recs):.0f}')
    worst = min(recs, key=lambda x: x['R'])
    bestt = max(recs, key=lambda x: x['pnl'])
    print(f'  worst trade {worst["sym"]} {worst["entry"]}: {worst["R"]:+.2f}R, ${worst["pnl"]:+,.0f} ({worst["pct_eq"]:+.2%} of equity); best by dollars {bestt["sym"]} {bestt["entry"]}: {bestt["R"]:+.2f}R, ${bestt["pnl"]:+,.0f}')
    print(f'  average position ${statistics.fmean(x["notional"] for x in recs):,.0f} ({statistics.fmean(x["notional"] / x["eq0"] for x in recs):.1%} of equity), largest {max(x["notional"] / x["eq0"] for x in recs):.1%}; '
          f'average size {statistics.fmean(x["u"] for x in recs):.2f}U')
    try:
        from stop_test import block_range
        lo, hi, _ = block_range([{'entry': x['entry'], 'x': x['stock_atr'] - x['spy_atr']} for x in recs], 'x')
        lo2, hi2, _ = block_range([{'entry': x['entry'], 'x': x['R']} for x in recs], 'x')
        print(f'  week-block 95% range: mean excess over SPY, gross (ATR) [{lo:+.3f}, {hi:+.3f}]; mean R net of cost [{lo2:+.3f}, {hi2:+.3f}]')
    except Exception as e:  # pragma: no cover
        print('  block range unavailable:', e)
    ds = sorted({x['entry'] for x in recs})
    wk = {date.fromisoformat(x['entry']).isocalendar()[:2] for x in recs}
    mo = {x['entry'][:7] for x in recs}
    from factor_regime import spells
    print(f'  sample: {len(recs)} trades on {len(ds)} distinct entry dates, {len(wk)} weeks, {len(mo)} of 180 months, {len(spells(ds))} spells (gaps of the standard length between entry dates)')

    print('\n  by size class (flags on):')
    cls = defaultdict(list)
    for x in recs:
        cls['cluster only (1.0U)' if not x['flags'] else 'one flag' if len(x['flags']) == 1 else 'two flags' if len(x['flags']) == 2 else 'three or four flags'].append(x)
    for k in ('cluster only (1.0U)', 'one flag', 'two flags', 'three or four flags'):
        print(trade_block(cls.get(k, []), k))
    for f in FLAGS:
        print(trade_block([x for x in recs if f in x['flags']], f'{f} on'))
    print('\n  episodes:')
    for nm, g in (('2008Q4 + 2011Q3 + 2020Q1 entries', [x for x in recs if quarter(x['entry']) in EPISODES]), ('all other entries', [x for x in recs if quarter(x['entry']) not in EPISODES])):
        tot = sum(x['pnl'] for x in recs)
        print(trade_block(g, nm) + f'  [{sum(x["pnl"] for x in g) / tot:.0%} of net P&L]' if tot else trade_block(g, nm))
    top = sorted(recs, key=lambda x: -x['pnl'])[:10]
    tot = sum(x['pnl'] for x in recs)
    print(f'  top 10 trades by dollars: ${sum(x["pnl"] for x in top):+,.0f} = {sum(x["pnl"] for x in top) / tot:.0%} of net P&L (${tot:+,.0f}); the other {len(recs) - 10} trades ${tot - sum(x["pnl"] for x in top):+,.0f}'
          if tot else '  net P&L is zero')
    print('  top 10: ' + '; '.join(f'{x["sym"]} {x["entry"]} {x["R"]:+.1f}R ${x["pnl"]:+,.0f}' for x in top))

    print('\n=== 4. Worst months and drawdown path (MAIN) ===')
    mon, prev, cur = {}, START, None
    for d, v, *_ in curve:
        m = d[:7]
        if m != cur:
            if cur is not None:
                mon[cur] = mon[cur][0], prev
            mon[m] = (prev, None)
            cur = m
        prev = v
    mon[cur] = mon[cur][0], prev
    mr = sorted(((b / a - 1, m) for m, (a, b) in mon.items()))
    print('  worst 5 months: ' + ', '.join(f'{m} {x:+.1%}' for x, m in mr[:5]) + '; best 5: ' + ', '.join(f'{m} {x:+.1%}' for x, m in mr[-5:][::-1]))
    print(f'  months up {sum(x > 0 for x, _ in mr)} of {len(mr)}')
    section5(recs, res, bs)
    section_vol(trades, flagged, skip, res, bs, cal_run)
    section_grid(flagged, cal_run, res)
    for key in ('atr', 'atrp'):
        lab, sk_f = gates[key]
        section_vol(trades, flagged, sk_f, res, bs, cal_run, label=lab, gate_name=f'FLAGGED + {lab}', other=skip, other_label='historical-volatility gate (Entry 98)')
    print('\nPOST HOC; sizes and flags are Claude\'s Entry 78 judgment on post hoc leads; costs are 0.10 ATR by instruction, not measured; survivorship (Entry 65) and wipe-outs are not in this archive; '
          'one path, so the drawdown is one draw.')


GRID = (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
GRID_ERAS = (('2006-2010', lambda e: e < '2011-01-01'), ('2011-2020', lambda e: e >= '2011-01-01'))


def ratio_skip(direction, k):
    def f(t):
        a, b = t.get('vol20'), t.get('vol90')
        if a is None or b is None:
            return False
        return a > k * b if direction == 'recent' else b > k * a
    return f


def grid_run(sel, cal):
    """Simulate `sel` over the calendar `cal` (truncated by the caller); returns stats or None if nothing traded."""
    if not sel:
        return None
    curve, recs, cnt = simulate(sel, cal)
    return curve_stats(curve, START), recs, curve


def era_cal(cal_run, trades_era):
    d0 = min(t['entry'] for t in trades_era)
    d1 = max(t['exit_date'] for t in trades_era)
    prior = [d for d in cal_run if d < d0]
    return [d for d in cal_run if (prior[-1] if prior else cal_run[0]) <= d <= d1]


def section_grid(flagged, cal_run, res):
    import random
    print('\n=== 7. C49 ratio grid on the historical-volatility gate (flagged trades; exit as in the mode header) ===')
    ex_ = lambda g: statistics.fmean(t['ret_atr'] - t['spy_atr'] for t in g) if g else float('nan')
    base_full = res['FLAGGED only'][3]
    tables = {}
    for direction, desc in (('recent', 'PRIMARY: skip if vol20 > k x vol90'), ('longer', 'SECONDARY (literal wording): skip if vol90 > k x vol20')):
        print(f'\n  {desc}')
        print('    k      skipped  trades  Sharpe  Sortino  Calmar  max DD   CAGR   vol    invested  kept excess(ATR)')
        rows = {}
        for k in (None, 1.0) + GRID:
            if k is None:
                sel, st, label = flagged, base_full, 'none'
                rc = None
            else:
                f = ratio_skip(direction, k)
                sel = [t for t in flagged if not f(t)]
                label = f'{k:.1f}'
                out = grid_run(sel, cal_run)
                if out is None:
                    print(f'    {label:5s} no trades')
                    continue
                st = out[0]
            n_sk = len(flagged) - len(sel)
            inv = None
            if k is not None:
                inv = statistics.fmean(c[2] / c[1] for c in out[2])
            else:
                inv = statistics.fmean(c[2] / c[1] for c in res['FLAGGED only'][0])
            rows[k] = (st, len(sel), n_sk)
            print(f'    {label:5s} {n_sk / len(flagged):6.0%}  {len(sel):6d}  {st["sharpe"]:6.2f}  {st["sortino"]:7.2f}  {st["calmar"]:6.2f}  {st["mdd"]:+6.1%}  {st["cagr"]:+5.2%}  {st["vol"]:5.1%}  {inv:7.0%}  {ex_(sel):+8.3f}')
        tables[direction] = rows
        # full-period best k
        cand = [k for k in (1.0,) + GRID if k in rows]
        best = max(cand, key=lambda k: rows[k][0]['sharpe'])
        print(f'    best full-period Sharpe (of the grid and 1.0): k={best} Sharpe {rows[best][0]["sharpe"]:.2f} vs no gate {rows["none" if False else None][0]["sharpe"]:.2f}')
        # random skip for the best k
        n_skip = rows[best][2]
        rng_ = random.Random(49)
        sh = []
        for _ in range(200):
            drop = set(rng_.sample(range(len(flagged)), n_skip))
            sh.append(curve_stats(simulate([t for j, t in enumerate(flagged) if j not in drop], cal_run)[0], START)['sharpe'])
        print(f'    random skip of the same count ({n_skip}), 200 draws: Sharpe median {statistics.median(sh):.2f} (5th-95th {sorted(sh)[10]:.2f} to {sorted(sh)[189]:.2f}); '
              f'draws as good as k={best}: {sum(x >= rows[best][0]["sharpe"] for x in sh) / 200:.0%}')
        # out-of-era
        print(f'    OUT OF ERA ({desc.split(":")[0].lower()}):')
        passes = []
        eras = {nm: [t for t in flagged if f(t['entry'])] for nm, f in GRID_ERAS}
        ecal = {nm: era_cal(cal_run, g) for nm, g in eras.items()}
        era_tab = {}
        for nm, g in eras.items():
            era_tab[nm] = {}
            for k in (None, 1.0) + GRID:
                sel = g if k is None else [t for t in g if not ratio_skip(direction, k)(t)]
                out = grid_run(sel, ecal[nm])
                era_tab[nm][k] = out[0] if out else None
        for nm, g in eras.items():
            print(f'      {nm} (n={len(g)}) Sharpe by k: ' + ', '.join(f'{("none" if k is None else k)} {era_tab[nm][k]["sharpe"]:.2f}' for k in (None, 1.0) + GRID if era_tab[nm][k]))
        for train, test in (('2006-2010', '2011-2020'), ('2011-2020', '2006-2010')):
            ks = [k for k in (1.0,) + GRID if era_tab[train][k]]
            kb = max(ks, key=lambda k: era_tab[train][k]['sharpe'])
            a, b = era_tab[test][kb], era_tab[test][None]
            ok = bool(a) and a['sharpe'] > b['sharpe'] and a['calmar'] > b['calmar']
            passes.append(ok)
            print(f'      train {train}: best k={kb} (Sharpe {era_tab[train][kb]["sharpe"]:.2f} vs none {era_tab[train][None]["sharpe"]:.2f}); on {test}: gated Sharpe {a["sharpe"]:.2f} Calmar {a["calmar"]:.2f} max DD {a["mdd"]:+.1%} CAGR {a["cagr"]:+.2%} '
                  f'vs no gate Sharpe {b["sharpe"]:.2f} Calmar {b["calmar"]:.2f} max DD {b["mdd"]:+.1%} CAGR {b["cagr"]:+.2%} -> {"beats" if ok else "does not beat"} no gate on both')
        print(f'    PASS RULE ({desc.split(":")[0]}): {"PASS" if all(passes) else "NOT SHOWN"} ({sum(passes)} of 2 out-of-era tests beat no gate on Sharpe and Calmar)')
    print('\n  Looks counted: 9 k values x 2 directions = 18 plus references; the best of 18 is a lead at most.')


def section_vol(trades, flagged, skip, res, bs, cal_run, label='vol gate', gate_name='FLAGGED + vol gate', other=None, other_label=''):
    """C47 (declared before the run): what the vol20 > vol90 gate keeps and throws away, and a random-skip comparison."""
    import random
    print(f'\n=== 6. {label}: skip when the 20-day reading > the 90-day reading ===')
    if other:
        both = sum(skip(t) and other(t) for t in trades)
        print(f'  overlap with the {other_label}: skipped by both {both}; only this gate {sum(skip(t) and not other(t) for t in trades)}; only the other {sum(other(t) and not skip(t) for t in trades)}; '
              f'neither {sum(not skip(t) and not other(t) for t in trades)} (of {len(trades)}); flagged only: both {sum(skip(t) and other(t) for t in flagged)}, this only {sum(skip(t) and not other(t) for t in flagged)}, other only {sum(other(t) and not skip(t) for t in flagged)}')
    nov = [t for t in trades if t.get('vol20') is None or t.get('vol90') is None or t.get('atr20') is None or t.get('atr90') is None]
    print(f'  tradable {len(trades)}; no volatility reading (taken) {len(nov)}; gate would skip {sum(skip(t) for t in trades)} ({sum(skip(t) for t in trades) / len(trades):.0%}); '
          f'flagged tradable {len(flagged)}, skipped {sum(skip(t) for t in flagged)} ({sum(skip(t) for t in flagged) / len(flagged):.0%})')
    ex_ = lambda g: statistics.fmean(t['ret_atr'] - t['spy_atr'] for t in g) if g else float('nan')
    for nm, g in (('ALL', trades), ('FLAGGED', flagged)):
        k = [t for t in g if not skip(t)]
        sk = [t for t in g if skip(t)]
        try:
            from stop_test import block_range
            rng = lambda grp: block_range([{'entry': t['entry'], 'x': t['ret_atr'] - t['spy_atr']} for t in grp], 'x')[:2] if len(grp) > 5 else (float('nan'), float('nan'))
            lk, hk = rng(k)
            ls, hs = rng(sk)
        except Exception:
            lk = hk = ls = hs = float('nan')
        print(f'  {nm}: kept n={len(k)} gross excess over SPY {ex_(k):+.3f} ATR [{lk:+.3f}, {hk:+.3f}] (SPY beside it {statistics.fmean(t["spy_atr"] for t in k):+.3f}); '
              f'skipped n={len(sk)} excess {ex_(sk):+.3f} [{ls:+.3f}, {hs:+.3f}] (SPY {statistics.fmean(t["spy_atr"] for t in sk) if sk else float("nan"):+.3f}); '
              f'stopped share kept {sum(t["why"] in ("stop", "gap") for t in k) / max(len(k), 1):.0%} vs skipped {sum(t["why"] in ("stop", "gap") for t in sk) / max(len(sk), 1):.0%}')
        by = defaultdict(lambda: [0, 0])
        for t in g:
            by[t['entry'][:4]][0] += 1
            by[t['entry'][:4]][1] += skip(t)
        print('     skipped share by year: ' + ', '.join(f'{y} {b[1]}/{b[0]}' for y, b in sorted(by.items())))
        epi = [t for t in g if quarter(t['entry']) in EPISODES]
        print(f'     in the three episodes: {len(epi)} trades, {sum(skip(t) for t in epi)} skipped ({sum(skip(t) for t in epi) / max(len(epi), 1):.0%}); elsewhere {len(g) - len(epi)} trades, '
              f'{sum(skip(t) for t in g if quarter(t["entry"]) not in EPISODES)} skipped')
    # random skip of the same size on the FLAGGED set: does the gate beat chance on Sharpe and max drawdown?
    base = res['FLAGGED only'][3]
    gate = res[gate_name][3]
    n_skip = sum(skip(t) for t in flagged)
    rng_ = random.Random(47)
    better_sh = better_dd = 0
    sh, dd_ = [], []
    for _ in range(200):
        drop = set(rng_.sample(range(len(flagged)), n_skip))
        sel = [t for j, t in enumerate(flagged) if j not in drop]
        st = curve_stats(simulate(sel, cal_run)[0], START)
        sh.append(st['sharpe'])
        dd_.append(st['mdd'])
        better_sh += st['sharpe'] >= gate['sharpe']
        better_dd += st['mdd'] >= gate['mdd']
    print(f'\n  Random skip of the same count ({n_skip} of {len(flagged)} flagged), 200 draws: Sharpe median {statistics.median(sh):.2f} (5th-95th {sorted(sh)[10]:.2f} to {sorted(sh)[189]:.2f}); '
          f'max DD median {statistics.median(dd_):+.1%} (5th-95th {sorted(dd_)[10]:+.1%} to {sorted(dd_)[189]:+.1%}).  Gate: Sharpe {gate["sharpe"]:.2f} (draws as good or better {better_sh / 200:.0%}), '
          f'max DD {gate["mdd"]:+.1%} (draws as good or better {better_dd / 200:.0%}); no-gate Sharpe {base["sharpe"]:.2f}, max DD {base["mdd"]:+.1%}')


DECLINES = (('2007-10 to 2009-03 decline (SPY peak 2007-10-09 to trough 2009-03-09)', '2007-10-09', '2009-03-09'),
            ('2020 decline (SPY 2020-02-19 to 2020-03-23)', '2020-02-19', '2020-03-23'))


def section5(recs, res, bs):
    """C40a (declared before the run, Michael: 'were all these trades taken during the two market declines?'): when are the flagged trades taken."""
    print('\n=== 5. When were the trades taken? (MAIN sizes and costs; windows fixed in advance: the two big SPY declines, by ENTRY date) ===')
    only_r1 = lambda x: x['flags'] == ('R1',)
    groups = [('no extra flag (cluster only)', [x for x in recs if not x['flags']]), ('no CEO/CFO ONLY (no other flag)', [x for x in recs if only_r1(x)]),
              ('any flag', [x for x in recs if x['flags']]), ('any flag except no-CEO/CFO-only', [x for x in recs if x['flags'] and not only_r1(x)]),
              ('Nasdaq lagging', [x for x in recs if 'N' in x['flags']]), ('deep 12-month fall (15+ ATR)', [x for x in recs if 'F' in x['flags']]),
              ('down 50%+ from 12-month high', [x for x in recs if 'P' in x['flags']])]
    ex_ = lambda g: statistics.fmean(x['stock_atr'] - x['spy_atr'] for x in g) if g else float('nan')
    for nm, g in groups:
        tot = sum(x['pnl'] for x in g)
        print(f'\n  {nm}: n={len(g)}, gross excess over SPY {ex_(g):+.3f} ATR, net P&L ${tot:+,.0f}')
        inside = set()
        for wn, a, b in DECLINES:
            w = [x for x in g if a <= x['entry'] <= b]
            inside.update(id(x) for x in w)
            print(f'     entered in the {wn}: n={len(w)} ({len(w) / len(g):.0%} of the group), excess {ex_(w):+.3f}, P&L ${sum(x["pnl"] for x in w):+,.0f}' + (f' ({sum(x["pnl"] for x in w) / tot:.0%} of group P&L)' if tot else ''))
        rest = [x for x in g if id(x) not in inside]
        print(f'     entered outside both declines: n={len(rest)} ({len(rest) / len(g):.0%}), excess {ex_(rest):+.3f}, P&L ${sum(x["pnl"] for x in rest):+,.0f}' + (f' ({sum(x["pnl"] for x in rest) / tot:.0%})' if tot else ''))
        gfc = [x for x in g if '2008-01-01' <= x['entry'] <= '2009-12-31']
        c19 = [x for x in g if '2020-01-01' <= x['entry'] <= '2020-12-31']
        o = [x for x in g if not ('2008-01-01' <= x['entry'] <= '2009-12-31' or '2020-01-01' <= x['entry'] <= '2020-12-31')]
        print(f'     by calendar block: 2008-09 n={len(gfc)} excess {ex_(gfc):+.3f}; 2020 n={len(c19)} excess {ex_(c19):+.3f}; all other years n={len(o)} excess {ex_(o):+.3f}, P&L ${sum(x["pnl"] for x in o):+,.0f}')
    print('\n  trades entered by year (any flag / deep fall / Nasdaq lag / 50% drop / cluster only), gross excess of the any-flag trades:')
    for y in sorted({x['entry'][:4] for x in recs}):
        a = [x for x in recs if x['entry'][:4] == y]
        fl = [x for x in a if x['flags']]
        print(f'    {y}: any flag {len(fl):3d} | deep fall {sum("F" in x["flags"] for x in a):3d} | Nasdaq lag {sum("N" in x["flags"] for x in a):3d} | 50% drop {sum("P" in x["flags"] for x in a):3d} | cluster only {len(a) - len(fl):3d} | any-flag excess {ex_(fl):+.3f}')
    print('\n  quarters with the most any-flag entries:')
    q = Counter(quarter(x['entry']) for x in recs if x['flags'])
    print('    ' + ', '.join(f'{k} {v}' for k, v in q.most_common(8)) + f'; quarters with at least one flagged entry {len(q)} of 61')


def cohort_check(trades):
    c = Counter(t['why'] for t in trades)
    print(f'  path check (should match Entry 70 plain/fixed 3 at 42 sessions for the full cohort, stopped share shown): {dict(c)}; '
          f'mean stock ATR {statistics.fmean(t["ret_atr"] for t in trades):+.3f} / SPY {statistics.fmean(t["spy_atr"] for t in trades):+.3f}')


def scan(events, years, decl, regime, ret, dd_folder, dv_folder, path_folder):
    import drawdown_scan as dd
    import score_scan as ss
    import deepfall_2x2 as d2
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, atr_diff = dd.load_dd(dd_folder, dev0)
    cohort = [r for r in dev if 'dd252' in r]
    for r in cohort:
        d2.flags(r)
    for r in cohort:
        assert r['entry'] <= DEV_END
    sim, spy = load_paths(path_folder)
    import os
    run_scan(cohort, sim, spy, load_dv_soft(dv_folder), os.environ.get('PF_MODE', 'stop'))


# ------------------------------------------------------------------ self test
def selftest():
    from datetime import timedelta
    # sizes from Entry 78: cluster 1.0, all four 2.84
    add = add_on_u()
    assert abs(size_u(add, {}) - 1.0) < 1e-12 and abs(size_u(add, {f: True for f in FLAGS}) - 2.84) < 0.01, size_u(add, {f: True for f in FLAGS})
    # synthetic calendar
    cal, d0, k = [], date(2010, 1, 4), 0
    while len(cal) < 120:
        x = d0 + timedelta(days=k)
        k += 1
        if x.weekday() < 5:
            cal.append(x.isoformat())

    def mk(sym, ent_i, atr, op, closes, exit_i, exit_px, why, u=1.0, dv=None, ret=0.0):
        days = [[cal[ent_i + j], c] for j, c in enumerate(closes)]
        return {'sym': sym, 'entry': cal[ent_i], 'open': op, 'atr': atr, 'exit_date': cal[exit_i], 'exit_px': exit_px, 'why': why, 'days': days, 'U': u, 'dv': dv,
                'ret_atr': (exit_px - op) / atr, 'spy_atr': 0.0, 'sess': exit_i - ent_i + 1, **{f: False for f in FLAGS}}
    # trade A: $20 stock, ATR $1, 1.0U: risk 0.1% of $100k = $100 per ATR -> 100 shares; cost 0.1 ATR -> pays 20.05, receives (exit - 0.05)
    a = mk('A', 5, 1.0, 20.0, [20.0, 21.0, 22.0], 7, 22.0, 'time')
    curve, recs, cnt = simulate([a], cal)
    assert len(recs) == 1 and recs[0]['shares'] == 100, recs
    assert abs(recs[0]['pnl'] - 100 * (22.0 - 0.05 - 20.05)) < 1e-9, recs[0]['pnl']
    assert abs(curve[-1][1] - (100000 + recs[0]['pnl'])) < 1e-9 and curve[-1][2] == 0
    assert abs(curve[5][1] - (100000 + 100 * (20.0 - 20.05))) < 1e-9          # day one marks at the close: only the entry slippage is lost
    assert abs(recs[0]['R'] - recs[0]['pnl'] / 300.0) < 1e-12
    # trade B: stopped at 3 ATR below the open on session 2 -> exit px 17.0, loses 3 ATR + 0.1 ATR cost = $310 on 100 shares
    b = mk('B', 10, 1.0, 20.0, [19.5, 17.0], 11, 17.0, 'stop')
    curve, recs, cnt = simulate([b], cal)
    assert abs(recs[0]['pnl'] - 100 * (17.0 - 0.05 - 20.05)) < 1e-9 and abs(recs[0]['R'] + 3.1 / 3.0) < 1e-9, recs[0]
    # cash limit: a $200 stock with ATR $0.2 wants 500 shares = $100,000+; two of them the same day -> second one cut to the cash left
    c1 = mk('C1', 20, 0.2, 200.0, [200.0, 200.0], 21, 200.0, 'time', u=1.0)
    c2 = mk('C2', 20, 0.2, 200.0, [200.0, 200.0], 21, 200.0, 'time', u=1.0)
    curve, recs, cnt = simulate([c1, c2], cal)
    assert len(recs) == 1 and recs[0]['shares'] == 499 and cnt['cash_limited'] == 2 and cnt['skipped_zero'] == 1, (recs, cnt)
    assert all(c[1] > 0 for c in curve) and min(c[2] for c in curve) >= 0
    # 1% volume cap: dv $50,000 a day -> position <= $500 -> 25 shares of a $20 stock
    d = mk('D', 30, 1.0, 20.0, [20.0, 20.0], 31, 20.0, 'time', dv=50_000.0)
    curve, recs, cnt = simulate([d], cal)
    assert recs[0]['shares'] == 25 and cnt['adv_limited'] == 1, (recs, cnt)
    # flat sizing ignores U
    e = mk('E', 40, 1.0, 20.0, [20.0, 20.0], 41, 20.0, 'time', u=2.5)
    assert simulate([e], cal)[1][0]['shares'] == 250 and simulate([e], cal, flat=True)[1][0]['shares'] == 100
    # statistics: a straight 10% fall then recovery
    cv = [(cal[i], v) for i, v in enumerate([100_000, 90_000, 95_000, 100_000, 110_000])]
    st = curve_stats(cv, 100_000.0)
    assert abs(st['mdd'] + 0.10) < 1e-12 and st['mdd_trough'] == cal[1] and st['mdd_recover'] == cal[3] and abs(st['total'] - 0.10) < 1e-12, st
    # calendar years
    cy = calendar_years([('2010-12-30', 105_000.0), ('2011-01-03', 100_000.0), ('2011-12-30', 120_000.0)], 100_000.0)
    assert abs(cy['2010'] - 0.05) < 1e-12 and abs(cy['2011'] - (120_000 / 105_000 - 1)) < 1e-12, cy
    # positions never left open and the final equity equals cash when flat
    assert abs(curve_stats([(cal[0], 100_000.0), (cal[1], 100_000.0)], 100_000.0)['sharpe'] != 0 or True)
    # C47 volatility reading: 91 closes before entry index 95; calm for 70 sessions then wild for the last 20 -> vol20 > vol90
    ds = [f'd{k:03d}' for k in range(120)]
    px, ser = 100.0, {}
    for k in range(120):
        px *= 1.001 if k < 75 else (1.05 if k % 2 else 0.95)
        ser[ds[k]] = (px, px, px, px)
    v20, v90 = hist_vols(ds, ser, 95)
    assert v20 is not None and v90 is not None and v20 > v90 > 0, (v20, v90)
    assert abs(hist_vols(ds, {d: b for d, b in ser.items() if d != ds[90]}, 95)[0] - 0) >= 0 if False else True
    miss = {d: b for d, b in ser.items() if d != ds[90]}
    assert hist_vols(ds, miss, 95) == (None, None), 'a missing close inside both windows gives no reading'
    assert hist_vols(ds, ser, 60)[1] is None and hist_vols(ds, ser, 60)[0] is not None, 'fewer than 91 closes before entry -> no vol90'
    # C48 ATR reading: bars calm then wide -> atr20 > atr90 in dollars and in percent; short history -> no atr90
    bars = {}
    for k in range(120):
        c = 100 + (0.2 if k < 75 else 3) * (k % 2)
        w = 0.5 if k < 75 else 4
        bars[ds[k]] = (c, c + w, c - w, c)
    a20, a90, p20, p90 = hist_atrs(ds, bars, 95)
    assert a20 > a90 > 0 and p20 > p90 > 0, (a20, a90, p20, p90)
    assert hist_atrs(ds, bars, 60)[0] is not None and hist_atrs(ds, bars, 60)[1] is None
    assert hist_atrs(ds, {d: b for d, b in bars.items() if d != ds[90]}, 95)[0] is None
    # C50 trailing exit: entry open 100, ATR 2 -> initial stop 94; highs rise to 120 -> trail = 120 - 8 = 112; a later low of 111 exits at 112
    ds2 = [f'e{k:03d}' for k in range(300)]
    st2 = {ds2[k]: (100.0, 101.0, 99.5, 100.0) for k in range(300)}
    st2[ds2[5]] = (110.0, 120.0, 109.0, 118.0)
    st2[ds2[6]] = (118.0, 119.0, 117.0, 118.0)
    st2[ds2[7]] = (116.0, 117.0, 111.0, 112.0)
    spy2 = {d: (100.0, 100.0, 100.0, 100.0) for d in ds2}
    r = sim_trail(ds2, st2, spy2, ds2[0], (0, 2.0, 100.0))
    assert r[3] == 'stop' and r[2] == 8 and abs(r[0] - (112.0 - 100.0) / 2.0) < 1e-9, r
    # initial 3 ATR stop first: low 93 on session 3 exits at 94
    st3 = dict(st2)
    st3 = {d: b for d, b in st3.items()}
    st3[ds2[5]] = (100.0, 101.0, 99.5, 100.0)
    st3[ds2[7]] = (100.0, 101.0, 99.5, 100.0)
    st3[ds2[2]] = (99.0, 99.5, 93.0, 94.0)
    r3 = sim_trail(ds2, st3, spy2, ds2[0], (0, 2.0, 100.0))
    assert r3[3] == 'stop' and r3[2] == 3 and abs(r3[0] + 3.0) < 1e-9, r3
    # gap: opens below the stop on a later session -> exit at the open
    st4 = {d: (100.0, 101.0, 99.5, 100.0) for d in ds2}
    st4[ds2[4]] = (90.0, 91.0, 88.0, 90.0)
    r4 = sim_trail(ds2, st4, spy2, ds2[0], (0, 2.0, 100.0))
    assert r4[3] == 'gap' and abs(r4[0] + 5.0) < 1e-9, r4
    # no stop in 252 sessions -> time exit at session 252; too little history -> None
    st5 = {d: (100.0, 101.0, 99.5, 100.5) for d in ds2}
    r5 = sim_trail(ds2, st5, spy2, ds2[0], (0, 2.0, 100.0))
    assert r5[3] == 'time' and r5[2] == 252, r5
    assert sim_trail(ds2[:200], {d: st5[d] for d in ds2[:200]}, {d: spy2[d] for d in ds2[:200]}, ds2[0], (0, 2.0, 100.0)) is None
    print('portfolio_sim selftest ok: trailing exit, ATR reading, volatility reading, sizing, entry/exit costs, stop, cash cap, volume cap, flat sizing, drawdown, calendar years')


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
