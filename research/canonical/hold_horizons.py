"""Longer holding periods (3, 6, 9, 12 months = 63, 126, 189, 252 sessions) for the two live leads (Entry 43).

Question (Michael, 8 Nov 2026): do the C8 12-month-fall lead and the C16 lead63 (Nasdaq lagging) lead keep paying if the position is held 3, 6, 9 or 12
months instead of 21 sessions, and what happens to the trade count and the survivorship exposure?

POST HOC: asked after seeing the 21-session results (Entries 36-42), so everything here is exploratory. Development years only (entries <= 2020-12-31, D-068).
Returns for each hold come from `refined_baseline.py year ... --hold H` (same entry rule, ATR and same-window-SPY definitions as Entry 28, price only, no costs,
entry session = day one, exit = close of session H counting the entry session). D-068 reads the ENTRY date: a 2020 entry held 252 sessions exits in late 2021, so
2021 prices of development-year stocks and SPY are used for exits (no 2021-2025 ENTRY return is computed). Pilot (2026) not used.

Cohort and groups are fixed once, from the Entry 41 cohort (development events with lead63, all four decline measures and a complete 21-session return;
n must be 1,273; lead63 cut points -0.0195 / +0.0391; raw252 fifths) and are NOT recomputed per horizon, so every horizon is the same set of events.
Groups: ALL; FELL = lowest fifth of raw252 (fell most over 12 months); LEAST = highest fifth; Q1 = lowest fifth of lead63 (Nasdaq lagging); BOTH = FELL and Q1;
EITHER = FELL or Q1; NEITHER.  Reference row: the 21-session hold, from the Entry 28 returns.

Declared before any long-hold return was computed:
  A. Census.  Return status (complete / incomplete = stock series ended before the exit, last close used / open / missing) per horizon, overall and for FELL vs the rest.
  B. Table, complete trades only.  Per horizon x group: n, entry weeks, spells (42-day rule), mean and median excess over same-window SPY in ATR with the stock and SPY legs, share
     beating SPY, plain-percent legs (mean stock, mean SPY, median percent excess), quarter-block and calendar-year-block 95% range of the mean excess (10,000 draws).
  C. Same table, complete + incomplete (delisted/acquired names priced at their last close). This is the survivorship sensitivity: complete-only drops every name that
     stopped trading inside the hold, and that share grows with the hold.
  D. Constant cohort: events complete at all four long horizons; mean excess per horizon and the increment between horizons for ALL, FELL, Q1, BOTH (does the edge keep accumulating
     or stop early?).
  E. Chance tests (the only ones): Spearman(raw252, excess) with excess shuffled inside the same entry week (10,000 draws, as Entry 36), at 63, 126, 189, 252 sessions,
     for complete-only (4 tests, the menu) and complete+incomplete (4 sensitivity tests).
  F. Trade counts: events per year and average open positions (events per year x hold / 252) for ALL, FELL, Q1, BOTH, EITHER.
  G. (ADDED after the first run, 42504935934, showed a mean of about +5,000 ATR at 189 and 252 sessions that no real trade can produce: a data-quality diagnostic, not a new
     hypothesis.) Per horizon, the 8 largest and 8 smallest complete trades by excess with symbol, entry, exit, entry open, ATR, stock % and SPY %, and a count of trades with
     |stock %| over 1,000%.
  H. (ADDED, same reason.) Mean excess by group with the excess clipped at the 1st and 99th percentile of that horizon's complete trades, beside the unclipped mean.
Overlap warning, printed with the results: holds of 63-252 sessions starting in the same period overlap almost completely, so the number of independent observations is far
smaller than n; the quarter-block and year-block ranges narrow this only partly. Nothing here is a test of a rule.
Not done on purpose: a different entry rule, stops, costs, the 2026 pilot, any new cut point, a 2011-2020 subset (can be added with --start if asked).
Questions on the tally: 5 horizons x 7 groups x 2 variants of means (70), 8 chance tests, descriptive census, constant-cohort and trade-count tables.

SUBSET RERUN (Entry 45; declared 8 Nov 2026 BEFORE any subset number was computed; asked in the Entry 43 "Next"): `subsets` command. POST HOC, exploratory.
Same cohort, same returns runs and same holds as Entry 43. Three subsets of the 1,273-event cohort:
  S1  without the three large episodes (entry quarters 2008Q4, 2011Q3, 2020Q1), all years;
  S2  entries from 2011-01-01 only (the Entry 42 subset, missing-price share 5-15%);
  S3  S2 and also without 2011Q3 and 2020Q1 (2008Q4 is outside S2).
Each subset is run two ways: FIXED = FELL/Q1 labels kept exactly as in Entry 43 (cut points from the full cohort), so only the events change; RECUT = fifths and the
lead63 cut points recomputed inside the subset (as Entry 42 did). 3 subsets x 2 = 6 passes. Per pass, only these sections (the ones named in the Entry 43 Next):
  B. complete-only table per hold x group (stock and SPY legs, percent legs, quarter- and year-block ranges), as Entry 43 section B;
  D. constant cohort (events complete at all horizons) with increments;
  E. week-shuffle chance tests, Spearman(raw252, excess), complete-only and complete+incomplete (8 per pass);
  H. clipped means (the SUNE ticker-reuse row, SunEdison 2015-08-26, is in every subset that holds 2011-2020; ALL and NEITHER unclipped at 189 and 252 are INVALID,
     use clipped means or medians; FELL/Q1/BOTH/EITHER are unaffected).
Not run: census, complete+incomplete tables, trade counts, extreme-trade lists (unchanged logic, see Entry 43). No new cut point, no 2021-2025 entry, no pilot.
Tally: 6 passes x 5 holds x 7 groups = 210 group means (B), 6 constant-cohort rows sets, 48 chance tests, 210 clipped means.
Usage (subsets):  python hold_horizons.py subsets DECLINE REGIME RET21 RET63 RET126 RET189 RET252

TWO-MONTH HOLD (Entry 47; declared 8 Nov 2026 BEFORE any 42-session return was computed; asked by Michael: "put something between 21 and 63"). POST HOC, exploratory.
New hold = 42 sessions (about 2 months; entry session = day one, exit = close of session 42), same entry rule, ATR and same-window-SPY definitions as Entry 28, price only.
Returns from `refined_baseline.py year ... --hold 42` (workflow refined-baseline-hold.yml, hold=42). `mid` command compares 21, 42 and 63 sessions only, on four sets of the
Entry 41 cohort with FELL/Q1 labels FIXED as in Entry 43 (no recut): FULL (n=1,273), S1 (without 2008Q4, 2011Q3, 2020Q1), S2 (entries from 2011-01-01), S3 (S2 without 2011Q3 and 2020Q1).
Per set: B complete-only table with block ranges; D constant cohort with increments; E week-shuffle chance, Spearman(raw252, excess), complete-only and complete+incomplete;
H clipped means. Also printed per set: excess per 21 sessions of capital tied up (mean excess / (hold/21)) for ALL, FELL, Q1, so holds can be compared per unit of time.
Not run: 126 and longer (Entry 46), recut labels, new cut points, costs, any 2021-2025 entry, the pilot.
Tally: 4 sets x 3 holds x 7 groups = 84 group means (B), 84 clipped means, 4 x 6 = 24 chance tests, 4 constant-cohort row sets, 12 per-time rows.
Usage (mid):  python hold_horizons.py mid DECLINE REGIME RET21 RET42 RET63

Usage:  python hold_horizons.py run DECLINE REGIME RET21 RET63 RET126 RET189 RET252 | --selftest
"""
import argparse, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, assert_allowed, quarter
import factor_decline as fd
import factor_regime as fg
import factor_cross as fc

