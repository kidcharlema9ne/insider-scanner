"""C41 (POST HOC, Michael 9 Nov 2026: "see what happens to the base case when we require different dates"): the four-buyer base case rebuilt with a
purchase-date condition, compared with the rule in force, development years only (entries <= 2020-12-31, D-068).

VARIANT is the DATE_RULE the NEW set was built with (refined_study.py, same routine exclusion, identity test, $3M floor, one event per issuer per hold,
same 21-session price-only hold and ATR/SPY conventions as the rule in force, no costs):
  m4 = the four buyers can each be given a DIFFERENT purchase date (Michael's wording, the primary variant)
  d3 = the counted purchases span at least 3 distinct dates      d2 = at least 2 distinct dates (drops only all-on-one-day clusters)
The entry is the next open after the filing that makes BOTH "four distinct buyers" and the date condition true, so a dropped cluster can come back later.

DECLARED BEFORE RUNNING (three variants m4, d3, d2, nothing else; m4 is the one asked for, d3 and d2 show how the result moves with the strictness):
  A. OLD (rule in force, Entry 28 set) and NEW: n, trades per month, stock / SPY / excess means, median, share beating SPY, week-block 95% range.
  B. NEW split: SAME = same issuer and entry date as an OLD trade; OTHER = anything else (later entry or a cluster OLD never saw); and OLD NOT in NEW (dropped).
  C. By entry year: n OLD | n NEW, NEW mean excess.   D. Without the three large episodes (2008Q4, 2011Q3, 2020Q1).
Caution written in advance: a variant chosen after the project's other results; a better number is a lead, not a rule. Dropped trades are the informative group:
if they are no worse than the kept ones, the rule only removes events and adds nothing.

Usage:  python distinct_dates_compare.py NEW_RETURNS_FOLDER OLD_RETURNS_FOLDER VARIANT   |   --selftest
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import EPISODES, quarter
from window_overlap import line, load, split


def report(new, old, variant):
    print(f'=== A. Development completed trades, 21-session hold, excess over same-window SPY (ATR); NEW = date rule {variant} ===')
    line('OLD: rule in force (15-session window, no date rule)', old)
    line(f'NEW: date rule {variant}', new)
    same, other, dropped = split(new, old)
    print(f'\n=== B. Split of the NEW set; and the OLD trades the date rule removed ===')
    line('SAME issuer and entry date as an OLD trade', same)
    line('OTHER (later entry for a cluster OLD also found, or a cluster OLD never saw)', other)
    line('OLD trades NOT in NEW (dropped by the date rule)', dropped)
    kept = [r for r in old if (r['cik'], r['entry']) in {(x['cik'], x['entry']) for x in new}]
    line('OLD trades that stay (same issuer and entry date in NEW)', kept)
    print('\n=== C. By entry year (OLD n | NEW n, NEW mean excess) ===')
    yo, yn = defaultdict(list), defaultdict(list)
    for r in old:
        yo[r['entry'][:4]].append(r)
    for r in new:
        yn[r['entry'][:4]].append(r)
    for y in sorted(set(yo) | set(yn)):
        m = statistics.fmean(r['excess_atr'] for r in yn[y]) if yn[y] else float('nan')
        print(f'  {y}: {len(yo[y])} | {len(yn[y])}, {m:+.3f}')
    print('\n=== D. Without the three large episodes ===')
    ne = lambda rs: [r for r in rs if quarter(r['entry']) not in EPISODES]
    line('OLD', ne(old))
    line(f'NEW {variant}', ne(new))
    line('OLD dropped', ne(dropped))


def selftest():
    mk = lambda cik, e, x: {'cik': cik, 'entry': e, 'excess_atr': x, 'stock_atr': x + 0.1, 'spy_atr': 0.1, 'status': 'complete'}
    old = [mk('1', '2010-01-04', 0.5), mk('2', '2010-02-01', -0.2), mk('3', '2010-03-01', 0.1)]
    new = [mk('1', '2010-01-04', 0.5), mk('3', '2010-03-08', 0.3)]
    same, other, dropped = split(new, old)
    assert [r['cik'] for r in same] == ['1'] and [r['cik'] for r in other] == ['3'] and sorted(r['cik'] for r in dropped) == ['2', '3']
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    else:
        new_f, old_f, var = sys.argv[1:4]
        report(load(new_f), load(old_f), var)
