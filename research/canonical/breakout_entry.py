"""C32 (declared 9 Nov 2026, BEFORE any run).  ENTRY TIMING: wait for a 10-session high after the signal, instead of buying at the next open.
Michael: "after the fourth person buys, wait to buy on a ten day high stop" (the signal is unchanged: the filing that brings the count to four distinct buyers).

RULE TESTED.  Signal and baseline entry session i exactly as Entries 28 and 62 (the next regular open after the qualifying filing).  Buy-stop price
L = highest HIGH of the 10 completed sessions before session i (sessions i-10 to i-1).  The buy-stop is live from session i for W sessions (W = 5, 10, 20;
declared menu; sessions i to i+W-1).  First session k in that window whose high is above L is the fill: filled at L, or at that session's open if the open is already >= L
(a gap).  If nothing fills inside W sessions the signal is skipped (no trade, cash).  Hold H = 21 or 42 sessions counted from the fill session (fill session =
day one), exit at that session's close, no stop; a series that ends early is closed at its last close ('delist').  Stock return in ATR uses the ATR of the signal
(Entry 62 convention, ATR of the 20 sessions before session i) so numbers compare with every earlier table; SPY leg = SPY return from the open of the fill session
to the close of the exit session, scaled by fill price / ATR (same window, same units).  Gross of cost: a breakout fill in a thin name will slip more than the
model, so every number here flatters the breakout arm a little.

COMPARATORS (same trades, same hold H, from session i): (a) baseline excess of the trades that DID fill; (b) baseline excess of the trades that did NOT fill
(did the wait skip the winners?); (c) baseline of all signals.  Per signal, with unfilled counted as zero (cash), excess over SPY: breakout arm vs baseline.
Also: fill rate, mean wait in sessions, share filled by gap, mean distance of L above the entry open in ATR.  Groups: the deep-fall rule (down 15+ ATR over
12 months), its score subset (SF2), ALL, and everything outside the deep-fall rule; eras 2006-10 and 2011-20; week-block 95% range of (breakout minus
baseline) on the filled trades.  3 waits x 2 holds = 6 cells per group; best-of-menu is optimistic and the cells are POST HOC (the deep-fall rule was chosen
after Entries 36-67).  Development entries only (D-068).  No cost is applied.

Usage:  python breakout_entry.py year YEAR --primary FILE --out FILE
        python breakout_entry.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER SIM_FOLDER
        python breakout_entry.py --selftest
"""
import argparse, json, math, statistics, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import excursion_stops as ex
import score_scan as ss
import cost_stops_f as cf
from refined_baseline import DEV_END, assert_allowed
from stop_test import block_range

LOOK = 10
WAITS = (5, 10, 20)
HOLDS = (21, 42)
F_CUT = -15.0


def sim_breakout(dates, stock, spy, ctx, W, H):
    """Returns None (cannot be evaluated), {'filled': False}, or {'filled': True, ...}."""
    i, atr, op = ctx
    prior = [stock[d][1] for d in dates[max(0, i - LOOK):i] if d in stock]
    if len(prior) < LOOK // 2:
        return None
    level = max(prior)
    fill = None
    for k in range(i, min(i + W, len(dates))):
        d = dates[k]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        if h > level:
            fill = (k, o if o >= level else level, o >= level)
            break
    if fill is None:
        if i + W - 1 >= len(dates):
            return None
        return {'filled': False, 'dist': round((level - op) / atr, 4)}
    k, px, gap = fill
    j = k + H - 1
    if j >= len(dates):
        return None
    kk = next((x for x in range(j, k - 1, -1) if dates[x] in stock), None)
    if kk is None:
        return None
    ed, fd = dates[kk], dates[k]
    if ed not in spy or fd not in spy:
        return None
    exit_px = stock[ed][3]
    return {'filled': True, 'stock': round((exit_px - px) / atr, 4), 'spy': round((spy[ed][3] / spy[fd][0] - 1) * px / atr, 4),
            'wait': k - i, 'gap': bool(gap), 'why': 'time' if kk == j else 'delist', 'dist': round((level - op) / atr, 4)}


