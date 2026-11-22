"""SEALED RUN (D-059, D-068): the one-time test of research_docs/SEALED_HYPOTHESES.md on entries 2021-04-01 through 2025-12-31.

Michael, 9 Nov 2026: "That's fine. Test them all. Let's go."  The hypothesis file is the contract; this script implements it and nothing else.

Three modes:
  check YEARS...   DEVELOPMENT years only, SEALED_RUN unset.  Rebuilds, with THIS file's code, the features and paths for those development years and compares them with the stored
                   development results (Entry 28 returns, Entry 36 raw252, Entry 37 lead63, Entry 32 roles, Entry 90 stop paths).  Any mismatch exits non-zero, which stops the sealed jobs.
  year YEAR        SEALED years: needs SEALED_RUN=1 and research_docs/SEALED_HYPOTHESES.md beginning "# Sealed-year hypotheses (FROZEN".  Per entry: roles, 12-month fall, Nasdaq lead, the 3 ATR /
                   42-session stop path, the 21-session no-stop return.
  analyze FOLDER   the declared statistics H1-H3, once.

Deviations from the hypothesis file, stated here because they cannot be avoided: the 1%-of-daily-dollar-volume cap is not applied (the sealed run has no dollar-volume files; the cap never
bound in the development portfolio, Entry 82).  Everything else is as declared.
"""
import json, math, os, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import refined_baseline as rb

SEALED_START, SEALED_END = '2021-04-01', '2025-12-31'
EXPECT_SEALED, EXPECT_DEV = 460, 1373
N_CUT = -0.0195                 # development fifth cut of ONEQ-minus-SPY over 63 sessions (Entry 41), NOT recomputed
FALL_DEEP = 15.0
ADD_R1, ADD_N, ADD_FALL, FALL_K, FALL_C, CAP = 0.20, 1.00, 0.11, 8.0, 20.0, 4.0
COST = 0.10
MIN_N = 40
SHUFFLES = 10_000
SEED = 20261109


def frozen_ok():
    head = (Path(__file__).resolve().parents[2] / 'docs' / 'SEALED_HYPOTHESES.md').read_text().splitlines()[0]
    return head.startswith('# Sealed-year hypotheses (FROZEN')


def size_u(row):
    r1 = (not row['ceo']) and (not row['cfo'])
    n = row['lead63'] is not None and row['lead63'] <= N_CUT
    fall = max(0.0, -row['raw252'])
    h = min(max(fall, FALL_K), FALL_C) - FALL_K
    return min(CAP, 1.0 + ADD_R1 * r1 + ADD_N * n + ADD_FALL * h), r1, n


# ------------------------------------------------------------------ rows
def load_events(events_path):
    from archive_coverage_audit import normalize_ticker
    events = json.loads(Path(events_path).read_text())
    by_key = defaultdict(list)
    for e in events:
        if e['set'] == 'refined':
            by_key[(e['issuer_cik'], normalize_ticker(e['ticker'])[0], e['entry'])].append(e)
    return by_key


