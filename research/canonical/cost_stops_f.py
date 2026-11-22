"""C30 (POST HOC, Michael 9 Nov 2026): realistic trading costs for the deep-fall rule F, and a wider stop x holding-period grid.

Michael's challenge: the flat 0.10 ATR cost of Entries 28/45/69 is an assumption with no market data behind them, most F winners trade under $10M a day,
and a quarter ATR (about 1.5% of price) looks too high for stocks.  He asks for real spreads in ATR units, more stop tests, and whether 2 months is the best hold.

NEW CODE, PROVISIONAL.  Development entries only (D-068; exits may fall after 2020-12-31 as in Entries 43, 62, 69); no sealed return is read; the 2026 pilot is
not run.  Entry, ATR and cohort exactly as Entries 28, 66-69: entry = open of the entry session (day one), ATR = mean true range of the 14 sessions before
entry, F = raw252 <= -15.0 ATR, SF2 = at least 2 of (R1, N, F).  Price only; SPY on the same window in the stock's ATR units beside every stock return (D-053).

DECLARED BEFORE RUNNING:
 A. SPREAD ESTIMATES FROM THE ARCHIVE'S OWN DAILY BARS (a check, not a measurement of quotes; no quote data exists in the repo).
      CS  = Corwin-Schultz (2012) high-low estimator on consecutive-session pairs, with the overnight adjustment (if the prior close is outside the next day's
            range, the next day's range is shifted to touch it).  Reported two ways: floored at zero per pair (the authors' version, biased up when noise is large)
            and UNFLOORED (unbiased in theory, noisy).
      AR  = Abdi-Ranaldo (2017) close-high-low estimator: s = 2 * sqrt(max(mean[(c_t - eta_t)(c_t - eta_t+1)], 0)), c = log close, eta = mean of log high and log low.
    Windows per event: PRE = the 20 sessions before entry; H1 = sessions 1..21; H2 = sessions 22..42.  Spread is a fraction of price (full quoted-spread equivalent).
    Caution written in advance: the stocks' daily range is 5-9% of price while the spread is a fraction of one percent, so single-event estimates are mostly
    noise; only group means are read, and both the floored and unfloored versions are shown.
 B. PUBLISHED BENCHMARK TABLE.  Collver (SEC Division of Trading and Markets, Sept 2014), "A characterization of market quality for small capitalization US
    equities", 2013 data: mean relative effective spread (%) and mean daily dollar volume ($K) by price row and market-cap bin (Tables 4 and 5).  Per event the
    table value is interpolated in log-log between bins of that event's price row at the event's 15-session average dollar volume (Entry 54), clamped at the ends.
    This is a calm-market (2013) full effective spread, i.e. the cost of crossing once in and once out.
 C. COST SCENARIOS, all in ATR units per round trip = (percent of price) / (ATR as percent of the entry open):
      MILD      table spread x 1                      + impact at 0.1% of daily volume, Y = 0.5
      REALISTIC table spread x 2 (stress allowance)   + impact at 1% of daily volume,   Y = 0.5
      HARSH     max(table x 2, CS floored incl. tick) + impact at 5% of daily volume,   Y = 1.0
    Impact: square-root law, I = Y * sigma * sqrt(Q/V) (Toth et al.; Y of order one); average price paid over the order = 2/3 of I; sigma taken as ATR percent
    (an over-estimate of daily volatility, conservative); one way = (2/3) * Y * sqrt(phi) ATR; two ways in a round trip.  A one-cent tick floor is applied to any
    spread estimate.  Also printed for comparison: the Entry 45 assumptions (flat 0.10 ATR; price tiers 0.5% / 1% / 2% / 4% of price).
 C31 ADDITION (9 Nov 2026, declared BEFORE the run; Michael: 'try a 2 and a 2.5 ATR stop'): two more FIXED stops, 2 and 2.5 ATR below the entry open,
      added to the grid below (9 rules x 5 periods = 45 cells); every other cell is unchanged and must reproduce Entry 70.  Fixed 4 ATR not added (trail 4 exists).
 D. GRID.  Stop rules x holding periods, price only, fills at the stop or at the open on a gap, a series that ends early is closed at its last close ('delist'):
      none; fixed stop at 3 and 5 ATR below the entry open; trailing stop at 3, 4, 5, 6 ATR below the highest high (A4 of Entry 69 is trail 4; trail level
      never lowered; ATR fixed at the entry value).  Holding periods (sessions, entry session = day one): 21, 42, 63, 84, 126; every cell exits at the close of
      the last session if not stopped.  7 rules x 5 periods = 35 cells, on F and on SF2.  Per cell: stock ATR with SPY beside it, excess, net of the REALISTIC
      cost, share stopped out, share ending worse than -3 ATR, worst loss.  Stability: best cell in 2006-10 evaluated in 2011-20 and the reverse, and the
      rank correlation of the 35 cell means between the two eras; week-block 95% range for the plain 21, plain 42 and the best cell.
 Reproduction checks printed: F plain 21 stock/SPY must equal Entry 69 (+0.817 / +0.218, n=269); plain 42 (+1.559 / +0.435).
 Cautions written in advance: F is post hoc; the best of 35 overlapping cells is optimistic and is reported as such; 2008-09 and 2020 dominate the sample;
 survivorship is unresolved (Entry 65); stop fills at the stop price are optimistic in thin names (gaps hit about 10% of F trades, Entry 69); the table is 2013
 and these are fallen, volatile stocks, hence the x2 allowance; execution at the opening auction is not modelled; anything picked after this run is a lead.

Usage:  python cost_stops_f.py year YEAR --primary FILE --out FILE
        python cost_stops_f.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER SIM_FOLDER DV_FOLDER
        python cost_stops_f.py --selftest
"""
import argparse, json, math, statistics, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import excursion_stops as ex
import score_scan as ss
import context_scan as cs
from refined_baseline import DEV_END, EPISODES, assert_allowed, quarter
from stop_test import block_range