def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C32 is development years only'
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year - 1, year, year + 1, year + 2], want, 25, 30)
        spy_bars, _ = load_span(s3, 'etf', [year - 1, year, year + 1, year + 2], {'SPY'}, 25, 30)
        spy = spy_bars.get('SPY', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}')
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
            base = cf.sim_stop(dates, series, spy, e['entry'], ctx, 'none', 0)
            r.update({'status': 'ok', 'atr': ctx[1], 'open': ctx[2], 'base': {str(H): base.get(H) for H in HOLDS},
                      'bo': {str(W): {str(H): sim_breakout(dates, series, spy, ctx, W, H) for H in HOLDS} for W in WAITS}})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: status {dict(Counter(r["status"] for r in rows))}')


def mean(xs):
    xs = list(xs)
    return statistics.fmean(xs) if xs else float('nan')


def load_join(folder, dev):
    sim = {}
    for p in sorted(Path(folder).glob('bo_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            sim[(r['cik'], r['sym'], r['entry'])] = r
    out, miss = [], 0
    for r in dev:
        s = sim.get((r['cik'], r['sym'], r['entry']))
        if s is None or s.get('status') != 'ok':
            miss += 1
            continue
        out.append({**r, 'atr': s['atr'], 'open': s['open'], 'base': s['base'], 'bo': s['bo']})
    print(f'cohort {len(dev)}; with paths {len(out)}; missing {miss}')
    return out


def group_table(name, rows):
    print(f'\n=== {name} (signals n={len(rows)}); excess = stock ATR minus SPY ATR over the same window; gross of cost ===')
    for H in HOLDS:
        base_all = [(r, r['base'][str(H)]) for r in rows if r['base'].get(str(H))]
        b_all = mean(c[0] - c[1] for _, c in base_all)
        print(f'  hold {H} sessions: baseline (next open) n={len(base_all)} excess {b_all:+.3f}  [stock {mean(c[0] for _, c in base_all):+.3f} / SPY {mean(c[1] for _, c in base_all):+.3f}]')
        for W in WAITS:
            ok, fl, nf = [], [], []
            for r in rows:
                b = r['base'].get(str(H))
                o = r['bo'][str(W)].get(str(H))
                if b is None or o is None:
                    continue
                ok.append((r, b, o))
            fl = [(r, b, o) for r, b, o in ok if o['filled']]
            nf = [(r, b, o) for r, b, o in ok if not o['filled']]
            if not ok:
                continue
            ne = mean(o['stock'] - o['spy'] for _, _, o in fl)
            be_f = mean(b[0] - b[1] for _, b, _ in fl)
            be_n = mean(b[0] - b[1] for _, b, _ in nf)
            per_sig_new = sum(o['stock'] - o['spy'] for _, _, o in fl) / len(ok)
            per_sig_base = mean(b[0] - b[1] for _, b, _ in ok)
            line = (f'    wait {W:2d}: evaluable {len(ok)}, filled {len(fl)} ({len(fl) / len(ok):.0%}); breakout excess on filled {ne:+.3f} '
                    f'[stock {mean(o["stock"] for _, _, o in fl):+.3f} / SPY {mean(o["spy"] for _, _, o in fl):+.3f}] vs baseline on the same trades {be_f:+.3f} '
                    f'(difference {ne - be_f:+.3f}); baseline of the UNFILLED {be_n:+.3f} (n={len(nf)}); per signal with unfilled = cash: breakout {per_sig_new:+.3f} vs baseline {per_sig_base:+.3f}; '
                    f'mean wait {mean(o["wait"] for _, _, o in fl):.1f} sessions, gap fills {mean(o["gap"] for _, _, o in fl):.0%}, level above entry open {mean(o["dist"] for _, _, o in fl):+.2f} ATR')
            print(line)
            if len(fl) >= 20:
                lo, hi, _ = block_range([{'entry': r['entry'], 'x': (o['stock'] - o['spy']) - (b[0] - b[1])} for r, b, o in fl], 'x')
                print(f'             week-block 95% range of (breakout minus baseline) on the filled trades: [{lo:+.3f}, {hi:+.3f}]')
            for nm, f in (('2006-10', lambda r: r['entry'] < '2011-01-01'), ('2011-20', lambda r: r['entry'] >= '2011-01-01')):
                s = [(r, b, o) for r, b, o in fl if f(r)]
                t = [(r, b, o) for r, b, o in ok if f(r)]
                if s:
                    print(f'             {nm}: filled {len(s)}/{len(t)}, breakout {mean(o["stock"] - o["spy"] for _, _, o in s):+.3f} vs baseline same trades {mean(b[0] - b[1] for _, b, _ in s):+.3f}')


def scan(events, years, decl, regime, ret, sim_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    rows = load_join(sim_folder, dev0)
    for r in rows:
        r['F'] = r['raw252'] <= F_CUT
        r['SF2'] = (int(r['R1']) + int(r['N']) + int(r['F'])) >= 2
    F = [r for r in rows if r['F']]
    print(f'groups: ALL {len(rows)}, deep-fall {len(F)}, score subset {sum(r["SF2"] for r in rows)}')
    print('\n=== Reproduction: deep-fall baseline excess must equal Entry 69/70: plain 21 +0.599 (stock +0.817 / SPY +0.218), plain 42 +1.123 (+1.559 / +0.435) ===')
    group_table('Deep-fall rule (down 15+ ATR over 12 months)', F)
    group_table('Score subset (SF2)', [r for r in rows if r['SF2']])
    group_table('ALL signals', rows)
    group_table('Outside the deep-fall rule', [r for r in rows if not r['F']])
    print('\nPOST HOC; gross of cost; breakout fills in thin names will slip more than a model; 6 cells per group, best-of-menu optimistic.')


def selftest():
    dates = [f'2020-01-{d:02d}' for d in range(1, 29)]
    bar = lambda o, h, l, c: (o, h, l, c)
    stock = {d: bar(10, 10.5, 9.5, 10) for d in dates}
    spy = {d: bar(100, 101, 99, 100) for d in dates}
    ctx = (14, 1.0, 10.0)
    # prior 10 highs = 10.5 -> level 10.5; session 16 trades up to 11 with open 10 -> fill at 10.5
    stock[dates[16]] = bar(10, 11, 9.9, 10.8)
    stock[dates[26]] = bar(12, 12.5, 11.5, 12)
    o = sim_breakout(dates, stock, spy, ctx, 5, 5)
    assert o and o['filled'] and abs(o['stock'] - ((stock[dates[20]][3] - 10.5) / 1.0)) < 1e-9 and o['wait'] == 2 and not o['gap'], o
    # gap fill at the open
    stock[dates[15]] = bar(11, 11.2, 10.9, 11)
    o = sim_breakout(dates, stock, spy, ctx, 5, 5)
    assert o['filled'] and o['wait'] == 1 and o['gap'] and abs(o['stock'] - ((stock[dates[19]][3] - 11) / 1.0)) < 1e-9, o
    # nothing fills inside the window -> skipped
    flat = {d: bar(10, 10.4, 9.6, 10) for d in dates}
    o = sim_breakout(dates, flat, spy, ctx, 5, 5)
    assert o == {'filled': False, 'dist': round((10.4 - 10.0) / 1.0, 4)}, o
    # fill inside the window but exit beyond the data -> None
    assert sim_breakout(dates, stock, spy, ctx, 5, 21) is None
    print('selftest ok: buy-stop fill at the level, gap fill at the open, expiry, hold beyond data')


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
