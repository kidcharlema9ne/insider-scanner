"""Same-day-close entry test (Michael's request, 8 Nov 2026): if the filing that brings the count to four was ACCEPTED by the SEC before the
close, enter at that day's CLOSE instead of the next regular open. POST HOC / exploratory variant, NOT the D-051 rule (D-051 uses the filing DATE
only; this variant needs the acceptance TIME). New code: marked PROVISIONAL. The baseline arm is the committed Entry 28 code (`refined_baseline.trade_outcome`).

Declared before any number was computed
  Events      identical to the baseline primary set (Entry 25 / 28: D-064, D-065 option C, identity, $3M floor). Selection is still by filing DATE;
              only the entry price and time of events whose fourth buyer's filing was accepted before the cutoff change. Development entries
              (<= 2020-12-31) and the 2026 pilot only (D-068); no 2021-2025 entry is fetched or priced.
  Crossing    The filing that brings the distinct-buyer count to four, found by walking the trigger-date filings in ACCEPTANCE-TIME order on top of
              the buyers already public on earlier dates (same rows the selector kept, routine rows excluded as in D-064).
  Time        SGML header ACCEPTANCE-DATETIME of the original filing (Eastern local time, runbook). Filing date F = the database filing date of that filing.
  Rule A      (primary, Michael's rule) F is a regular session and accepted before 16:00:00 ET -> entry = close of F.  Otherwise (accepted 16:00 or
              later, filing date not a session, or time unavailable) -> baseline next open.
  Rule B      (sensitivity, declared now) cutoff 15:50:00 ET instead of 16:00 (a closing order has to be placed before the close).
  Exit        close of the session that is 21 sessions after the entry session for a close entry (= the baseline's exit session for the same event,
              because the baseline enters at the open of the next session and exits at the close of its 21st session). Price only, no costs.
  ATR         mean true range of the 14 sessions completed BEFORE the filing session (the filing session is not finished when the order is placed).
  SPY         same window (SPY close of F to SPY close of the exit session) in the stock's ATR units; excess = stock minus SPY (D-053).
  Report      status counts, the time-of-day split, baseline vs variant on the SAME events (changed subset, unchanged subset, whole set), the
              close-to-next-open gap, sample sizes (issuers, entry dates, entry weeks), week-block bootstrap, eras and the three episodes.
Cautions written in advance: a fill at the exact close is an assumption (a filing accepted at 15:58 cannot realistically be filled at the 16:00 print;
rule B partly covers that); no costs, no market impact; events keep the baseline's survivor bias; a choice of rule made after seeing a result is a lead.

Usage:  python same_day_close.py events --out FILE          (needs R2 secrets and SEC_USER_AGENT; fetches headers of trigger-date filings only)
        python same_day_close.py year YEAR --primary FILE --timed FILE --out FILE
        python same_day_close.py summary FOLDER
        python same_day_close.py --selftest
"""
import argparse, json, os, statistics, sys, tempfile, time, urllib.error, urllib.request, re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import (ATR_BARS, DEV_END, EPISODES, HOLD, PILOT_START, allowed, assert_allowed, independence, load_span, quarter,
                              stats, trade_outcome, true_range, week_bootstrap)

CUT_A = '16:00:00'
CUT_B = '15:50:00'
OPEN_T = '09:30:00'
ACC_RE = re.compile(rb'<ACCEPTANCE-DATETIME>\s*(\d{14})')


# ------------------------------------------------------------------ acceptance times
def parse_accept(raw):
    m = ACC_RE.search(raw)
    return datetime.strptime(m.group(1).decode(), '%Y%m%d%H%M%S').isoformat() if m else None