HS = (21, 42, 63, 84, 126)
MAXH = max(HS)
STOPS = [('none', 0), ('fixed', 2), ('fixed', 2.5), ('fixed', 3), ('fixed', 5), ('trail', 3), ('trail', 4), ('trail', 5), ('trail', 6)]
F_CUT = -15.0
K_CS = 3 - 2 * math.sqrt(2)
TICK = 0.01

# Collver (2014) Tables 4 and 5, 2013: per price row, (mean daily dollar volume $K, mean relative effective spread %) for market-cap bins <100, 100-250, 250-500,
# 500-1000, 1000-2000, 2000-5000 ($ million).
TABLE = {
    'p2': [(128, 1.708), (593, 0.477), (1946, 0.301), (5494, 0.244), (14714, 0.235), (28496, 0.221)],
    'p6': [(123, 1.553), (487, 0.521), (1503, 0.237), (4233, 0.144), (12896, 0.127), (26004, 0.121)],
    'p10': [(98, 1.499), (454, 0.625), (1435, 0.267), (3932, 0.139), (9659, 0.088), (24206, 0.074)],
    'p20': [(44, 1.762), (345, 0.800), (1283, 0.344), (3392, 0.170), (8217, 0.089), (20708, 0.056)],
    'p40': [(64, 1.238), (339, 0.910), (1003, 0.514), (3050, 0.251), (8226, 0.129), (19242, 0.072)],
}
SCENARIOS = {'MILD': (1.0, 0.001, 0.5), 'REALISTIC': (2.0, 0.01, 0.5), 'HARSH': (2.0, 0.05, 1.0)}


