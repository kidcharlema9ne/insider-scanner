"""C42 (POST HOC, Michael 9 Nov 2026: "do the score less than 0 as a filter and the score greater than 0 as a bonus ... run those variants").

NEW CODE, PROVISIONAL.  Development entries only (D-068); no sealed entry is read.  Uses the Entry 82 engine UNCHANGED (portfolio_sim.simulate, the per-trade paths of run
42624583101: $100,000, 0.1% of equity per 1 ATR at 1.0U, 3 ATR fixed stop, 42 sessions, 0.10 ATR round trip, Entry 78 size-ups) and the Entry 85/86 earlier-buy score
(insider_history.event_flags, ret_mean2: mean excess of the buyers' earlier buys, each buyer needs >= 2 priced earlier buys).

DECLARED BEFORE RUNNING:
 Tier of a trade: GOOD = score > 0; BAD = score <= 0; NEUTRAL = not scoreable (fewer than 2 qualifying buyers, or entered before 2008-04-01 when the insider history starts).
 Menu of variants (all printed, same cohort, same engine, same cost 0.10 ATR):
   V0 BASELINE   the Entry 82 MAIN run (must reproduce: end $239,509, CAGR +5.98%, max DD -21.7%).
   V1 VETO       skip BAD trades (not entered at all).
   V2 BONUS      GOOD trades get + BONUS_U on top of their U.  BONUS_U = the R1 add-on from sizing_weights (0.105U): Michael compared the flag to the small CEO/CFO bonus,
                 and the Entry 86 gap of GOOD over NEUTRAL (about +0.14 ATR) is the same size as R1's estimate (+0.116).  Not tuned.
   V3 BOTH       V1 and V2 together (Michael's proposal).
   S1 SENSITIVITY  VETO + a GOOD bonus of +0.846U (the N add-on), to see whether a bigger bonus matters.  Counted in the menu (5 variants), not the headline.
 Placebo for the veto: 300 random draws that skip the same NUMBER of trades chosen at random from the SCOREABLE trades (same pool as the real veto), run through the same engine;
   we report where the real veto sits among them (end equity, Sharpe, mean gross excess of the trades kept).  Seed 20261109.
 Reconciliation: mean gross excess over SPY (ATR) by tier on the tradable trades, to compare with Entry 86 (GOOD +0.274, BAD -0.112, cohort +0.130 on its own 1,165-event cohort).
 Statistics as Entry 82: end value, CAGR, vol, Sharpe, Sortino, max drawdown, entries, per month, trade block, calendar years, week-block range of the mean excess, sample sizes.
Cautions written in advance: the flag was found on this same cohort (Entry 85) so every gain here is in-sample; a 5-variant menu chosen after seeing Entry 86; the 8U open cap is
NOT enforced (peak open 128U in 2008-09, Entry 82); survivorship (Entry 65) and wipe-outs are not in this archive; one path, so the drawdown is one draw; costs are 0.10 ATR by
instruction.  A lead, not an edge.

Usage:  python earlier_buy_portfolio.py scan EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER DV_FOLDER PATH_FOLDER ROWS EP_DIR EPRET_DIR
        python earlier_buy_portfolio.py --selftest
"""
import json, random, statistics, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio_sim as pf
from refined_baseline import DEV_END, assert_allowed

SEED = 20261109
DRAWS = 300
BONUS_REF = 'R1'      # add-on used for V2/V3
BONUS_BIG = 'N'       # add-on used for the sensitivity


def tier(score):
    if score is None:
        return 'NEUTRAL'
    return 'GOOD' if score > 0 else 'BAD'


def apply_variant(trades, veto, bonus_u):
    """trades: dicts with 'tier' and 'U'.  Returns new trade dicts (copies)."""
    out = []
    for t in trades:
        if veto and t['tier'] == 'BAD':
            continue
        u = t['U'] + (bonus_u if t['tier'] == 'GOOD' else 0.0)
        out.append({**t, 'U': u})
    return out