def fetch_accept(cik, accession, agent, tries=4):
    url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}.txt'
    req = urllib.request.Request(url, headers={'User-Agent': agent, 'Range': 'bytes=0-6143', 'Accept-Encoding': 'identity'})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return parse_accept(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise SystemExit(f'SEC refused ({e.code}) for {accession}; stopping, not retrying (runbook).')
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def crossing(prior_owners, day_rows, accepted):
    """day_rows: list of (acc, owner). accepted: {acc: ISO time or None}. Returns (crossing acc, index) walking in acceptance order,
    or (None, reason). Rows without a time sort last (so they cannot bring the count to four ahead of timed rows)."""
    order = sorted(day_rows, key=lambda r: (accepted.get(r[0]) is None, accepted.get(r[0]) or '', r[0]))
    owners = set(prior_owners)
    for acc, owner in order:
        owners.add(owner)
        if len(owners) >= 4:
            return acc, 'ok'
    return None, 'no_cross'


def events_job(out):
    from cluster_counts_by_year import fetch_db, load_rows, sessions
    from refined_study import find_events_refined, row_owner
    agent = os.environ['SEC_USER_AGENT'].strip()
    with tempfile.TemporaryDirectory() as tmp:
        rows = list(load_rows(fetch_db(tmp)))
    cal = sessions()
    events, _ = find_events_refined(rows, cal, True)
    events = [e for e in events if allowed(e['entry'])]
    rowmap = {}
    for r in rows:
        rowmap[(r['accession'], tuple(r['transaction_row_keys']))] = r
    plan = []
    need = {}
    for e in events:
        i = bisect_left(cal, e['entry'])
        day_start = cal[i - 1]
        prior, day = set(), []
        for x in e['rows']:
            r = rowmap[(x['acc'], tuple(x['keys']))]
            if r['filing_date'] >= day_start:
                day.append((r['accession'], row_owner(r), r['filing_date'], r['issuer_cik']))
            else:
                prior.add(row_owner(r))
        plan.append((e, prior, day))
        for acc, _, _, cik in day:
            need[acc] = cik
    print(f'events (allowed, refined): {len(events)}; trigger-date filings to read: {len(need)}', flush=True)
    accepted, t0 = {}, time.time()
    for n, (acc, cik) in enumerate(sorted(need.items()), 1):
        accepted[acc] = fetch_accept(cik, acc, agent)
        time.sleep(0.3)
        if n % 250 == 0:
            print(f'  {n}/{len(need)} read, {time.time() - t0:.0f}s, missing so far {sum(v is None for v in accepted.values())}', flush=True)
    res = []
    for e, prior, day in plan:
        acc, why = crossing(prior, [(a, o) for a, o, _, _ in day], accepted)
        fd = {a: f for a, _, f, _ in day}.get(acc)
        all_owners = prior | {o for _, o, _, _ in day}
        res.append({'issuer_cik': e['issuer_cik'], 'ticker': e['ticker'], 'entry': e['entry'], 'buyers': e['buyers'],
                    'consistent_buyers': len(all_owners) == e['buyers'], 'cross_acc': acc, 'why': why, 'filing_date': fd,
                    'accepted': accepted.get(acc) if acc else None, 'n_day_rows': len(day),
                    'day_accepted': sorted(accepted.get(a) or 'NA' for a, _, _, _ in day)})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res))
    print(f'timed events: {len(res)}; with an acceptance time {sum(r["accepted"] is not None for r in res)}; '
          f'count consistent with the selector {sum(r["consistent_buyers"] for r in res)}; no crossing found {sum(r["why"] != "ok" for r in res)}')


# ------------------------------------------------------------------ variant outcome
def bucket(filing_date, accepted, sessions_set):
    if not accepted:
        return 'no_time'
    if filing_date not in sessions_set:
        return 'non_session'
    t = accepted[11:19]
    if t < OPEN_T:
        return 'pre_open'
    return 'intraday' if t < CUT_A else 'after_close'