# ------------------------------------------------------------------ spread estimators
def cs_pairs(bars):
    """bars: list of (o, h, l, c) or None for consecutive sessions.  Returns the list of two-day Corwin-Schultz spreads (fraction), unfloored."""
    vals, prev = [], None
    for b in bars:
        if b is not None and prev is not None:
            _, h1, l1, c1 = prev
            _, h2, l2, c2 = b
            if min(h1, l1, h2, l2, c1) > 0 and h1 >= l1 and h2 >= l2:
                if c1 < l2:
                    d = l2 - c1
                    h2, l2 = h2 - d, l2 - d
                elif c1 > h2:
                    d = c1 - h2
                    h2, l2 = h2 + d, l2 + d
                if l2 > 0:
                    beta = math.log(h1 / l1) ** 2 + math.log(h2 / l2) ** 2
                    gamma = math.log(max(h1, h2) / min(l1, l2)) ** 2
                    alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / K_CS - math.sqrt(gamma / K_CS)
                    vals.append(2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha)))
        prev = b if b is not None else None
    return vals


def ar_est(bars):
    prods, prev = [], None
    for b in bars:
        if b is not None and min(b[1], b[2], b[3]) > 0:
            cur = (math.log(b[3]), (math.log(b[1]) + math.log(b[2])) / 2)
            if prev is not None:
                prods.append((prev[0] - prev[1]) * (prev[0] - cur[1]))
            prev = cur
        else:
            prev = None
    if len(prods) < 5:
        return None
    return 2 * math.sqrt(max(statistics.fmean(prods), 0.0))


def spread_block(bars):
    v = cs_pairs(bars)
    if len(v) < 5:
        return None
    return {'cs': statistics.fmean(max(x, 0.0) for x in v), 'csu': statistics.fmean(v), 'ar': ar_est(bars), 'n': len(v)}


# ------------------------------------------------------------------ stops
def sim_stop(dates, stock, spy, entry, ctx, kind, k):
    i, atr, op = ctx
    end = min(i + MAXH, len(dates))
    level, top, stopped = op - k * atr, op, None
    for kk in range(i, end):
        d = dates[kk]
        if d not in stock:
            continue
        o, h, l, c = stock[d]
        if kind == 'trail':
            level = max(level, top - k * atr)
        if kind != 'none' and l <= level:
            gap = kk > i and o <= level
            stopped = (kk, o if gap else level, 'gap' if gap else 'stop')
            break
        top = max(top, h)
    out = {}
    for H in HS:
        j = i + H - 1
        if j >= len(dates):
            out[H] = None
            continue
        if stopped is not None and stopped[0] <= j:
            kk, px, why = stopped
        else:
            kk = next((x for x in range(j, i - 1, -1) if dates[x] in stock), None)
            if kk is None:
                out[H] = None
                continue
            px, why = stock[dates[kk]][3], ('time' if kk == j else 'delist')
        ed = dates[kk]
        if ed not in spy:
            out[H] = None
            continue
        out[H] = [round((px - op) / atr, 4), round((spy[ed][3] / spy[entry][0] - 1) * op / atr, 4), kk - i + 1, why]
    return out


def year_job(year, primary_path, out):
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    from refined_baseline import load_span
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
        assert e['entry'] <= DEV_END, 'C30 is development years only'
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
            ctx, err = ex.entry_ctx(dates, series, spy, e['entry'])
            if err:
                r.update(err)
                rows.append(r)
                continue
            i, atr, op = ctx
            seq = lambda a, b: [series.get(dates[k]) if 0 <= k < len(dates) else None for k in range(a, b)]
            r.update({'status': 'ok', 'atr': atr, 'open': op,
                      'sp': {'pre': spread_block(seq(i - 20, i)), 'h1': spread_block(seq(i, i + 21)), 'h2': spread_block(seq(i + 21, i + 42))},
                      'grid': {f'{kd}{k}': {str(H): v for H, v in sim_stop(dates, series, spy, e['entry'], ctx, kd, k).items()} for kd, k in STOPS}})
            rows.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: status {dict(Counter(r["status"] for r in rows))}')