def score_map(events, years, returns, hist, ep_dir, epret_dir):
    import insider_history as ih
    base, ev_by_key, hist_, ep_by_owner, ep_res = ih.load_all(events, years, returns, hist, ep_dir, epret_dir)
    out = {}
    for r in base:
        if ih.COHORT_START <= r['entry'] <= DEV_END:
            k = (r['cik'], r['sym'], r['entry'])
            ev = ev_by_key[k][0]
            out[k] = ih.event_flags(ev, hist_, ep_by_owner, ep_res)['ret_mean2']
    return out


def build(cohort, sim, dv, add, scores):
    out, miss = [], Counter()
    for r in cohort:
        k = (r['cik'], r['sym'], r['entry'])
        s = sim.get(k)
        if s is None:
            miss['no_row'] += 1
            continue
        if s.get('status') != 'ok':
            miss[s.get('status', 'bad')] += 1
            continue
        t = {**{f: bool(r[f]) for f in pf.FLAGS}, 'entry': r['entry'], 'sym': r['sym'], 'dv': dv.get(k), 'U': pf.size_u(add, r), 'tier': tier(scores.get(k))}
        t.update({f: s[f] for f in ('atr', 'open', 'ret_atr', 'spy_atr', 'sess', 'why', 'exit_date', 'exit_px', 'days')})
        out.append(t)
    out.sort(key=lambda t: (t['entry'], t['sym']))
    return out, miss


def run(trades, cal, **kw):
    curve, recs, cnt = pf.simulate(trades, cal, **kw)
    return curve, recs, cnt, pf.curve_stats(curve, pf.START)


def months_between(d0, d1):
    return (date.fromisoformat(d1) - date.fromisoformat(d0)).days / 30.4375