HOLDS = (21, 63, 126, 189, 252)
LONG = HOLDS[1:]
GROUPS = ('ALL', 'FELL', 'LEAST', 'Q1', 'BOTH', 'EITHER', 'NEITHER')
SEED = 20261108
KEYS = ('status', 'stock_atr', 'spy_atr', 'excess_atr', 'stock_pct', 'spy_pct')
YEARS_OF_DATA = 15   # 2006-2020


def key(r):
    return (r['cik'], r['sym'], r['entry'])


def read_returns(folder):
    out = {}
    for p in sorted(Path(folder).glob('returns_*.json')):
        for r in json.loads(p.read_text())['rows']:
            assert_allowed(r['entry'])
            out[key(r)] = r
    return out


def member(r, g):
    f, q = r['g_raw252'] == 'most', r['band'] == 'Q1'
    return {'ALL': True, 'FELL': f, 'LEAST': r['g_raw252'] == 'least', 'Q1': q, 'BOTH': f and q, 'EITHER': f or q, 'NEITHER': not (f or q)}[g]


def build_cohort(decline, regime, ret21):
    import numpy as np
    dev, _ = fc.load_joined(decline, regime, ret21)
    x = np.array([r['lead63'] for r in dev])
    lo, hi = np.quantile(x, [0.2, 0.8])
    for r, b in zip(dev, fc.bands(x, lo, hi)):
        r['band'] = b
    for r, g in zip(dev, fc.groups([r['raw252'] for r in dev])):
        r['g_raw252'] = g
    print(f'cohort: {len(dev)} development events (Entry 41: 1,273); lead63 cut points {lo:+.4f} / {hi:+.4f} (Entry 41: -0.0195 / +0.0391)')
    if len(dev) != 1273 or abs(lo + 0.0195) > 0.0006 or abs(hi - 0.0391) > 0.0006:
        print('WARNING: cohort does not reproduce Entry 41; treat everything below as PROVISIONAL until explained')
    return dev