# ------------------------------------------------------------------ cost model
def table_spread(price, dv):
    """Collver 2013 mean relative effective spread (fraction) for this price and daily dollar volume (dollars)."""
    row = 'p2' if price < 6 else 'p6' if price < 10 else 'p10' if price < 20 else 'p20' if price < 40 else 'p40'
    pts = TABLE[row]
    x = max(dv / 1000.0, 1e-9)
    if x <= pts[0][0]:
        return pts[0][1] / 100
    if x >= pts[-1][0]:
        return pts[-1][1] / 100
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (math.log(x) - math.log(x0)) / (math.log(x1) - math.log(x0))
            return math.exp(math.log(y0) + t * (math.log(y1) - math.log(y0))) / 100
    raise AssertionError


def impact_rt_atr(phi, Y):
    return 2 * (2.0 / 3.0) * Y * math.sqrt(phi)


def cost_atr(r, scen):
    """Round-trip cost in ATR for one joined event row, or None if inputs are missing."""
    mult, phi, Y = SCENARIOS[scen]
    ap = r['atr'] / r['open']
    spr = max(table_spread(r['open'], r['dv_mean']) * mult, TICK / r['open'])
    if scen == 'HARSH':
        a, b = (r['sp'].get('pre') or {}).get('cs'), (r['sp'].get('h1') or {}).get('cs')
        if a is None or b is None:
            return None
        spr = max(spr, (a + b) / 2, TICK / r['open'])
    return spr / ap + impact_rt_atr(phi, Y)


def entry45_tier(r):
    p = r['open']
    pct = 0.005 if p >= 20 else 0.01 if p >= 10 else 0.02 if p >= 5 else 0.04
    return pct / (r['atr'] / r['open'])


# ------------------------------------------------------------------ summary
def mean(xs):
    xs = list(xs)
    return statistics.fmean(xs) if xs else float('nan')


def cell(r, key, H):
    return r['grid'][key].get(str(H))