def year_rows(year, primary, by_key):
    """primary: entries of this year (dicts with sym, cik, entry, via).  Returns (rows, spy closes)."""
    import excursion_stops as ex
    import cost_stops_f as cf
    import factor_decline as fdec
    import factor_regime as freg
    import factor_roles as fr
    from archive_coverage_audit import DELISTED
    from r2_storage import client
    s3 = client()
    syms = {e['sym'] for e in primary}
    want = syms | {s + DELISTED for s in syms}
    stock_bars, dates = rb.load_span(s3, 'stock', [year - 1, year, year + 1], want, 30, 30)
    etf_bars, edates = rb.load_span(s3, 'etf', [year - 1, year, year + 1], {'SPY', 'ONEQ'}, 30, 30)
    spy, oneq = etf_bars.get('SPY', {}), etf_bars.get('ONEQ', {})
    print(f'{year}: {len(primary)} entries, {len(dates)} stock sessions, SPY bars {len(spy)}, ONEQ bars {len(oneq)}')
    rows, last_exit = [], max(e['entry'] for e in primary)
    for e in sorted(primary, key=lambda e: (e['entry'], e['sym'])):
        series = dict(stock_bars.get(e['sym'], {}))
        if e.get('via') == 'delisted' or not series:
            series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
        r = {'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik']}
        ev = by_key.get((e['cik'], e['sym'], e['entry']))
        if not ev:
            r['status'] = 'no_event'
            rows.append(r)
            continue
        r.update({k: v for k, v in fr.roles(ev[0]['owners']).items() if k in ('ceo', 'cfo')})
        ctx, err = ex.entry_ctx(dates, series, spy, e['entry'])
        if err:
            r.update(err)
            rows.append(r)
            continue
        i, atr, op = ctx
        f = fdec.features(dates, series, spy, e['entry'])
        reg = freg.date_features(edates, spy, oneq, e['entry'])
        r['raw252'] = f.get('raw252')
        r['lead63'] = reg.get('lead63') if reg.get('status') == 'ok' else None
        stop = cf.sim_stop(dates, series, spy, e['entry'], ctx, 'fixed', 3).get(42)
        plain = cf.sim_stop(dates, series, spy, e['entry'], ctx, 'none', 3).get(21)
        if stop is None or plain is None or r['raw252'] is None:
            r.update({'status': 'no_path', 'atr': atr, 'open': op})
            rows.append(r)
            continue
        ret, spy_atr, sess, why = stop
        kk = i + sess - 1
        r.update({'status': 'ok', 'atr': atr, 'open': op, 'ret_atr': ret, 'spy_atr': spy_atr, 'sess': sess, 'why': why, 'exit_date': dates[kk],
                  'exit_px': round(op + ret * atr, 6), 'ex21': plain[0] - plain[1], 'stock21': plain[0], 'spy21': plain[1],
                  'days': [[dates[k], series[dates[k]][3] if dates[k] in series else None] for k in range(i, kk + 1)]})
        last_exit = max(last_exit, dates[kk])
        rows.append(r)
    spy_out = {d: spy[d][3] for d in dates if f'{year}-01-01' <= d <= max(last_exit, f'{year}-12-31') and d in spy}
    return rows, spy_out


def primary_window(year_folder, lo, hi):
    prim = rb.build_primary(year_folder)
    return [e for e in prim if lo <= e['entry'] <= hi]


# ------------------------------------------------------------------ check (development years only)
def check(years, year_folder, events_path, decl, regime, ret, dd_folder, path_folder):
    assert os.environ.get('SEALED_RUN') != '1', 'check mode runs on development years only'
    import drawdown_scan as dd
    import score_scan as ss
    import portfolio_sim as ps
    prim = primary_window(year_folder, '2000-01-01', rb.DEV_END)
    assert len(prim) == EXPECT_DEV, f'development primary count {len(prim)} != {EXPECT_DEV}'
    dev0 = ss.build(events_path, year_folder, decl, regime, ret)
    dev, _ = dd.load_dd(dd_folder, dev0)
    coh = {(r['cik'], r['sym'], r['entry']): r for r in dev}
    sim, _ = ps.load_paths(path_folder)
    by_key = load_events(events_path)
    bad, ok, compared = Counter(), Counter(), 0
    dry_dir = Path('reports/devcheck')
    dry_dir.mkdir(parents=True, exist_ok=True)
    for y in years:
        rows, spy_y = year_rows(y, [e for e in prim if e['entry'].startswith(str(y))], by_key)
        (dry_dir / f'sealed_{y}.json').write_text(json.dumps({'year': y, 'rows': rows, 'spy': spy_y}))
        for r in rows:
            k = (r['cik'], r['sym'], r['entry'])
            c = coh.get(k)
            if c is None or r.get('status') != 'ok':
                continue
            compared += 1
            tests = {'raw252': abs(r['raw252'] - c['raw252']) < 1e-9, 'lead63': r['lead63'] is not None and abs(r['lead63'] - c['lead63']) < 1e-9,
                     'ceo': r['ceo'] == c['ceo'], 'cfo': r['cfo'] == c['cfo'], 'excess21': abs(r['ex21'] - c['excess_atr']) < 3e-4}   # sim_stop rounds each leg to 4 decimals (the stored stop paths match at 1e-6)
            s = sim.get(k)
            if s and s.get('status') == 'ok':
                tests['stop_ret'] = abs(r['ret_atr'] - s['ret_atr']) < 1e-6
                tests['stop_exit'] = r['exit_date'] == s['exit_date'] and r['why'] == s['why']
            for t, good in tests.items():
                (ok if good else bad)[t] += 1
    print(f'CHECK on development years {list(years)}: events compared {compared}; agree {dict(ok)}; DISAGREE {dict(bad)}')
    if bad or compared < 150:
        print('CHECK FAILED: the sealed run must not start')
        sys.exit(1)
    print('CHECK PASSED: features, roles, 21-session returns and 3 ATR stop paths reproduce the development results exactly')
    print('\n########## DRY RUN OF THE ANALYSIS ON THESE DEVELOPMENT YEARS (a test of the code, not a result) ##########')
    analyze(str(dry_dir), dry=True)
    print('########## END OF DRY RUN ##########')