def rows_for(cohort, rets, statuses):
    out = []
    for c in cohort:
        r = rets.get(key(c))
        if r and r['status'] in statuses:
            out.append({**c, **{k: r[k] for k in KEYS if k in r}})
    return out


def block_range(rs, keyf, draws=10000):
    import numpy as np
    blocks = defaultdict(list)
    for r in rs:
        blocks[keyf(r)].append(r['excess_atr'])
    if len(blocks) < 3:
        return None
    sums = np.array([sum(v) for v in blocks.values()])
    cnts = np.array([len(v) for v in blocks.values()], dtype=float)
    idx = np.random.default_rng(SEED).integers(0, len(sums), size=(draws, len(sums)))
    m = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(lo), float(hi), len(blocks)


def line(rs):
    if not rs:
        return 'n=0'
    ex = [r['excess_atr'] for r in rs]
    ds = sorted(r['entry'] for r in rs)
    s = (f'n={len(rs):4d} {len({fd.week_of(r) for r in rs}):3d}w {len(fg.spells(ds)):2d}sp  excess {statistics.fmean(ex):+.3f} median {statistics.median(ex):+.3f} '
         f'[stock {statistics.fmean(r["stock_atr"] for r in rs):+.3f} SPY {statistics.fmean(r["spy_atr"] for r in rs):+.3f}] '
         f'beat SPY {sum(x > 0 for x in ex) / len(ex):.0%}')
    if all('stock_pct' in r for r in rs):
        pe = [r['stock_pct'] - r['spy_pct'] for r in rs]
        s += (f' | pct: stock {statistics.fmean(r["stock_pct"] for r in rs):+.1%} SPY {statistics.fmean(r["spy_pct"] for r in rs):+.1%} '
              f'median excess {statistics.median(pe):+.1%}')
    if len(rs) < 15:
        s += '  (n<15, not interpreted)'
    return s