def load_join(folder, dev, dv_folder):
    sim = {}
    for p in sorted(Path(folder).glob('cost_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            sim[(r['cik'], r['sym'], r['entry'])] = r
    out, miss = [], 0
    for r in dev:
        s = sim.get((r['cik'], r['sym'], r['entry']))
        if s is None or s.get('status') != 'ok':
            miss += 1
            continue
        out.append({**r, **{k: s[k] for k in ('atr', 'open', 'sp', 'grid')}})
    print(f'cohort {len(dev)}; with paths {len(out)}; missing {miss}')
    out = cs.load_dv(dv_folder, out)
    print(f'with 15-session dollar volume {len(out)}')
    return out


def sp_pct(rows, win, key):
    v = [r['sp'][win][key] for r in rows if r['sp'].get(win) and r['sp'][win].get(key) is not None]
    return (mean(v) * 100 if v else float('nan')), len(v)


def spread_section(label, rows):
    print(f'\n -- {label} (n={len(rows)}) --')
    if not rows:
        return
    ap = [r['atr'] / r['open'] for r in rows]
    print(f'    price median ${statistics.median(r["open"] for r in rows):.2f}; ATR as % of price median {statistics.median(ap) * 100:.1f}% (quartiles {cs_q(ap, .25) * 100:.1f}-{cs_q(ap, .75) * 100:.1f}%); '
          f'daily dollar volume median ${statistics.median(r["dv_mean"] for r in rows) / 1e6:.1f}M')
    tab = [table_spread(r['open'], r['dv_mean']) for r in rows]
    print(f'    2013 table (Collver) full effective spread: mean {mean(tab) * 100:.2f}% of price = {mean(t / a for t, a in zip(tab, ap)):.3f} ATR round trip')
    for win, nm in (('pre', 'PRE 20 sessions'), ('h1', 'HOLD sessions 1-21'), ('h2', 'HOLD sessions 22-42')):
        parts = []
        for key, lab in (('cs', 'CS floored'), ('csu', 'CS unfloored'), ('ar', 'AR')):
            m, nn = sp_pct(rows, win, key)
            parts.append(f'{lab} {m:.2f}% (n={nn})')
        print(f'    from the bars, {nm}: ' + '; '.join(parts))


def cs_q(vals, p):
    import numpy as np
    return float(np.quantile(vals, p))


def rank(v):
    order = sorted(range(len(v)), key=lambda x: v[x])
    rk = [0.0] * len(v)
    for pos, idx in enumerate(order):
        rk[idx] = pos
    return rk


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float('nan')


def grid_cells(rows):
    out = {}
    for kd, k in STOPS:
        for H in HS:
            vals = []
            for r in rows:
                c = cell(r, f'{kd}{k}', H)
                if c is not None:
                    vals.append((r, c))
            out[(f'{kd}{k}', H)] = vals
    return out


def label(key):
    return 'none' if key == 'none0' else ('fixed ' if key.startswith('fixed') else 'trail ') + key.lstrip('fixedtrail') + ' ATR'


def grid_section(name, rows):
    print(f'\n=== D. Grid on {name} (n={len(rows)}); cells are stock ATR / SPY ATR (same window); excess; net of REALISTIC cost ===')
    cells = grid_cells(rows)
    keys = [f'{kd}{k}' for kd, k in STOPS]
    cost = {id(r): cost_atr(r, 'REALISTIC') for r in rows}
    hdr = ' ' * 16 + ''.join(f'{str(H) + " sess":>20s}' for H in HS)
    stat = {}
    for key in keys:
        for H in HS:
            v = cells[(key, H)]
            if not v:
                stat[(key, H)] = None
                continue
            st, sp = mean(c[0] for _, c in v), mean(c[1] for _, c in v)
            net = mean(c[0] - c[1] - cost[id(r)] for r, c in v)
            stat[(key, H)] = {'n': len(v), 'stock': st, 'spy': sp, 'ex': st - sp, 'net': net,
                              'stopped': mean(c[3] in ('stop', 'gap') for _, c in v), 'bad3': mean(c[0] <= -3 for _, c in v), 'worst': min(c[0] for _, c in v),
                              'sess': mean(c[2] for _, c in v)}
    print('\n  stock ATR / SPY ATR\n' + hdr)
    for key in keys:
        print(f'  {label(key):14s}' + ''.join(f'{stat[(key, H)]["stock"]:>+11.2f}/{stat[(key, H)]["spy"]:+.2f}  ' if stat[(key, H)] else f'{"n/a":>20s}' for H in HS))
    print('\n  excess over SPY (ATR)\n' + hdr)
    for key in keys:
        print(f'  {label(key):14s}' + ''.join(f'{stat[(key, H)]["ex"]:>+20.3f}' if stat[(key, H)] else f'{"n/a":>20s}' for H in HS))
    print('\n  excess NET of the REALISTIC cost (ATR)\n' + hdr)
    for key in keys:
        print(f'  {label(key):14s}' + ''.join(f'{stat[(key, H)]["net"]:>+20.3f}' if stat[(key, H)] else f'{"n/a":>20s}' for H in HS))
    print('\n  share stopped out / share ending worse than -3 ATR / worst loss (ATR) / mean sessions held / n\n' + hdr)
    for key in keys:
        print(f'  {label(key):14s}' + ''.join(f'{stat[(key, H)]["stopped"]:>7.0%}/{stat[(key, H)]["bad3"]:.0%}/{stat[(key, H)]["worst"]:+.1f}/{stat[(key, H)]["sess"]:.0f}/{stat[(key, H)]["n"]:<3d}' if stat[(key, H)] else f'{"n/a":>20s}' for H in HS))
    # stability
    allc = [(k, H) for k in keys for H in HS if stat[(k, H)]]
    best = max(allc, key=lambda x: stat[x]['ex'])
    print(f'\n  best of {len(allc)} cells by gross excess: {label(best[0])} / {best[1]} sessions = {stat[best]["ex"]:+.3f} ATR (net {stat[best]["net"]:+.3f}); plain 42 = {stat[("none0", 42)]["ex"]:+.3f}; plain 21 = {stat[("none0", 21)]["ex"]:+.3f}.  '
          'The best of these overlapping cells is optimistic by construction.')
    e1 = [r for r in rows if r['entry'] < '2011-01-01']
    e2 = [r for r in rows if r['entry'] >= '2011-01-01']
    ce = {}
    for nm, rs in (('2006-10', e1), ('2011-20', e2)):
        cc = grid_cells(rs)
        ce[nm] = {kh: (mean(c[0] - c[1] for _, c in v) if v else float('nan')) for kh, v in cc.items()}
    ks = [kh for kh in ce['2006-10'] if not math.isnan(ce['2006-10'][kh]) and not math.isnan(ce['2011-20'][kh])]
    b1 = max(ks, key=lambda x: ce['2006-10'][x])
    b2 = max(ks, key=lambda x: ce['2011-20'][x])
    print(f'  era split (n 2006-10 = {len(e1)}, 2011-20 = {len(e2)}): best cell in 2006-10 = {label(b1[0])} / {b1[1]} ({ce["2006-10"][b1]:+.3f}) -> in 2011-20 {ce["2011-20"][b1]:+.3f} '
          f'(rank {sorted(ce["2011-20"][k] for k in ks).index(ce["2011-20"][b1]) + 1} of {len(ks)}); best in 2011-20 = {label(b2[0])} / {b2[1]} ({ce["2011-20"][b2]:+.3f}) -> in 2006-10 {ce["2006-10"][b2]:+.3f} '
          f'(rank {sorted(ce["2006-10"][k] for k in ks).index(ce["2006-10"][b2]) + 1} of {len(ks)}); Spearman of the {len(ks)} cell means between eras {spearman([ce["2006-10"][k] for k in ks], [ce["2011-20"][k] for k in ks]):+.2f}')
    for nm, kh in (('plain 21', ('none0', 21)), ('plain 42', ('none0', 42)), ('best cell', best)):
        v = cells[kh]
        lo, hi, _ = block_range([{'entry': r['entry'], 'x': c[0] - c[1]} for r, c in v], 'x')
        print(f'  week-block 95% range of the mean excess, {nm}: [{lo:+.3f}, {hi:+.3f}]')


def scan(events, years, decl, regime, ret, sim_folder, dv_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    rows = load_join(sim_folder, dev0, dv_folder)
    for r in rows:
        r['F'] = r['raw252'] <= F_CUT
        r['SF2'] = (int(r['R1']) + int(r['N']) + int(r['F'])) >= 2
    F = [r for r in rows if r['F']]
    SF2 = [r for r in rows if r['SF2']]
    print(f'groups: ALL {len(rows)}, F {len(F)}, SF2 {len(SF2)}')
    print('\n=== Reproduction (Entry 69, F, from the entry open) ===')
    for H, ref in ((21, '+0.817 / +0.218'), (42, '+1.559 / +0.435')):
        v = [cell(r, 'none0', H) for r in F if cell(r, 'none0', H)]
        print(f'  plain {H}: n={len(v)} stock {mean(c[0] for c in v):+.3f} / SPY {mean(c[1] for c in v):+.3f}   [Entry 69: n=269, {ref}]')
    print('\n=== A/B. Spreads: published 2013 table vs estimates from this archive\'s daily bars (F) ===')
    spread_section('F, all', F)
    for lab, lo, hi in cs.DV_BANDS:
        spread_section(f'F, {lab}', cs.band_rows(F, lo, hi))
    spread_section('F, 2006-10', [r for r in F if r['entry'] < '2011-01-01'])
    spread_section('F, 2011-20', [r for r in F if r['entry'] >= '2011-01-01'])
    spread_section('F, the three episodes (2008Q4, 2011Q3, 2020Q1)', [r for r in F if quarter(r['entry']) in EPISODES])
    spread_section('F, outside the episodes', [r for r in F if quarter(r['entry']) not in EPISODES])
    spread_section('NOT F (comparison)', [r for r in rows if not r['F']])
    print('\n=== C. Round-trip cost in ATR (F) ===')
    print('  Entry 45 / 69 assumptions for comparison: flat 0.10 ATR; price tiers (0.5% / 1% / 2% / 4% of price) = mean {:.3f} ATR on F'.format(mean(entry45_tier(r) for r in F)))
    for scen in SCENARIOS:
        v = [cost_atr(r, scen) for r in F]
        v = [x for x in v if x is not None]
        print(f'  {scen:9s}: mean {mean(v):.3f}  median {statistics.median(v):.3f}  p90 {cs_q(v, .9):.3f} ATR  (n={len(v)})   [as % of price, mean {mean(cost_atr(r, scen) * r["atr"] / r["open"] for r in F if cost_atr(r, scen) is not None) * 100:.2f}%]')
    print('  impact alone per round trip (ATR): ' + ', '.join(f'{p:.1%} of volume, Y={Y}: {impact_rt_atr(p, Y):.3f}' for p, Y in ((0.001, .5), (0.01, .5), (0.05, .5), (0.01, 1.0), (0.05, 1.0))))
    for lab, lo, hi in cs.DV_BANDS:
        g = cs.band_rows(F, lo, hi)
        if not g:
            continue
        line = f'  {lab:15s} n={len(g):3d} median price ${statistics.median(r["open"] for r in g):.2f}, ATR% {statistics.median(r["atr"] / r["open"] for r in g) * 100:.1f}%, 1% of volume = ${statistics.median(r["dv_mean"] for r in g) * 0.01 / 1000:,.0f}K | '
        line += ' | '.join(f'{s} {mean(x for x in (cost_atr(r, s) for r in g) if x is not None):.3f}' for s in SCENARIOS) + f' | Entry45 tier {mean(entry45_tier(r) for r in g):.3f}'
        print(line)
    print('\n=== C2. Plain holds on F: gross excess and excess net of each scenario (per-event costs), by period ===')
    for H in HS:
        v = [(r, cell(r, 'none0', H)) for r in F if cell(r, 'none0', H)]
        gross = mean(c[0] - c[1] for _, c in v)
        nets = {s: mean(c[0] - c[1] - cost_atr(r, s) for r, c in v if cost_atr(r, s) is not None) for s in SCENARIOS}
        print(f'  {H:3d} sessions: n={len(v)} stock {mean(c[0] for _, c in v):+.3f} SPY {mean(c[1] for _, c in v):+.3f} excess {gross:+.3f} | net MILD {nets["MILD"]:+.3f}  REALISTIC {nets["REALISTIC"]:+.3f}  HARSH {nets["HARSH"]:+.3f}')
    print('  by dollar-volume band (plain 21 and plain 42; excess gross -> net REALISTIC / HARSH):')
    for lab, lo, hi in cs.DV_BANDS:
        g = cs.band_rows(F, lo, hi)
        parts = []
        for H in (21, 42):
            v = [(r, cell(r, 'none0', H)) for r in g if cell(r, 'none0', H)]
            if v:
                parts.append(f'{H}: n={len(v)} {mean(c[0] - c[1] for _, c in v):+.3f} -> {mean(c[0] - c[1] - cost_atr(r, "REALISTIC") for r, c in v):+.3f} / '
                             f'{mean(c[0] - c[1] - cost_atr(r, "HARSH") for r, c in v if cost_atr(r, "HARSH") is not None):+.3f}')
        print(f'    {lab:15s} ' + ' | '.join(parts))
    grid_section('F', F)
    grid_section('SF2', SF2)
    print('\nPOST HOC; costs are model estimates (published table + square-root impact + bar-based spreads), not quotes or fills; 35 cells, best-of-menu optimistic.')


# ------------------------------------------------------------------ self test
def selftest():
    from datetime import date, timedelta
    # Abdi-Ranaldo recovers a constant spread: close = mid + s/2, high/low symmetric about the mid
    s = 0.02
    bars = [(10, 10 * math.exp(0.05), 10 * math.exp(-0.05), 10 * math.exp(s / 2)) for _ in range(30)]
    assert abs(ar_est(bars) - s) < 1e-9, ar_est(bars)
    # Corwin-Schultz on identical bars with range r returns about r
    r = math.log(100.5 / 99.5)
    cb = [(100, 100.5, 99.5, 100)] * 30
    v = cs_pairs(cb)
    assert abs(statistics.fmean(v) - r) < 1e-3, statistics.fmean(v)
    z = cs_pairs([(10, 10, 10, 10)] * 10)
    assert all(abs(x) < 1e-12 for x in z)
    # table interpolation hits the nodes and clamps
    assert abs(table_spread(8.0, 4233e3) - 0.00144) < 1e-9 and abs(table_spread(12.0, 5e4) - 0.01499) < 1e-9 and abs(table_spread(50.0, 1e10) - 0.00072) < 1e-9
    mid = table_spread(8.0, 2.5e6)
    assert 0.00144 < mid < 0.00237, mid
    assert abs(impact_rt_atr(0.01, 0.5) - 2 * (2 / 3) * 0.5 * 0.1) < 1e-12
    # stop simulator on a synthetic path
    d0, dates, k = date(2010, 1, 4), [], 0
    while len(dates) < 300:
        x = d0 + timedelta(days=k)
        k += 1
        if x.weekday() < 5:
            dates.append(x.isoformat())
    stock = {d: (10.0, 10.5, 9.5, 10.0) for d in dates}
    spy = {d: (100.0, 101.0, 99.0, 100.0 + 0.1 * n) for n, d in enumerate(dates)}
    i = 60
    entry = dates[i]
    ctx, err = ex.entry_ctx(dates, stock, spy, entry)
    assert err is None and abs(ctx[1] - 1.0) < 1e-9
    stock[dates[i + 3]] = (10.0, 10.2, 6.5, 8.0)                  # session 4: low 6.5 touches the 3 ATR stop at 7.0
    o = sim_stop(dates, stock, spy, entry, ctx, 'fixed', 3)
    assert o[21][3] == 'stop' and abs(o[21][0] + 3.0) < 1e-9 and o[21][2] == 4, o[21]
    n = sim_stop(dates, stock, spy, entry, ctx, 'none', 0)
    assert n[21][3] == 'time' and n[21][2] == 21 and abs(n[21][0]) < 1e-9, n[21]
    stock[dates[i + 3]] = (10.0, 14.0, 9.5, 13.0)                 # high 14 -> trail 3 ATR level 11 from session 5
    stock[dates[i + 4]] = (13.0, 13.2, 10.0, 12.0)               # session 5 low 10 <= 11, opens above -> exit at 11
    t = sim_stop(dates, stock, spy, entry, ctx, 'trail', 3)
    assert t[21][3] == 'stop' and abs(t[21][0] - 1.0) < 1e-9 and t[21][2] == 5, t[21]
    stock[dates[i + 4]] = (9.0, 9.5, 8.5, 9.0)                    # opens below the level -> gap fill at the open
    t2 = sim_stop(dates, stock, spy, entry, ctx, 'trail', 3)
    assert t2[21][3] == 'gap' and abs(t2[21][0] + 1.0) < 1e-9, t2[21]
    assert sim_stop(dates, stock, spy, entry, ctx, 'none', 0)[126] is not None and sim_stop(dates, stock, spy, dates[len(dates) - 50], ex.entry_ctx(dates, stock, spy, dates[len(dates) - 50])[0], 'none', 0)[126] is None
    print('selftest ok: Abdi-Ranaldo, Corwin-Schultz, table interpolation, impact, stop simulator (stop, gap, time, open)')


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