# ------------------------------------------------------------------ sealed year
def sealed_year(year, year_folder, events_path, out):
    assert os.environ.get('SEALED_RUN') == '1', 'SEALED_RUN=1 required'
    assert frozen_ok(), 'research_docs/SEALED_HYPOTHESES.md is not marked FROZEN: no sealed entry may be read'
    prim = primary_window(year_folder, SEALED_START, SEALED_END)
    assert len(prim) == EXPECT_SEALED, f'sealed primary count {len(prim)} != {EXPECT_SEALED} (D-068)'
    mine = [e for e in prim if e['entry'].startswith(str(year))]
    rows, spy = year_rows(year, mine, load_events(events_path)) if mine else ([], {})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows, 'spy': spy}))
    print(f'{year}: status {dict(Counter(r["status"] for r in rows))}')


# ------------------------------------------------------------------ statistics
def week_of(entry):
    return date.fromisoformat(entry).isocalendar()[:2]


def shuffle_chance(vals, labels, weeks, draws=SHUFFLES, seed=SEED):
    """One-sided chance that mean(vals[label]) - mean(vals[~label]) is at least the observed value when labels are shuffled inside each entry week."""
    rng = np.random.default_rng(seed)
    vals, labels = np.asarray(vals, float), np.asarray(labels, bool)
    obs = vals[labels].mean() - vals[~labels].mean()
    groups = defaultdict(list)
    for i, w in enumerate(weeks):
        groups[w].append(i)
    idx = [np.asarray(g) for g in groups.values()]
    hit = 0
    for _ in range(draws):
        lab = labels.copy()
        for g in idx:
            if len(g) > 1:
                lab[g] = lab[g][rng.permutation(len(g))]
        if lab.sum() in (0, len(lab)):
            continue
        hit += (vals[lab].mean() - vals[~lab].mean()) >= obs - 1e-12
    return obs, hit / draws