def scan(events, years, decl, regime, ret, dd_folder, dv_folder, path_folder, rows, ep_dir, epret_dir):
    import drawdown_scan as dd
    import score_scan as ss
    import deepfall_2x2 as d2
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, _ = dd.load_dd(dd_folder, dev0)
    cohort = [r for r in dev if 'dd252' in r]
    for r in cohort:
        d2.flags(r)
        assert r['entry'] <= DEV_END
    sim, spy = pf.load_paths(path_folder)
    dv = pf.load_dv_soft(dv_folder)
    scores = score_map(events, years, ret, rows, ep_dir, epret_dir)
    add = pf.add_on_u()
    trades, miss = build(cohort, sim, dv, add, scores)
    tc = Counter(t['tier'] for t in trades)
    print(f'cohort {len(cohort)}; tradable paths {len(trades)}; not tradable {dict(miss)}; tiers on tradable trades: {dict(tc)}')
    cal = sorted(spy)
    d_first = min(t['entry'] for t in trades)
    prior = [d for d in cal if d < d_first]
    cal_run = [d for d in cal if d >= d_first]
    d0 = prior[-1] if prior else cal_run[0]
    bench = pf.spy_curve(spy, cal_run, d0, pf.START)
    bs = pf.curve_stats(bench, pf.START)
    n_months = months_between(cal_run[0], cal_run[-1])
    print(f'period {cal_run[0]} to {cal_run[-1]} ({len(cal_run)} sessions, {n_months:.0f} months). SPY buy and hold: end ${bs["end"]:,.0f}, CAGR {bs["cagr"]:+.2%}, Sharpe {bs["sharpe"]:.2f}, max DD {bs["mdd"]:+.1%}')
    bonus_ref, bonus_big = add[BONUS_REF], add[BONUS_BIG]
    print(f'bonus sizes: V2/V3 +{bonus_ref:.3f}U (the {BONUS_REF} add-on); sensitivity +{bonus_big:.3f}U (the {BONUS_BIG} add-on)')

    # ---- reconciliation with Entry 86: gross excess by tier on the tradable paths
    print('\n=== 0. Gross excess over SPY by tier, tradable trades (stock leg / SPY leg / excess, ATR; 42-session path with the 3 ATR stop, so NOT the 21-session hold of Entry 86) ===')
    ex = lambda g: statistics.fmean(t['ret_atr'] - t['spy_atr'] for t in g) if g else float('nan')
    for nm in ('GOOD', 'BAD', 'NEUTRAL'):
        g = [t for t in trades if t['tier'] == nm]
        print(f'  {nm:8s} n={len(g):4d}  stock {statistics.fmean(t["ret_atr"] for t in g):+.3f} / SPY {statistics.fmean(t["spy_atr"] for t in g):+.3f} = excess {ex(g):+.3f}'
              f'   | inside F n={sum(t["F"] for t in g)} excess {ex([t for t in g if t["F"]]):+.3f}; outside F n={sum(not t["F"] for t in g)} excess {ex([t for t in g if not t["F"]]):+.3f}')
    print(f'  ALL      n={len(trades):4d}  excess {ex(trades):+.3f}')

    variants = [('V0 BASELINE', False, 0.0), ('V1 VETO (skip BAD)', True, 0.0), (f'V2 BONUS (GOOD +{bonus_ref:.2f}U)', False, bonus_ref),
                (f'V3 BOTH (veto + {bonus_ref:.2f}U)', True, bonus_ref), (f'S1 veto + GOOD +{bonus_big:.2f}U', True, bonus_big)]
    res = {}
    for nm, veto, bu in variants:
        tr = apply_variant(trades, veto, bu)
        res[nm] = (tr,) + run(tr, cal_run)
    gross = {}
    for nm, veto, bu in variants:
        gross[nm] = run(apply_variant(trades, veto, bu), cal_run, cost=0.0)[3]
    cost20 = {}
    for nm, veto, bu in variants:
        cost20[nm] = run(apply_variant(trades, veto, bu), cal_run, cost=0.20)[3]

    print('\n=== 1. Portfolio, five variants ($100,000; 3 ATR stop; 42-session exit; cost 0.10 ATR) ===')
    for nm, _, _ in variants:
        tr, curve, recs, cnt, st = res[nm]
        inv = [c[2] / c[1] for c in curve]
        print(pf.fmt_stats(nm, st, f'  entries {len(recs)} ({len(recs) / n_months:.1f}/month)  avg invested {statistics.fmean(inv):.0%}  peak open {cnt["peak_open_U"]:.0f}U'))
    print(pf.fmt_stats('SPY buy and hold', bs))
    print('\n  same variants at cost 0.00 (gross) and 0.20 ATR (CAGR / max DD / end):')
    for nm, _, _ in variants:
        print(f'   {nm:34s} gross {gross[nm]["cagr"]:+6.2%} / {gross[nm]["mdd"]:+6.1%} / ${gross[nm]["end"]:>9,.0f}   cost 0.20 {cost20[nm]["cagr"]:+6.2%} / {cost20[nm]["mdd"]:+6.1%} / ${cost20[nm]["end"]:>9,.0f}')

    base_st = res['V0 BASELINE'][4]
    print(f'\n  reproduction check (Entry 82 MAIN: end $239,509, CAGR +5.98%, max DD -21.7%): here end ${base_st["end"]:,.0f}, CAGR {base_st["cagr"]:+.2%}, max DD {base_st["mdd"]:+.1%}')

    print('\n=== 2. Trade statistics by variant (net of cost; ATR columns gross unless noted) ===')
    for nm, _, _ in variants:
        recs = res[nm][2]
        print(pf.trade_block(recs, nm))
        try:
            from stop_test import block_range
            lo, hi, _ = block_range([{'entry': x['entry'], 'x': x['stock_atr'] - x['spy_atr']} for x in recs], 'x')
            lo2, hi2, _ = block_range([{'entry': x['entry'], 'x': x['R']} for x in recs], 'x')
            print(f'      week-block 95%: mean gross excess [{lo:+.3f}, {hi:+.3f}]; mean R net [{lo2:+.3f}, {hi2:+.3f}]')
        except Exception as e:      # pragma: no cover
            print('      block range unavailable:', e)
        ds = sorted({x['entry'] for x in recs})
        wk = {date.fromisoformat(x['entry']).isocalendar()[:2] for x in recs}
        print(f'      sample: {len(recs)} trades, {len(ds)} entry dates, {len(wk)} weeks, {len({x["entry"][:7] for x in recs})} months')

    print('\n=== 3. Calendar-year return by variant ===')
    cys = {nm: pf.calendar_years(res[nm][1], pf.START) for nm, _, _ in variants}
    bsy = pf.calendar_years(bench, pf.START)
    names = [v[0] for v in variants]
    print('  year   ' + ' '.join(f'{n[:11]:>11s}' for n in names) + '      SPY')
    for y in cys[names[0]]:
        print(f'  {y}  ' + ' '.join(f'{cys[n][y]:+10.1%} ' for n in names) + f' {bsy.get(y, float("nan")):+8.1%}')
    for n in names[1:]:
        up = sum(cys[n][y] > cys[names[0]][y] for y in cys[n])
        print(f'  {n}: better than baseline in {up} of {len(cys[n])} calendar years')

    print('\n=== 4. Does the veto beat a random skip of the same size from the same pool? (300 draws; end equity, Sharpe, mean gross excess of trades kept) ===')
    rng = random.Random(SEED)
    scoreable = [i for i, t in enumerate(trades) if t['tier'] != 'NEUTRAL']
    nbad = sum(t['tier'] == 'BAD' for t in trades)
    v1 = res[names[1]]
    real = (v1[4]['end'], v1[4]['sharpe'], ex(v1[0]))
    ends, shs, exs = [], [], []
    for _ in range(DRAWS):
        skip = set(rng.sample(scoreable, nbad))
        kept = [t for i, t in enumerate(trades) if i not in skip]
        _, _, _, st = run(kept, cal_run)
        ends.append(st['end'])
        shs.append(st['sharpe'])
        exs.append(ex(kept))
    pct = lambda xs, v: sum(x >= v for x in xs) / len(xs)
    print(f'  skipped {nbad} of {len(scoreable)} scoreable trades per draw.  Real veto: end ${real[0]:,.0f}, Sharpe {real[1]:.3f}, kept-trade excess {real[2]:+.3f}')
    print(f'  random draws: end ${statistics.fmean(ends):,.0f} (5-95%: ${sorted(ends)[int(.05 * DRAWS)]:,.0f} to ${sorted(ends)[int(.95 * DRAWS)]:,.0f}); Sharpe {statistics.fmean(shs):.3f}; kept excess {statistics.fmean(exs):+.3f}')
    print(f'  share of random draws at least as good as the real veto: end equity {pct(ends, real[0]):.1%}, Sharpe {pct(shs, real[1]):.1%}, kept-trade excess {pct(exs, real[2]):.1%}')
    print('  (this is the chance of a skip-this-many rule looking this good by luck among the SAME scoreable trades; it does not correct for the flag having been found on this cohort)')

    print('\nPOST HOC; the flag was found on this cohort (Entry 85) and the menu of 5 variants was chosen after Entry 86; the 8U open cap is not enforced; survivorship (Entry 65) and wipe-outs are not in '
          'this archive; costs are 0.10 ATR by instruction; one path, so the drawdown is one draw.  A lead, not an edge.')


def selftest():
    T = lambda tier_, u=1.0: {'tier': tier_, 'U': u}
    ts = [T('GOOD'), T('BAD', 2.0), T('NEUTRAL', 1.5)]
    assert tier(None) == 'NEUTRAL' and tier(0.0) == 'BAD' and tier(-0.1) == 'BAD' and tier(0.01) == 'GOOD'
    v = apply_variant(ts, False, 0.0)
    assert [t['U'] for t in v] == [1.0, 2.0, 1.5]
    v = apply_variant(ts, True, 0.0)
    assert [t['tier'] for t in v] == ['GOOD', 'NEUTRAL']
    v = apply_variant(ts, True, 0.1)
    assert [round(t['U'], 6) for t in v] == [1.1, 1.5], v
    v = apply_variant(ts, False, 0.1)
    assert [round(t['U'], 6) for t in v] == [1.1, 2.0, 1.5], v
    assert ts[0]['U'] == 1.0          # inputs untouched
    print('earlier_buy_portfolio selftest ok: tiers, veto, bonus, copies')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    assert sys.argv[1] == 'scan'
    scan(*sys.argv[2:])
