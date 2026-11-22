"""C38 (POST HOC, Michael 9 Nov 2026: "open that up to a month ... what happens?"): compare the four-buyer signals built with a longer buying window
(21 sessions, about a month) against the rule in force (15 sessions, D-057), on development years only (entries <= 2020-12-31, D-068).

Inputs are two folders of returns_YYYY.json files made by refined_baseline.py year (same code, same 21-session price-only hold, same ATR and SPY
conventions): NEW (window variant, built by cluster-window-variant.yml with CLUSTER_WINDOW set) and OLD (the 15-session set, Entry 28 run 42490748366).
No sealed return is read. Excess = stock minus same-window SPY over 21 sessions in the stock's ATR units, stock and SPY legs shown (D-053). No costs.

DECLARED BEFORE RUNNING (one variant, window 21; no other window is run in this entry):
  A. Both sets: completed development trades, trades per month (n / 180), stock / SPY / excess means, median, share beating SPY, week-block 95% range.
  B. Split of the NEW set: SAME = same issuer and same entry date as an OLD trade; OTHER = everything else (earlier entry for a cluster the 15-session
     rule also found later, or a cluster the 15-session rule never saw). Same stats for each part, plus OLD trades that are not in NEW.
  C. By entry year: n for OLD and NEW and the NEW mean excess.
  D. Without the three large episodes (2008Q4, 2011Q3, 2020Q1).
Caution written in advance: one variant chosen after the project's other results, so a better or worse number is a lead, not a rule; the new set is
rebuilt end to end (routine exclusion, identity test, $3M floor, one event per issuer per hold) with only the window changed.

Usage:  python window_overlap.py NEW_RETURNS_FOLDER OLD_RETURNS_FOLDER   |   --selftest
"""
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, quarter, stats, week_bootstrap

MONTHS = 180
WIN = os.environ.get('CLUSTER_WINDOW', '21')   # label only; the data come from the folders


def load(folder):
    rows = [r for p in sorted(Path(folder).glob('returns_*.json')) for r in json.loads(p.read_text())['rows']]
    return [r for r in rows if r['status'] == 'complete' and r['entry'] <= DEV_END]


def line(label, rs):
    if not rs:
        print(f'  {label}: n=0')
        return
    rg = ''
    if len(rs) > 1:
        lo, hi, _ = week_bootstrap(rs, 2000)
        rg = f' | 95% range {lo:+.3f} to {hi:+.3f}'
    print(f'  {label}: {stats(rs)} | {len(rs) / MONTHS:.2f} a month{rg}')


def split(new, old):
    old_keys = {(r['cik'], r['entry']) for r in old}
    new_keys = {(r['cik'], r['entry']) for r in new}
    same = [r for r in new if (r['cik'], r['entry']) in old_keys]
    other = [r for r in new if (r['cik'], r['entry']) not in old_keys]
    dropped = [r for r in old if (r['cik'], r['entry']) not in new_keys]
    return same, other, dropped


def report(new, old):
    print('=== A. Development completed trades, 21-session hold, excess over same-window SPY (ATR) ===')
    line('15-session window (rule in force)', old)
    line(f'{WIN}-session window', new)
    same, other, dropped = split(new, old)
    print('\n=== B. Split of the 21-session set ===')
    line('SAME issuer and entry date as a 15-session trade', same)
    line('OTHER (earlier entry or a cluster the 15-session rule never saw)', other)
    line(f'15-session trades NOT in the {WIN}-session set', dropped)
    print('\n=== C. By entry year (15-session n | new-window n, mean excess) ===')
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
    line('15-session', ne(old))
    line(f'{WIN}-session', ne(new))
    line(f'{WIN}-session OTHER', ne(other))


def selftest():
    mk = lambda cik, entry, ex: dict(cik=cik, entry=entry, status='complete', excess_atr=ex, stock_atr=ex, spy_atr=0.0)
    old = [mk('a', '2010-01-04', 1.0), mk('b', '2010-02-01', -1.0)]
    new = [mk('a', '2010-01-04', 1.0), mk('c', '2010-03-01', 3.0), mk('b', '2010-01-20', -1.0)]
    same, other, dropped = split(new, old)
    assert len(same) == 1 and len(other) == 2 and len(dropped) == 1 and dropped[0]['cik'] == 'b'
    print('window_overlap self-test passed')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    else:
        report(load(sys.argv[1]), load(sys.argv[2]))
