"""C37 (POST HOC, Michael 9 Nov 2026: "how many trades per month on average there is for each combination of flags"): counts of four-buyer signals by every
combination of the four sizing flags R1, N, F, P, with trades per month, mean excess, and the continuous size from Entry 78 at HALF the earlier risk.

Development years only (entries <= 2020-12-31, D-068); no sealed return is read. Same inputs, cohort and flag definitions as Entry 67 (deepfall_2x2.py, imported
unchanged for the join and the flags): cohort = development events with roles, lead63, raw252 and dd252 (n=1,273 in Entries 66-67, of 1,372 base events; the
other 99 lack a feature and cannot be flagged). Excess = stock minus same-window SPY over 21 sessions in the stock's ATR units, stock and SPY legs shown (D-053).
No costs. Returns code PROVISIONAL as in Entry 28. 180 development months (2006-2020).

DECLARED BEFORE RUNNING:
  Flags: R1 = neither CEO nor CFO among the buyers; N = Nasdaq lagging SPY (lowest fifth of lead63); F = raw252 <= -15.0 ATR; P = dd252 >= 50%.
  A. For each of the 16 combinations (R1, N, F, P): n, trades per month (n / 180), mean excess with stock and SPY legs. Then the same for the 8 combinations
     of (R1, N, F) alone, and for each single flag with and without.
  B. Size from sizing_weights.py (Entry 78, Entry 67 model): total U = 1.0 + add-ons of the flags that are on; risk per ATR = total U x 0.125% (Michael,
     9 Nov 2026: base risk cut in half, so U = 0.125% of equity per 1 ATR). Per combination: total U, risk per ATR, and the monthly sum of U (n/180 x total U).
  C. Totals: signals per month in the cohort, mean U per signal, and the average number of positions open at once if each is held 21 sessions (about one
     month): trades per month x 1.0 (a rough count, overlapping entries are not simulated here).
Cautions written in advance: the combinations are cut after seeing Entries 51, 66 and 67, so every cell is post hoc; several cells are tiny (do not read a
mean off n under 30); P and F overlap heavily so P-without-F and F-without-P are thin; the continuous sizes are judgment on post hoc inputs.

Usage:  python flag_combo_counts.py EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER DD_FOLDER   |   --selftest
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drawdown_scan as dd
import score_scan as ss
import deepfall_2x2 as d2
import sizing_weights as sw

MONTHS = 180
HALF_U = 0.125          # percent of equity per 1 ATR for 1.0U (Michael, 9 Nov 2026)
FLAGS = ['R1', 'N', 'F', 'P']


def combos(cohort, keys):
    for combo in itertools.product((0, 1), repeat=len(keys)):
        yield combo, [r for r in cohort if tuple(int(bool(r[k])) for k in keys) == combo]


def size_u(add, keys, combo):
    return 1.0 + sum(add[k] for k, on in zip(keys, combo) if on)


def label(keys, combo):
    on = [k for k, c in zip(keys, combo) if c]
    return '+'.join(on) if on else 'cluster only'


def report(cohort):
    add = {k: v['add_U'] for k, v in sw.weights(sw.MODELS['Entry 67 (R1+N+P+F)']).items()}
    print('add-ons in U (Entry 78, Entry 67 model): ' + ', '.join(f'{k} {v:+.2f}' for k, v in add.items()))
    print(f'U = {HALF_U}% of equity per 1 ATR (half of the earlier 0.25%); cohort n={len(cohort)}; {MONTHS} development months')

    print('\n=== A/B. All 16 combinations of R1, N, F, P ===')
    print('  combination        n   per month   total U  risk %/ATR  U per month | excess (stock / SPY)')
    tot_u = 0.0
    for combo, g in combos(cohort, FLAGS):
        u = size_u(add, FLAGS, combo)
        pm = len(g) / MONTHS
        tot_u += len(g) * u
        print(f'  {label(FLAGS, combo):14s} {len(g):5d}   {pm:7.2f}    {u:5.2f}   {u * HALF_U:7.3f}%   {pm * u:8.2f}   | {dd.line(g) if g else "no events"}')

    print('\n=== A2. The 8 combinations of R1, N, F alone (P ignored) ===')
    print('  combination        n   per month | excess (stock / SPY)')
    for combo, g in combos(cohort, ['R1', 'N', 'F']):
        print(f'  {label(["R1", "N", "F"], combo):14s} {len(g):5d}   {len(g) / MONTHS:7.2f}   | {dd.line(g) if g else "no events"}')

    print('\n=== A3. Each flag on and off (any other flags) ===')
    for k in FLAGS:
        g = [r for r in cohort if r[k]]
        go = [r for r in cohort if not r[k]]
        print(f'  {k} on : n={len(g)}, {len(g) / MONTHS:.2f} per month | {dd.line(g)}')
        print(f'  {k} off: n={len(go)}, {len(go) / MONTHS:.2f} per month | {dd.line(go)}')

    print('\n=== C. Totals ===')
    n = len(cohort)
    print(f'  signals in cohort {n}, {n / MONTHS:.2f} per month; mean size {tot_u / n:.2f}U per signal (risk {tot_u / n * HALF_U:.3f}% per ATR); '
          f'U-months per month {tot_u / MONTHS:.2f}')
    print(f'  rough open positions at once with a 21-session (about one month) hold: {n / MONTHS:.1f} signals a month -> about {n / MONTHS:.1f} open on average '
          f'(overlap and crash clustering NOT simulated)')


def scan(events, years, decl, regime, ret, dd_folder):
    dev0 = ss.build(events, years, decl, regime, ret)
    dev, atr_diff = dd.load_dd(dd_folder, dev0)
    if atr_diff:
        print('WARNING: entry ATR does not match the Entry 36 file for some rows; PROVISIONAL until explained')
    cohort = [r for r in dev if 'dd252' in r]
    for r in cohort:
        d2.flags(r)
    report(cohort)


def selftest():
    rows = [dict(R1=a, N=b, F=c, P=d, excess_atr=0.0) for a in (0, 1) for b in (0, 1) for c in (0, 1) for d in (0, 1) for _ in range(2)]
    seen = 0
    for combo, g in combos(rows, FLAGS):
        assert len(g) == 2, (combo, len(g))
        seen += len(g)
    assert seen == len(rows)
    add = {'R1': 0.1, 'N': 0.8, 'F': 0.5, 'P': 0.3}
    assert abs(size_u(add, FLAGS, (1, 1, 0, 0)) - 1.9) < 1e-9
    assert label(FLAGS, (0, 0, 0, 0)) == 'cluster only' and label(FLAGS, (1, 1, 0, 0)) == 'R1+N'
    print('flag_combo_counts self-test passed')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    else:
        scan(*sys.argv[1:7])