def ranges(rs):
    q = block_range(rs, lambda r: r['entry'][:4] + str((int(r['entry'][5:7]) - 1) // 3))
    y = block_range(rs, lambda r: r['entry'][:4])
    t = lambda b, nm: f'{nm}-block [{b[0]:+.3f}, {b[1]:+.3f}] ({b[2]} blocks)' if b else f'{nm}-block n/a'
    return '      ' + t(q, 'quarter') + '   ' + t(y, 'year')


def table(cohort, rets_by_hold, statuses, title, holds=HOLDS):
    print(f'\n=== {title} ===')
    for h in holds:
        rows = rows_for(cohort, rets_by_hold[h], statuses)
        print(f'-- hold {h} sessions (about {round(h / 21)} months)')
        for g in GROUPS:
            rs = [r for r in rows if member(r, g)]
            print(f'  {g:8s} {line(rs)}')
            if rs and g in ('ALL', 'FELL', 'Q1', 'BOTH'):
                print(ranges(rs))


def census(cohort, rets_by_hold):
    print('\n=== A. Census of outcome status in the cohort (complete / incomplete = stock series ended before the exit / open / other) ===')
    for h in HOLDS:
        rets = rets_by_hold[h]
        def cnt(sel):
            c = Counter((rets[key(r)]['status'] if key(r) in rets else 'no_row') for r in sel)
            n = len(sel)
            return f'n={n} complete {c.get("complete", 0)} ({c.get("complete", 0) / n:.1%}) incomplete {c.get("incomplete", 0)} ({c.get("incomplete", 0) / n:.1%}) ' \
                   f'other {n - c.get("complete", 0) - c.get("incomplete", 0)}'
        print(f'  hold {h:3d}: ALL {cnt(cohort)}')
        print(f'            FELL {cnt([r for r in cohort if member(r, "FELL")])}')
        print(f'            rest {cnt([r for r in cohort if not member(r, "FELL")])}')


def constant(cohort, rets_by_hold, holds=HOLDS):
    print('\n=== D. Constant cohort: events complete at ALL of 63, 126, 189, 252 sessions (plus 21); mean excess (ATR) and increment from the previous horizon ===')
    keep = [c for c in cohort if all(key(c) in rets_by_hold[h] and rets_by_hold[h][key(c)]['status'] == 'complete' for h in holds)]
    print(f'  {len(keep)} of {len(cohort)} events')
    for g in ('ALL', 'FELL', 'Q1', 'BOTH'):
        sub = [c for c in keep if member(c, g)]
        means = [statistics.fmean(rets_by_hold[h][key(c)]['excess_atr'] for c in sub) if sub else float('nan') for h in holds]
        inc = [means[0]] + [means[i] - means[i - 1] for i in range(1, len(holds))]
        print(f'  {g:5s} n={len(sub):4d}  ' + '  '.join(f'{h}:{m:+.3f}' for h, m in zip(holds, means)) + '   increments ' + '  '.join(f'{h}:{d:+.3f}' for h, d in zip(holds, inc)))


def chance(cohort, rets_by_hold, holds=HOLDS):
    print('\n=== E. Spearman(raw252, excess), excess shuffled inside the same entry week (negative = deeper 12-month fall, better excess) ===')
    for label, st in (('complete only (menu)', {'complete'}), ('complete + incomplete (sensitivity)', {'complete', 'incomplete'})):
        for h in holds:
            rows = rows_for(cohort, rets_by_hold[h], st)
            obs, p, n = fd.perm_rho(rows, 'raw252', 'excess_atr')
            print(f'  {label:36s} hold {h:3d}: rho {obs:+.3f}, chance {p:.2%} (n={n})')


def counts(cohort):
    print(f'\n=== F. Trade counts: events per year over {YEARS_OF_DATA} development years, and average open positions (events/yr x hold / 252) ===')
    for g in ('ALL', 'FELL', 'Q1', 'BOTH', 'EITHER'):
        n = sum(member(r, g) for r in cohort)
        per = n / YEARS_OF_DATA
        print(f'  {g:7s} {n:4d} events, {per:5.1f}/yr, {per / 12:4.2f}/month; open positions at hold ' + ', '.join(f'{h}: {per * h / 252:4.1f}' for h in HOLDS))


def outliers(cohort, rets_by_hold):
    print('\n=== G. Extreme trades (complete, cohort members): largest and smallest excess; entry open, exit date, ATR, stock % and SPY % ===')
    for h in HOLDS:
        rows = [(rets_by_hold[h][key(c)], c) for c in cohort if key(c) in rets_by_hold[h] and rets_by_hold[h][key(c)]['status'] == 'complete']
        rows.sort(key=lambda t: t[0]['excess_atr'])
        big = [t for t in rows if abs(t[0].get('stock_pct', 0.0)) > 10]
        print(f'-- hold {h}: {len(rows)} trades; |stock %| > 1,000%: {len(big)}')
        for label, sel in (('largest', rows[-8:][::-1]), ('smallest', rows[:8])):
            for r, c in sel:
                pct = f'{r["stock_pct"]:+.1%}' if 'stock_pct' in r else 'n/a'
                print(f'   {label:8s} {r["sym"]:10s} entry {r["entry"]} exit {r.get("exit")} open {r["entry_open"]:.4f} ATR {r["atr"]:.5f} stock {pct} excess {r["excess_atr"]:+.1f} ATR  FELL={member(c, "FELL")} Q1={member(c, "Q1")}')


def winsor(cohort, rets_by_hold, holds=HOLDS):
    import numpy as np
    print('\n=== H. Mean excess (ATR), unclipped vs clipped at the 1st and 99th percentile of the horizon\'s complete trades ===')
    for h in holds:
        rows = rows_for(cohort, rets_by_hold[h], {'complete'})
        lo, hi = np.percentile([r['excess_atr'] for r in rows], [1, 99])
        out = []
        for g in GROUPS:
            rs = [r for r in rows if member(r, g)]
            if rs:
                out.append(f'{g} {statistics.fmean(r["excess_atr"] for r in rs):+.3f}/{statistics.fmean(min(max(r["excess_atr"], lo), hi) for r in rs):+.3f}')
        print(f'  hold {h:3d} (clip {lo:+.2f} to {hi:+.2f}): ' + '  '.join(out))


def run(decline, regime, ret21, *long_folders):
    cohort = build_cohort(decline, regime, ret21)
    rets = {21: read_returns(ret21)}
    for h, f in zip(LONG, long_folders):
        rets[h] = read_returns(f)
        print(f'hold {h}: {len(rets[h])} return rows read from {f}')
    print('OVERLAP WARNING: long holds that start in the same period overlap almost completely; independent observations are far fewer than n.')
    census(cohort, rets)
    table(cohort, rets, {'complete'}, 'B. Complete trades only; excess over same-window SPY in ATR (stock and SPY legs beside it)')
    table(cohort, rets, {'complete', 'incomplete'}, 'C. Complete + incomplete (delisted/acquired priced at the last close)')
    constant(cohort, rets)
    chance(cohort, rets)
    counts(cohort)
    outliers(cohort, rets)
    winsor(cohort, rets)
    print('\nQuestions asked on this cohort in this entry: see the docstring tally (post hoc, exploratory).')


SUBSETS = (('S1 without 2008Q4, 2011Q3, 2020Q1 (all years)', None, EPISODES),
           ('S2 entries from 2011-01-01', '2011-01-01', ()),
           ('S3 entries from 2011-01-01 without 2011Q3 and 2020Q1', '2011-01-01', ('2011Q3', '2020Q1')))


def subset_cohort(full, start, drop_quarters, recut):
    import numpy as np
    sub = [dict(r) for r in full if (not start or r['entry'] >= start) and quarter(r['entry']) not in drop_quarters]
    if recut and sub:
        x = np.array([r['lead63'] for r in sub])
        lo, hi = np.quantile(x, [0.2, 0.8])
        for r, b in zip(sub, fc.bands(x, lo, hi)):
            r['band'] = b
        for r, g in zip(sub, fc.groups([r['raw252'] for r in sub])):
            r['g_raw252'] = g
        print(f'  recut: lead63 cut points {lo:+.4f} / {hi:+.4f}')
    return sub


def run_subsets(decline, regime, ret21, *long_folders):
    full = build_cohort(decline, regime, ret21)
    rets = {21: read_returns(ret21)}
    for h, f in zip(LONG, long_folders):
        rets[h] = read_returns(f)
        print(f'hold {h}: {len(rets[h])} return rows read from {f}')
    print('OVERLAP WARNING: long holds that start in the same period overlap almost completely; independent observations are far fewer than n.')
    for name, start, drop in SUBSETS:
        for recut in (False, True):
            print(f'\n########## {name} | groups {"RECUT inside the subset" if recut else "FIXED as in Entry 43"} ##########')
            sub = subset_cohort(full, start, drop, recut)
            print(f'  n={len(sub)} of {len(full)}; ' + ', '.join(f'{g} {sum(member(r, g) for r in sub)}' for g in GROUPS))
            table(sub, rets, {'complete'}, 'B. Complete trades only; excess over same-window SPY in ATR')
            constant(sub, rets)
            chance(sub, rets)
            winsor(sub, rets)
    print('\nQuestions asked in this entry: see the docstring tally (post hoc, exploratory).')


MID = (21, 42, 63)


def run_mid(decline, regime, ret21, ret42, ret63):
    full = build_cohort(decline, regime, ret21)
    rets = {21: read_returns(ret21), 42: read_returns(ret42), 63: read_returns(ret63)}
    for h in (42, 63):
        print(f'hold {h}: {len(rets[h])} return rows read')
    print('OVERLAP WARNING: holds that start in the same period overlap; independent observations are far fewer than n.')
    sets = (('FULL cohort (all years)', None, ()),) + SUBSETS
    for name, start, drop in sets:
        print(f'\n########## {name} | labels FIXED as in Entry 43 ##########')
        sub = subset_cohort(full, start, drop, False)
        print(f'  n={len(sub)} of {len(full)}; ' + ', '.join(f'{g} {sum(member(r, g) for r in sub)}' for g in GROUPS))
        table(sub, rets, {'complete'}, 'B. Complete trades only; excess over same-window SPY in ATR', MID)
        constant(sub, rets, MID)
        chance(sub, rets, MID)
        winsor(sub, rets, MID)
        print('  per 21 sessions of capital tied up (mean excess / (hold/21)), complete only:')
        for g in ('ALL', 'FELL', 'Q1'):
            cells = []
            for h in MID:
                rs = [r for r in rows_for(sub, rets[h], {'complete'}) if member(r, g)]
                cells.append(f'{h}: {statistics.fmean(r["excess_atr"] for r in rs) / (h / 21):+.3f}' if rs else f'{h}: n/a')
            print(f'    {g:5s} ' + '   '.join(cells))
    print('\nQuestions asked in this entry: see the docstring tally (post hoc, exploratory).')


def selftest():
    rs = [{'entry': f'20{10 + k % 5}-0{1 + k % 9}-1{k % 9}', 'excess_atr': float(k % 7) - 2.0, 'stock_atr': 1.0, 'spy_atr': 0.5, 'stock_pct': 0.10, 'spy_pct': 0.05,
           'g_raw252': 'most' if k % 5 == 0 else 'mid', 'band': 'Q1' if k % 3 == 0 else 'mid'} for k in range(90)]
    assert sum(member(r, 'FELL') for r in rs) == 18 and sum(member(r, 'BOTH') for r in rs) == 6
    assert sum(member(r, 'EITHER') for r in rs) == 18 + 30 - 6 and sum(member(r, 'NEITHER') for r in rs) == 90 - 42
    lo, hi, nb = block_range(rs, lambda r: r['entry'][:4])
    assert lo < statistics.fmean(r['excess_atr'] for r in rs) < hi and nb == 5
    assert block_range([rs[0], rs[5]], lambda r: r['entry'][:4]) is None
    assert 'pct:' in line(rs) and 'n=  90' in line(rs)
    sub = subset_cohort([{**r, 'lead63': float(i), 'raw252': float(-i)} for i, r in enumerate(rs)], '2012-01-01', ('2013Q1',), True)
    assert sub and all(r['entry'] >= '2012-01-01' and quarter(r['entry']) != '2013Q1' for r in sub) and any(member(r, 'FELL') for r in sub)
    print('hold_horizons self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('folders', nargs='+')
    a = ap.parse_args()
    if a.cmd == 'run' and len(a.folders) == 7:
        run(*a.folders)
    elif a.cmd == 'mid' and len(a.folders) == 5:
        run_mid(*a.folders)
    elif a.cmd == 'subsets' and len(a.folders) == 7:
        run_subsets(*a.folders)
    else:
        raise SystemExit(__doc__)