def week_block_range(vals, weeks, draws=SHUFFLES, seed=SEED + 1):
    rng = np.random.default_rng(seed)
    groups = defaultdict(list)
    for v, w in zip(vals, weeks):
        groups[w].append(v)
    blocks = [np.asarray(g) for g in groups.values()]
    means = []
    for _ in range(draws):
        pick = rng.integers(0, len(blocks), len(blocks))
        means.append(np.concatenate([blocks[j] for j in pick]).mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def bh_adjust(ps_):
    order = sorted(range(len(ps_)), key=lambda i: ps_[i])
    adj, prev = [0.0] * len(ps_), 1.0
    for rank in range(len(ps_), 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps_[i] * len(ps_) / rank)
        adj[i] = prev
    return adj


def group_test(name, rows, flag):
    lab = [flag(r) for r in rows]
    net = [r['ex21'] - COST for r in rows]
    weeks = [week_of(r['entry']) for r in rows]
    g = [v for v, l in zip(net, lab) if l]
    rest = [v for v, l in zip(net, lab) if not l]
    print(f'\n{name}: n={len(g)} (rest {len(rest)})')
    if len(g) < MIN_N or len(rest) < MIN_N:
        print(f'  fewer than {MIN_N} entries in a group -> INCONCLUSIVE')
        return None, 'INCONCLUSIVE'
    gr = [r for r, l in zip(rows, lab) if l]
    ro = [r for r, l in zip(rows, lab) if not l]
    obs, p = shuffle_chance(net, lab, weeks)
    lo, hi = week_block_range(g, [week_of(r['entry']) for r in gr])
    print(f'  group: stock {statistics.fmean(r["stock21"] for r in gr):+.3f} / SPY {statistics.fmean(r["spy21"] for r in gr):+.3f} = gross excess {statistics.fmean(r["ex21"] for r in gr):+.3f} ATR; '
          f'net of {COST} ATR {statistics.fmean(g):+.3f}  (week-block 95% range {lo:+.3f} to {hi:+.3f})')
    print(f'  rest : stock {statistics.fmean(r["stock21"] for r in ro):+.3f} / SPY {statistics.fmean(r["spy21"] for r in ro):+.3f} = gross excess {statistics.fmean(r["ex21"] for r in ro):+.3f} ATR; '
          f'net {statistics.fmean(rest):+.3f}')
    print(f'  difference (group minus rest, net) {obs:+.3f}; chance from shuffling inside the entry week {p:.2%} ({SHUFFLES:,} draws)')
    return p, None


def analyze(folder, dry=False):
    import portfolio_sim as ps
    import continuous_sizing as cs
    assert dry or frozen_ok(), 'hypothesis file is not FROZEN'
    rows, spy = [], {}
    for p in sorted(Path(folder).glob('sealed_*.json')):
        j = json.loads(p.read_text())
        rows += j['rows']
        spy.update(j['spy'])
    if not dry:
        rows = [r for r in rows if SEALED_START <= r['entry'] <= SEALED_END]
    print(f'{"DRY RUN" if dry else "SEALED RUN"}: {len(rows)} entries; status {dict(Counter(r["status"] for r in rows))}')
    assert dry or len(rows) == EXPECT_SEALED, len(rows)
    ok = [r for r in rows if r['status'] == 'ok']
    for r in ok:
        r['U'], r['R1'], r['N'] = size_u(r)
    print(f'usable {len(ok)}; no-CEO/CFO {sum(r["R1"] for r in ok)}; Nasdaq lagging {sum(r["N"] for r in ok)}; fall >= {FALL_DEEP:g} ATR {sum(-r["raw252"] >= FALL_DEEP for r in ok)}; '
          f'mean U {statistics.fmean(r["U"] for r in ok):.2f}, max U {max(r["U"] for r in ok):.2f}')
    print(f'by year (entries / mean 21-session excess gross over SPY): ' + '; '.join(
        f'{y} {sum(r["entry"][:4] == y for r in ok)} / {statistics.fmean(r["ex21"] for r in ok if r["entry"][:4] == y):+.3f}' for y in sorted({r["entry"][:4] for r in ok})))
    print(f'ALL sealed entries, 21 sessions, no stop: stock {statistics.fmean(r["stock21"] for r in ok):+.3f} / SPY {statistics.fmean(r["spy21"] for r in ok):+.3f} = gross excess '
          f'{statistics.fmean(r["ex21"] for r in ok):+.3f} ATR; net of {COST}: {statistics.fmean(r["ex21"] for r in ok) - COST:+.3f}')

    print('\n=== H1: the sized system ($100,000, 3 ATR stop, 42 sessions, 0.10 ATR; SPY same dates) ===')
    trades = [{'entry': r['entry'], 'sym': r['sym'], 'open': r['open'], 'atr': r['atr'], 'exit_date': r['exit_date'], 'exit_px': r['exit_px'], 'why': r['why'], 'days': r['days'],
               'sess': r['sess'], 'ret_atr': r['ret_atr'], 'spy_atr': r['spy_atr'], 'U': r['U'], 'dv': None} for r in ok]
    st, bs, n = cs.run_port(trades, spy)
    sf, _, nf = cs.run_port(trades, spy, flat=True)
    print(ps.fmt_stats('SIZED system', st, f'  trades {n}'))
    print(ps.fmt_stats('FLAT 1.0U', sf, f'  trades {nf}'))
    print(ps.fmt_stats('SPY buy and hold', bs))
    beta, alpha = ps.beta_alpha(st['r'], bs['r'])
    print(f'  beta to SPY {beta:.2f}; alpha {alpha:+.2%} a year (daily regression); max drawdown {st["mdd"]:+.1%} ({st["mdd_peak"]} to {st["mdd_trough"]}) vs SPY {bs["mdd"]:+.1%}')
    a = alpha > 0
    b = st['sharpe'] > sf['sharpe'] and st['calmar'] > sf['calmar']
    c = st['mdd'] > bs['mdd']
    print(f'  (a) alpha > 0: {a}; (b) Sharpe {st["sharpe"]:.2f} vs flat {sf["sharpe"]:.2f} AND Calmar {st["calmar"]:.2f} vs flat {sf["calmar"]:.2f}: {b}; (c) max drawdown shallower than SPY: {c}')
    h1 = 'PASS' if (a and b and c) else ('FAIL' if not a else 'NOT SHOWN')
    print(f'  H1 RESULT: {h1}')

    print('\n=== H2 and H3: signal tests, 21-session hold, no stop, net of 0.10 ATR ===')
    p2, v2 = group_test('H2 deep fall (12-month fall of 15 ATR or more)', ok, lambda r: -r['raw252'] >= FALL_DEEP)
    p3, v3 = group_test('H3 Nasdaq lagging (ONEQ minus SPY over 63 sessions <= %.4f)' % N_CUT, ok, lambda r: r['N'])
    ps_ = [p for p in (p2, p3) if p is not None]
    adj = bh_adjust(ps_) if ps_ else []
    print(f'\nBenjamini-Hochberg adjusted chances (H2, H3 where run): raw {[round(p, 4) for p in ps_]} -> adjusted {[round(x, 4) for x in adj]}')
    res = {}
    for name, p, v, flag in (('H2', p2, v2, lambda r: -r['raw252'] >= FALL_DEEP), ('H3', p3, v3, lambda r: r['N'])):
        if v:
            res[name] = v
            continue
        g = [r['ex21'] - COST for r in ok if flag(r)]
        rest = [r['ex21'] - COST for r in ok if not flag(r)]
        res[name] = 'PASS' if (statistics.fmean(g) > 0 and statistics.fmean(g) > statistics.fmean(rest) and p <= 0.10) else 'FAIL'
    print(f'\n=== RESULTS (pass rules exactly as frozen): H1 {h1}; H2 {res["H2"]}; H3 {res["H3"]} ===')
    print('Not changed after this run: sizes, cutoffs, stop, hold, cost. The sealed years are now spent for this idea.')


def selftest():
    rng = np.random.default_rng(3)
    vals = list(rng.normal(0, 1, 200))
    lab = [i % 4 == 0 for i in range(200)]
    for i in range(200):
        if lab[i]:
            vals[i] += 1.5
    weeks = [(2021, i // 5) for i in range(200)]
    obs, p = shuffle_chance(vals, lab, weeks, draws=500)
    assert obs > 1.0 and p < 0.01, (obs, p)
    obs, p = shuffle_chance(list(rng.normal(0, 1, 200)), lab, weeks, draws=500)
    assert p > 0.05, p
    lo, hi = week_block_range(vals, weeks, draws=500)
    assert lo < hi
    adj = bh_adjust([0.01, 0.04])
    assert abs(adj[0] - 0.02) < 1e-12 and abs(adj[1] - 0.04) < 1e-12, adj
    u, r1, n = size_u({'ceo': False, 'cfo': False, 'lead63': -0.05, 'raw252': -25.0})
    assert abs(u - (1 + 0.2 + 1.0 + 0.11 * 12)) < 1e-9 and r1 and n, u
    u, r1, n = size_u({'ceo': True, 'cfo': False, 'lead63': 0.01, 'raw252': -5.0})
    assert u == 1.0 and not r1 and not n
    print('sealed_run selftest ok: shuffle test detects a planted effect and not noise, week-block range, Benjamini-Hochberg, declared size rule')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    elif sys.argv[1] == 'check':
        years = [int(x) for x in sys.argv[2].split(',')]
        check(years, *sys.argv[3:])
    elif sys.argv[1] == 'year':
        sealed_year(int(sys.argv[2]), *sys.argv[3:])
    elif sys.argv[1] == 'analyze':
        analyze(sys.argv[2])