def close_entry_outcome(dates, stock, spy, f, hold_after=HOLD):
    """Enter at the close of session f, exit at the close of the session `hold_after` sessions later. ATR from the 14 sessions before f."""
    assert_allowed(f)
    j = bisect_left(dates, f)
    if j >= len(dates) or dates[j] != f:
        return {'status': 'entry_not_session'}
    if j < ATR_BARS + 1:
        return {'status': 'atr_missing'}
    window = dates[j - ATR_BARS - 1:j]
    if any(d not in stock for d in window):
        return {'status': 'atr_missing'}
    atr = sum(true_range(stock[window[k]], stock[window[k - 1]][3]) for k in range(1, len(window))) / ATR_BARS
    if atr <= 0 or f not in stock:
        return {'status': 'atr_missing'}
    px = stock[f][3]
    x = j + hold_after
    if x >= len(dates):
        return {'status': 'open', 'atr': atr, 'entry_px': px}
    if f not in spy or dates[x] not in spy:
        return {'status': 'spy_missing'}
    spy_pct = spy[dates[x]][3] / spy[f][3] - 1
    spy_atr = spy_pct * px / atr
    if dates[x] in stock:
        s = (stock[dates[x]][3] - px) / atr
        return {'status': 'complete', 'atr': atr, 'entry_px': px, 'exit': dates[x], 'stock_atr': s, 'spy_atr': spy_atr,
                'excess_atr': s - spy_atr, 'stock_pct': stock[dates[x]][3] / px - 1, 'spy_pct': spy_pct}
    held = [d for d in dates[j:x + 1] if d in stock]
    last = held[-1]
    s = (stock[last][3] - px) / atr
    return {'status': 'incomplete', 'atr': atr, 'entry_px': px, 'exit': last, 'stock_atr': s, 'spy_atr': spy_atr,
            'excess_atr': s - spy_atr, 'stock_pct': stock[last][3] / px - 1, 'spy_pct': spy_pct}


def year_job(year, primary_path, timed_path, out):
    from r2_storage import client
    from archive_coverage_audit import DELISTED
    s3 = client()
    timed = {(t['issuer_cik'], t['entry']): t for t in json.loads(Path(timed_path).read_text())}
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
    rows = []
    if entries:
        syms = {e['sym'] for e in entries}
        want = syms | {s + DELISTED for s in syms}
        stock_bars, dates = load_span(s3, 'stock', [year], want, 25, 30)
        spy_bars, _ = load_span(s3, 'etf', [year], {'SPY'}, 25, 30)
        spy = spy_bars.get('SPY', {})
        sess = set(dates)
        for e in entries:
            series = dict(stock_bars.get(e['sym'], {}))
            if e.get('via') == 'delisted' or not series:
                series = {**series, **stock_bars.get(e['sym'] + DELISTED, {})}
            t = timed.get((e['cik'], e['entry']))
            base = trade_outcome(dates, series, spy, e['entry'])
            row = {'entry': e['entry'], 'sym': e['sym'], 'cik': e['cik'], 'via': e.get('via'), 'matched': t is not None, 'base': base}
            if t is None:
                row.update(bucket='unmatched', filing_date=None, accepted=None)
            else:
                b = bucket(t['filing_date'], t['accepted'], sess)
                row.update(bucket=b, filing_date=t['filing_date'], accepted=t['accepted'])
                for name, cut in (('varA', CUT_A), ('varB', CUT_B)):
                    use = b in ('pre_open', 'intraday') and t['accepted'][11:19] < cut
                    row[name] = close_entry_outcome(dates, series, spy, t['filing_date']) if use else None
                if row['varA'] and row['varA'].get('status') == 'complete' and base.get('status') == 'complete' and t['filing_date'] in series and e['entry'] in series:
                    row['gap_pct'] = series[e['entry']][0] / series[t['filing_date']][3] - 1
            rows.append(row)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'rows': rows}))
    print(f'{year}: {len(rows)} entries; buckets {dict(Counter(r["bucket"] for r in rows))}; base {dict(Counter(r["base"]["status"] for r in rows))}')


# ------------------------------------------------------------------ summary
def combined(r, name):
    """Outcome under the rule: the variant where it applies and completed, else the baseline."""
    v = r.get(name)
    return v if v and v.get('status') == 'complete' else r['base']


def line(label, rs):
    return f'{label}: {stats(rs)}' if rs else f'{label}: n=0'


