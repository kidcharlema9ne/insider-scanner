"""Why does the refined pilot (Entry 28: 80 trades, +0.333) differ from the Entry 8 pilot (91 liquid trades, +0.5257)?

Two questions, answered separately:
  1. DEFINITION: take the Entry 8 trades as they are and recompute each with refined_baseline.trade_outcome from the
     archive. If the code and the data agree, the per-trade difference is near zero.
  2. COHORT: which Entry 8 trades are missing from the refined primary set, why (D-064, identity, floor, option C),
     and which refined trades are new.
Only 2026 entries (the in-sample pilot) are touched; refined_baseline.assert_allowed would block anything else.

Usage: python reconcile_pilot.py OLD.json RETURNS_2026.json YEAR_2026.json
"""
import json, statistics, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import load_span, trade_outcome
from refined_study import FINE

m = lambda xs: statistics.fmean(xs) if xs else float('nan')


def near(day, other, k=5):
    return abs((date.fromisoformat(day) - date.fromisoformat(other)).days) <= k


def main(old_path, new_path, year_path):
    from r2_storage import client
    from archive_coverage_audit import DELISTED
    old = json.loads(Path(old_path).read_text())
    new = [r for r in json.loads(Path(new_path).read_text())['rows'] if r['status'] == 'complete']
    ev = json.loads(Path(year_path).read_text())['results']
    old_liq = [t for t in old if t['liquid']]
    print(f'old cohort: {len(old)} completed, {len(old_liq)} liquid, mean excess {m([t["excess_atr"] for t in old_liq]):+.4f}')
    print(f'new primary pilot (complete): {len(new)}, mean excess {m([r["excess_atr"] for r in new]):+.4f}')

    s3 = client()
    want = {t['ticker'].upper() for t in old} | {t['ticker'].upper() + DELISTED for t in old}
    bars, dates = load_span(s3, 'stock', [2026], want, 25, 30)
    spy = load_span(s3, 'etf', [2026], {'SPY'}, 25, 30)[0].get('SPY', {})

    print('\n=== 1. DEFINITION CHECK: Entry 8 trades recomputed with the new code from the archive (all 137) ===')
    diffs, recomputed = [], {}
    for t in old:
        sym = t['ticker'].upper()
        series = dict(bars.get(sym, {})) or dict(bars.get(sym + DELISTED, {}))
        r = trade_outcome(dates, series, spy, t['entry'])
        recomputed[(sym, t['entry'])] = r
        if r['status'] == 'complete':
            diffs.append((r['excess_atr'] - t['excess_atr'], t, r))
    print(f'recomputed complete: {len(diffs)} of {len(old)}; statuses {dict(Counter(r["status"] for r in recomputed.values()))}')
    for label, sel in (('all', diffs), ('liquid', [d for d in diffs if d[1]['liquid']])):
        ds = [d[0] for d in sel]
        print(f'{label}: n={len(ds)}  old mean {m([d[1]["excess_atr"] for d in sel]):+.4f}  new-code mean {m([d[2]["excess_atr"] for d in sel]):+.4f}  '
              f'mean diff {m(ds):+.4f}  mean |diff| {m([abs(x) for x in ds]):.4f}  max |diff| {max((abs(x) for x in ds), default=0):.3f}  '
              f'|diff|>0.05: {sum(abs(x) > 0.05 for x in ds)}')
        print(f'   entry open ratio new/old: median {statistics.median(d[2]["entry_open"] / d[1]["entry_open"] for d in sel):.4f}, '
              f'ATR ratio median {statistics.median(d[2]["atr"] / d[1]["atr14"] for d in sel):.4f}')
    worst = sorted(diffs, key=lambda d: -abs(d[0]))[:8]
    print('largest differences (ticker entry old new): ' + '; '.join(f'{d[1]["ticker"]} {d[1]["entry"]} {d[1]["excess_atr"]:+.2f} {d[2]["excess_atr"]:+.2f}' for d in worst))

    print('\n=== 2. COHORT CHECK ===')
    newkey = {(r['sym'].upper(), r['entry']): r for r in new}
    oldkey = {(t['ticker'].upper(), t['entry']): t for t in old_liq}
    both = [k for k in oldkey if k in newkey]
    only_old = [k for k in oldkey if k not in newkey]
    only_new = [k for k in newkey if k not in oldkey]
    print(f'both {len(both)}; old liquid only {len(only_old)}; new only {len(only_new)}')
    print(f'both:     old values {m([oldkey[k]["excess_atr"] for k in both]):+.4f}   new values {m([newkey[k]["excess_atr"] for k in both]):+.4f}')
    print(f'old only: old values {m([oldkey[k]["excess_atr"] for k in only_old]):+.4f}   (n={len(only_old)})')
    print(f'new only: new values {m([newkey[k]["excess_atr"] for k in only_new]):+.4f}   (n={len(only_new)})')

    by = defaultdict(list)
    for e in ev:
        by[(e['sym'].upper(), e['entry'])].append(e)
    primary_keys = set(newkey)
    why = defaultdict(list)
    for k in only_old:
        rs = by.get(k, [])
        refined = [e for e in rs if e['set'] == 'refined']
        if not rs:
            nb = [e for e in ev if e['sym'].upper() == k[0] and near(e['entry'], k[1])]
            reason = 'no event on that date; same ticker within 5 days in new sets' if nb else 'no event for that ticker in the new base set'
        elif not refined:
            reason = 'in base set only (removed by D-064 routine exclusion)'
        else:
            e = max(refined, key=lambda x: x['status'] in FINE)
            if e['status'] not in FINE:
                reason = f'identity not fine ({e["status"]})'
            elif not e['liquid']:
                reason = 'fails new $3M floor (15 archive bars)'
            elif k not in primary_keys:
                reason = 'collapsed by option C (D-065); every primary pilot entry completed'
            else:
                reason = 'other'
        why[reason].append(k)
    print('\nWhy old-only trades are not in the new set:')
    for reason, ks in sorted(why.items(), key=lambda kv: -len(kv[1])):
        print(f'  {len(ks):>3}  {reason}: old mean excess {m([oldkey[k]["excess_atr"] for k in ks]):+.3f}; ' + ', '.join(f'{k[0]} {k[1]} {oldkey[k]["excess_atr"]:+.2f}' for k in ks))
    oldall = {(t['ticker'].upper(), t['entry']): t for t in old}
    wn = defaultdict(list)
    for k in only_new:
        wn['in old 137 but not liquid' if k in oldall else 'not in old 137 at all'].append(k)
    print('\nWhy new-only trades are not in the old liquid set:')
    for reason, ks in wn.items():
        print(f'  {len(ks):>3}  {reason}: new mean excess {m([newkey[k]["excess_atr"] for k in ks]):+.3f}; ' + ', '.join(f'{k[0]} {k[1]}' for k in ks[:6]))
    tot_old, tot_new = sum(oldkey[k]['excess_atr'] for k in oldkey), sum(newkey[k]['excess_atr'] for k in newkey)
    print(f'\nTotal excess ATR: old {tot_old:.2f} over {len(oldkey)}; new {tot_new:.2f} over {len(newkey)}')
    print('Old-only trades by excess (top 5): ' + '; '.join(f'{k[0]} {k[1]} {oldkey[k]["excess_atr"]:+.2f}' for k in sorted(only_old, key=lambda k: -oldkey[k]['excess_atr'])[:5]))


if __name__ == '__main__':
    main(*sys.argv[1:4])