def summary(folder):
    rows = [r for p in sorted(Path(folder).glob('same_day_*.json')) for r in json.loads(p.read_text())['rows']]
    for r in rows:
        assert_allowed(r['entry'])
    print(f'=== A. Entries: {len(rows)} (development <= {DEV_END} plus 2026 pilot; D-068) ===')
    print('matched to an acceptance time:', Counter(r['matched'] for r in rows))
    print('time-of-day bucket of the crossing filing:', dict(Counter(r['bucket'] for r in rows)))
    ok = [r for r in rows if r['base'].get('status') == 'complete']
    print(f'baseline completed: {len(ok)} (Entry 28 reference: development 1,372 / pilot 80)')
    dev = lambda rs: [r for r in rs if r['entry'] <= DEV_END]
    for tag, sel in (('development 2006-2020', dev), ('2026 pilot (in-sample)', lambda rs: [r for r in rs if r['entry'] >= PILOT_START])):
        sub = sel(ok)
        print(f'\n=== B. {tag}: baseline (next open) vs Rule A (close of filing day if accepted before 16:00) on the same events ===')
        print(line('baseline, all events', [r['base'] | {'entry': r['entry']} for r in sub]))
        for nm, cutname in (('Rule A (16:00)', 'varA'), ('Rule B (15:50)', 'varB')):
            chg = [r for r in sub if r.get(cutname) and r[cutname].get('status') == 'complete']
            print(f'\n  {nm}: {len(chg)} of {len(sub)} events change entry (baseline and variant both completed)')
            print('  ' + line('baseline arm, changed events  ', [r['base'] | {'entry': r['entry']} for r in chg]))
            print('  ' + line('variant arm, changed events   ', [r[cutname] | {'entry': r['entry']} for r in chg]))
            same = [r for r in sub if r not in chg]
            print('  ' + line('unchanged events (baseline)  ', [r['base'] | {'entry': r['entry']} for r in same]))
            allv = [combined(r, cutname) | {'entry': r['entry']} for r in sub]
            print('  ' + line('whole set under this rule    ', allv))
            if len(chg) > 1:
                diff = [{'entry': r['entry'], 'excess_atr': r[cutname]['excess_atr'] - r['base']['excess_atr']} for r in chg]
                lo, hi, p = week_bootstrap(diff)
                print(f'  paired difference (variant minus baseline), changed events: mean {statistics.fmean(d["excess_atr"] for d in diff):+.3f} ATR, '
                      f'week-block 95% range {lo:+.3f} to {hi:+.3f}, share of draws <= 0 {p:.1%}')
                pc = [r[cutname]['stock_pct'] - r['base']['stock_pct'] for r in chg]
                print(f'  paired difference in stock return: mean {statistics.fmean(pc):+.2%}, median {statistics.median(pc):+.2%}')
                gaps = [r['gap_pct'] for r in chg if 'gap_pct' in r]
                if gaps:
                    print(f'  close of filing day to next open (the gap the baseline pays or earns): mean {statistics.fmean(gaps):+.2%}, median {statistics.median(gaps):+.2%}, n={len(gaps)}')
                    print(f'  independence of changed events: {independence([{"entry": r["entry"], "cik": r["cik"]} for r in chg])}')
        print(f'\n  by time-of-day bucket (Rule A, changed events), baseline arm vs variant arm:')
        for b in ('pre_open', 'intraday'):
            c = [r for r in sub if r['bucket'] == b and r.get('varA') and r['varA'].get('status') == 'complete']
            print(f'   {b}: {len(c)} events')
            if c:
                print('     ' + line('baseline', [r['base'] | {'entry': r['entry']} for r in c]))
                print('     ' + line('variant ', [r['varA'] | {'entry': r['entry']} for r in c]))
    d = dev(ok)
    print('\n=== C. Eras and episodes, development, Rule A: whole set under the rule vs baseline ===')
    for label, sel in (('2006-2010', lambda r: r['entry'] <= '2010-12-31'), ('2011-2020', lambda r: r['entry'] > '2010-12-31'),
                       ('without 2008Q4/2011Q3/2020Q1', lambda r: quarter(r['entry']) not in EPISODES)):
        sub = [r for r in d if sel(r)]
        print(line(f'{label} baseline', [r['base'] | {'entry': r['entry']} for r in sub]))
        print(line(f'{label} Rule A  ', [combined(r, 'varA') | {'entry': r['entry']} for r in sub]))
    print('\n=== D. Costs: none included. A close entry means paying the closing-auction price; Rule B (15:50) is the realistic cutoff. ===')


# ------------------------------------------------------------------ self-test
def selftest():
    # acceptance parsing
    assert parse_accept(b'xx<ACCEPTANCE-DATETIME>20161115204558\n') == '2016-11-15T20:45:58'
    assert parse_accept(b'nothing') is None
    # crossing walks in acceptance order on top of the prior buyers
    acc = {'a': '2020-03-02T10:00:00', 'b': '2020-03-02T15:30:00', 'c': '2020-03-02T16:30:00', 'd': None}
    day = [('c', 'o3'), ('a', 'o1'), ('b', 'o2'), ('d', 'o9')]
    assert crossing({'p1', 'p2'}, day, acc) == ('b', 'ok')                      # p1 p2 + o1 (3) + o2 (4) -> b, accepted 15:30
    assert crossing({'p1'}, day, acc) == ('c', 'ok')                            # needs o1, o2, o3 -> c (after the close)
    assert crossing({'p1'}, [('a', 'o1')], acc) == (None, 'no_cross')
    assert crossing({'p1', 'p2', 'p3'}, [('d', 'o9')], acc) == ('d', 'ok')       # untimed row can still be the only one
    # time buckets
    sess = {'2020-03-02'}
    assert bucket('2020-03-02', '2020-03-02T08:00:00', sess) == 'pre_open'
    assert bucket('2020-03-02', '2020-03-02T09:30:00', sess) == 'intraday'
    assert bucket('2020-03-02', '2020-03-02T15:59:59', sess) == 'intraday'
    assert bucket('2020-03-02', '2020-03-02T16:00:00', sess) == 'after_close'
    assert bucket('2020-03-01', '2020-03-01T10:00:00', sess) == 'non_session'
    assert bucket('2020-03-02', None, sess) == 'no_time'
    # close entry arithmetic
    dates = [f'2020-02-{d:02d}' for d in range(1, 29)] + [f'2020-03-{d:02d}' for d in range(1, 32)]
    flat = {d: (100.0, 102.0, 98.0, 100.0) for d in dates}
    spy = {d: (400.0, 401.0, 399.0, 400.0) for d in dates}
    f = dates[20]
    flat[dates[20 + HOLD]] = (100.0, 110.0, 98.0, 108.0)
    spy[dates[20 + HOLD]] = (400.0, 405.0, 399.0, 404.0)
    r = close_entry_outcome(dates, flat, spy, f)
    assert r['status'] == 'complete' and r['exit'] == dates[20 + HOLD] and abs(r['atr'] - 4.0) < 1e-9, r
    assert abs(r['stock_atr'] - 2.0) < 1e-9 and abs(r['spy_atr'] - 0.25) < 1e-9 and abs(r['excess_atr'] - 1.75) < 1e-9, r
    # same exit session as the baseline that enters at the next open
    b = trade_outcome(dates, flat, spy, dates[21])
    assert b['status'] == 'complete' and b['exit'] == r['exit'], (b, r)
    assert close_entry_outcome(dates, flat, spy, '2020-04-15')['status'] == 'entry_not_session'
    assert close_entry_outcome(dates, flat, spy, dates[3])['status'] == 'atr_missing'
    assert close_entry_outcome(dates, flat, spy, dates[-3])['status'] == 'open'
    for bad in ('2021-01-04', '2023-06-01'):
        try:
            close_entry_outcome(dates, flat, spy, bad)
        except RuntimeError:
            continue
        raise AssertionError('D-068 guard let ' + bad + ' through')
    short = {d: x for d, x in flat.items() if d < dates[20 + HOLD - 2]}
    assert close_entry_outcome(dates, short, spy, f)['status'] == 'incomplete'
    row = {'base': {'status': 'complete', 'excess_atr': 1.0}, 'varA': {'status': 'complete', 'excess_atr': 2.0}, 'varB': None}
    assert combined(row, 'varA')['excess_atr'] == 2.0 and combined(row, 'varB')['excess_atr'] == 1.0
    print('same_day_close self-test passed')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['events', 'year', 'summary'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--timed')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'events':
        events_job(a.out)
    elif a.cmd == 'year':
        year_job(int(a.arg), a.primary, a.timed, a.out)
    elif a.cmd == 'summary':
        summary(a.arg)
    else:
        ap.error('give a subcommand or --selftest')
