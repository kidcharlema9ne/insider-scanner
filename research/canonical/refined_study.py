"""Refined event study set-up: split-grid identity test, routine-purchase exclusion, repeat-event collapse, sealed-share cut.

Implements Michael's decisions of 8 Nov 2026 (research_docs/DECISION_LOG.md D-064, D-065, D-066). COUNTS ONLY: this module
never computes a return. Terminal-price information is not produced at all.

  D-064  Routine (plan-like) purchases are excluded, using only filings public at the time:
         (a) a filing is routine if three or more distinct owners bought on the same transaction date at weighted
             prices within one cent of each other (judged on the filings public on the entry-filing day);
         (b) an event is dropped if, on its filing day, the issuer already showed signature (a) in at least two of
             the three complete calendar months before the filing month.
         Routine filings do not count toward the four distinct buyers. Look-back only: a filing that arrives after
         the entry filing can never change that event.
  D-065  Option C: after D-064, keep the first event per issuer; ignore that issuer until its 21-session hold ended
         (a new event may enter on session index >= first entry index + 21; entry session is day one).
  D-066  Sealed share target about 25%: choose the quarter boundary whose sealed share (entries from that quarter
         through 2025-12-31, as a share of ALL 2006-2025 entries) is nearest 25%. Counts only.
  Identity (Entry 23 follow-up): the archive closes are split-adjusted, so the median purchase-price / archive-close
         ratio is also accepted when it sits on a split factor (1.5, 2, 3 ... and inverses) AND is stable across at
         least two independent purchase prices. Everything else off 1.0 is 'mismatch' (a possible wrong company).

Subcommands
  events   build base and refined event sets (SEC step, 10-45 min) -> events JSON
  year     match one entry year against the price archive -> year_YYYY.json
  summary  merge, collapse, print tables and the quarter-cut table
  --selftest
"""
import argparse, json, os, statistics, sys, tempfile
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from archive_coverage_audit import DELISTED, FLOOR, WINDOW as LIQ_WINDOW, key_date, list_dates, normalize_ticker, read_file
from identity_check import OK_HI, OK_LO, load_year, ratios_for, window_stats

CLUSTER_WINDOW = int(os.environ.get('CLUSTER_WINDOW', '15'))   # sessions of purchase dates before entry (D-057: 15 is the rule in force; other values are exploratory variants, C38)
SAME_PRICE_TOL = 0.01          # D-064 (a): weighted prices within one cent
SAME_DAY_BUYERS = 3            # D-064 (a): three or more distinct owners
MODE_MONTHS, MODE_NEED = 3, 2  # D-064 (b): two of the three complete months before the filing month
HOLD_SESSIONS = 21             # D-065
DATE_RULE = os.environ.get('DATE_RULE', '')   # C41 (POST HOC variant, Michael 9 Nov 2026): '' = rule in force; 'd2'/'d3' = counted purchases span >= 2/3 distinct dates; 'm4' = four buyers can be given four different dates

SPLIT_FACTORS = [1.5, 2, 2.25, 2.5, 3, 4, 5, 6, 8, 9, 10, 12, 15, 16, 20, 24, 25, 30, 40, 50, 100, 200, 250, 500, 1000]
GRID = sorted(set(SPLIT_FACTORS) | {1 / f for f in SPLIT_FACTORS})
GRID_TOL = 0.07                # relative distance of the median ratio from a grid factor
STABLE_BAND, STABLE_SHARE, MIN_POINTS = 0.20, 0.75, 2
RANK = {'ok': 4, 'split_ok': 3, 'split_unverified': 2, 'unverifiable': 1, 'mismatch': 0}
FINE = {'ok', 'split_ok'}
LOOSE = FINE | {'split_unverified', 'unverifiable'}


# ------------------------------------------------------------------ identity with split grid
def grid_factor(med):
    best = min(GRID, key=lambda g: abs(med / g - 1))
    return best if abs(med / best - 1) <= GRID_TOL else None


def identity_v2(ratios):
    """-> (status, median ratio, split factor or None)."""
    if not ratios:
        return 'unverifiable', None, None
    med = statistics.median(ratios)
    if OK_LO <= med <= OK_HI:
        return 'ok', med, None
    g = grid_factor(med)
    if g is None:
        return 'mismatch', med, None
    stable = sum(1 for r in ratios if abs(r / med - 1) <= STABLE_BAND) / len(ratios) >= STABLE_SHARE
    if not stable:
        return 'mismatch', med, None
    return ('split_ok' if len(ratios) >= MIN_POINTS else 'split_unverified'), med, g


def evaluate_event_v2(e, all_dates, series):
    best = None
    for via, (closes, dvol) in series.items():
        bars, nwin, mean = window_stats(all_dates, e['entry'], closes, dvol)
        if bars == 0:
            continue
        ratios = ratios_for([tuple(p) for p in e['purchases']], closes)
        status, med, g = identity_v2(ratios)
        cand = {'via': via, 'status': status, 'ratio': med, 'factor': g, 'n_cmp': len(ratios), 'bars': bars,
                'liquid': bars == LIQ_WINDOW and nwin == LIQ_WINDOW and mean is not None and mean >= FLOOR}
        if best is None or (RANK[status], bars) > (RANK[best['status']], best['bars']):
            best = cand
    return best or {'status': 'no_price', 'via': None, 'ratio': None, 'factor': None, 'n_cmp': 0, 'bars': 0, 'liquid': False}


# ------------------------------------------------------------------ routine purchases (D-064)
def row_owner(r):
    return r['owners'][0]['cik']


def row_price(r):
    try:
        p = float(r.get('insider_weighted_price')) if r.get('insider_weighted_price') not in (None, '') else None
    except (TypeError, ValueError):
        return None
    return p if p and p > 0 else None


def same_day_same_price(rows, min_date=None, max_date=None, tol=SAME_PRICE_TOL, min_buyers=SAME_DAY_BUYERS):
    """Signature (a). Returns (indexes of flagged rows, flagged transaction dates). Uses only the rows given."""
    by_date = defaultdict(list)
    for k, r in enumerate(rows):
        p = row_price(r)
        if p is None:
            continue
        for d in r['transaction_dates']:
            if (min_date and d < min_date) or (max_date and d > max_date):
                continue
            by_date[d].append((p, row_owner(r), k))
    flagged_rows, flagged_dates = set(), set()
    for d, items in by_date.items():
        for p0, _, _ in items:
            grp = [x for x in items if p0 - 1e-9 <= x[0] <= p0 + tol + 1e-9]
            if len({o for _, o, _ in grp}) >= min_buyers:
                flagged_dates.add(d)
                flagged_rows.update(k for _, _, k in grp)
    return flagged_rows, flagged_dates


def prior_months(filing_date, n=MODE_MONTHS):
    y, m = int(filing_date[:4]), int(filing_date[5:7])
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f'{y:04d}-{m:02d}')
    return out


def issuer_routine_mode(issuer_rows, i, filing_date, tol=SAME_PRICE_TOL, min_buyers=SAME_DAY_BUYERS):
    """Signature (b), look-back only: rows filed up to session index i; months strictly before the filing month."""
    months = prior_months(filing_date)
    pub = [r for j, r in issuer_rows if j <= i]
    _, fdates = same_day_same_price(pub, min_date=months[-1] + '-01', max_date=filing_date, tol=tol, min_buyers=min_buyers)
    return len({d[:7] for d in fdates} & set(months)) >= MODE_NEED


# ------------------------------------------------------------------ distinct purchase dates (C41, exploratory)
def owner_dates(rows, start, entry):
    od = defaultdict(set)
    for r in rows:
        for d in r['transaction_dates']:
            if start <= d < entry:
                od[row_owner(r)].add(d)
    return od


def max_matching(od):
    """Largest set of owners that can each be given a different purchase date (Kuhn's augmenting paths)."""
    match = {}
    def try_owner(o, seen):
        for d in od[o]:
            if d in seen:
                continue
            seen.add(d)
            if d not in match or try_owner(match[d], seen):
                match[d] = o
                return True
        return False
    return sum(try_owner(o, set()) for o in od)


def date_rule_ok(rows, start, entry, rule):
    if not rule:
        return True
    od = owner_dates(rows, start, entry)
    if rule in ('d2', 'd3'):
        return len(set().union(*od.values())) >= int(rule[1]) if od else False
    if rule == 'm4':
        return max_matching(od) >= 4
    raise ValueError(rule)


def find_events_refined(rows, cal, exclude_routine, tol=SAME_PRICE_TOL, min_buyers=SAME_DAY_BUYERS, date_rule=None):
    """Same crossing logic as cluster_counts_by_year.find_events. With exclude_routine=False the result is identical to it.
    date_rule (default: DATE_RULE from the environment, applied only when exclude_routine is True): an event needs four distinct buyers AND
    the date condition at the same time; the entry is the filing that makes both true. With no date rule the result is unchanged."""
    rule = (DATE_RULE if date_rule is None else date_rule) if exclude_routine else ''
    from cluster_counts_by_year import usable
    by_security, by_issuer = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for row in rows:
        if not usable(row):
            continue
        i = bisect_right(cal, row['filing_date'])
        if i >= len(cal):
            continue
        by_security[(row['issuer_cik'], row['ticker_at_filing'], row['security_title'].upper())][i].append(row)
        by_issuer[row['issuer_cik']].append((i, row))
    events, stats = [], Counter()
    for key, by_idx in by_security.items():
        if len({row_owner(r) for rs in by_idx.values() for r in rs}) < 4:
            continue
        seen = []
        for i in sorted(by_idx):
            entry, start = cal[i], cal[max(0, i - CLUSTER_WINDOW)]
            ok = lambda r: any(start <= d < entry for d in r['transaction_dates'])
            seen = [r for r in seen if ok(r)]
            new = [r for r in by_idx[i] if ok(r)]
            allrows = seen + new
            bad = set()
            if exclude_routine and allrows:
                bad = {id(allrows[k]) for k in same_day_same_price(allrows, tol=tol, min_buyers=min_buyers)[0]}
            before_rows = [r for r in seen if id(r) not in bad]
            before = {row_owner(r) for r in before_rows}
            seen = allrows
            after_rows = [r for r in seen if id(r) not in bad]
            after = {row_owner(r) for r in after_rows}
            qual_before = len(before) >= 4 and date_rule_ok(before_rows, start, entry, rule)
            qual_after = len(after) >= 4 and date_rule_ok(after_rows, start, entry, rule)
            if not qual_before and qual_after:
                if bad:
                    stats['crossings_with_routine_rows_excluded'] += 1
                if exclude_routine and issuer_routine_mode(by_issuer[key[0]], i, max(r['filing_date'] for r in new), tol, min_buyers):
                    stats['dropped_issuer_routine_mode'] += 1
                    continue
                purchases = []
                for r in seen:
                    if id(r) in bad:
                        continue
                    p = row_price(r)
                    purchases += [(d, p) for d in r['transaction_dates'] if start <= d < entry]
                owners = sorted({(row_owner(r), r['owners'][0]['relationship'], r['owners'][0].get('title') or '')
                                 for r in seen if id(r) not in bad})
                events.append({'issuer_cik': key[0], 'ticker': key[1], 'entry': entry, 'buyers': len(after),
                               'purchases': purchases, 'n_routine_rows': len(bad), 'owners': [list(o) for o in owners],
                               'distinct_dates': len({d for d, _ in purchases}), 'match4': max_matching(owner_dates(after_rows, start, entry)) >= 4,
                               'window_start': start,
                               'rows': [{'acc': r['accession'], 'keys': r['transaction_row_keys']} for r in seen if id(r) not in bad]})
    return events, stats


def enrich(events, db):
    """Attach to each event the individual purchase lines (owner, date, shares, price, shares owned after, direct/indirect)
    that were counted, read from the SEC database. Selection is untouched. Removes the temporary 'rows' and 'window_start'."""
    cache = {}
    for e in events:
        lines = []
        for r in e.pop('rows'):
            for k in r['keys']:
                if (r['acc'], k) not in cache:
                    got = db.execute('SELECT payload FROM purchase_candidates WHERE accession=? AND transaction_row_key=?', (r['acc'], k)).fetchone()
                    cache[(r['acc'], k)] = json.loads(got[0]) if got else None
                p = cache[(r['acc'], k)]
                if p is not None and p.get('transaction_date') and e['window_start'] <= p['transaction_date'] < e['entry']:
                    lines.append({'owner': p['owners'][0]['cik'], 'date': p['transaction_date'], 'shares': p.get('shares'),
                                  'price': p.get('price_per_share'), 'after': p.get('shares_after'), 'di': p.get('direct_indirect'), 'acc': r['acc']})
        e['lines'] = lines
        e.pop('window_start')


def build_events(out):
    from cluster_counts_by_year import fetch_db, find_events, load_rows, sessions
    with tempfile.TemporaryDirectory() as tmp:
        rows = list(load_rows(fetch_db(tmp)))
        cal = sessions()
        original = find_events(rows, cal)
        base, _ = find_events_refined(rows, cal, False)
        refined, stats = find_events_refined(rows, cal, True)
        import sqlite3
        db = sqlite3.connect(str(next(Path(tmp).glob('*.sqlite3'))))
        enrich(refined, db)
        for e in base:
            e.pop('rows', None)
            e.pop('window_start', None)
        sens_rows, sens_cal = rows, cal
    k = lambda ev: sorted((e['issuer_cik'], e['ticker'], e['entry'], e['buyers']) for e in ev)
    assert k(base) == k(original), 'base set differs from cluster_counts_by_year.find_events'
    both = {(e['issuer_cik'], e['ticker'], e['entry']) for e in base} & {(e['issuer_cik'], e['ticker'], e['entry']) for e in refined}
    for e in base:
        e['set'] = 'base'
    for e in refined:
        e['set'] = 'refined'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(base + refined))
    print(f'base events: {len(base)} (identical to cluster_counts_by_year.find_events)')
    print(f'refined events (D-064 applied): {len(refined)}; same issuer/ticker/entry in both: {len(both)}; '
          f'base only: {len(base) - len(both)}; refined only: {len(refined) - len(both)}')
    print(f'refined run stats: {dict(stats)}  (DATE_RULE={DATE_RULE or "off"})')
    dd = Counter(min(e['distinct_dates'], 5) for e in refined)
    print('Distinct purchase dates among the counted purchases, refined events (5 = five or more): ' + ', '.join(f'{k}: {dd[k]}' for k in sorted(dd)))
    print(f'Refined events where four buyers can each be given a different date: {sum(e["match4"] for e in refined)} of {len(refined)}')
    print('Sensitivity of the refined event count to the D-064 thresholds (counts only; base = %d):' % len(base))
    for tol, mb in ((0.0, 3), (0.005, 3), (0.01, 3), (0.02, 3), (0.01, 4), (0.0, 4)):
        n = len(refined) if (tol, mb) == (SAME_PRICE_TOL, SAME_DAY_BUYERS) else len(find_events_refined(rows, cal, True, tol, mb, date_rule='')[0])
        print(f'  price tolerance ${tol:.3f}, min distinct same-day buyers {mb}: refined events {n}')


# ------------------------------------------------------------------ year job (identity v2 + $3M floor; no returns)
def year_job(year, events_path, out):
    from r2_storage import client
    s3 = client()
    allev = json.loads(Path(events_path).read_text())
    for e in allev:
        e['sym'], e['tcat'] = normalize_ticker(e['ticker'])
    events = [e for e in allev if e['entry'].startswith(str(year)) and e['tcat'] == 'ok']
    need = {x for e in events for x in (e['sym'], e['sym'] + DELISTED)}
    closes, dvol, _, dates = load_year(s3, year, need, set())
    tail = list_dates(s3, 'stock', year - 1)[-LIQ_WINDOW - 10:]
    tail_dates = []
    with ThreadPoolExecutor(8) as pool:
        for key, _, t in pool.map(lambda k: read_file(s3, k), tail):
            day = key_date(key)
            tail_dates.append(day)
            for s, c, v in zip(t['symbol'], t['close'], t['volume']):
                if s in need and c and c > 0:
                    closes[s][day] = c
                    if v is not None and v >= 0:
                        dvol[s][day] = c * v
    all_dates = sorted(set(tail_dates) | set(dates))
    results = []
    for e in events:
        series = {'plain': (closes.get(e['sym'], {}), dvol.get(e['sym'], {})),
                  'delisted': (closes.get(e['sym'] + DELISTED, {}), dvol.get(e['sym'] + DELISTED, {}))}
        r = evaluate_event_v2(e, all_dates, series)
        r.update({'set': e['set'], 'entry': e['entry'], 'sym': e['sym'], 'cik': e['issuer_cik']})
        results.append(r)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'results': results}))
    print(f"{year}: events {len(events)} " + str({s: dict(Counter(r['status'] for r in results if r['set'] == s)) for s in ('base', 'refined')}))


# ------------------------------------------------------------------ summary
def quarter(iso):
    return f'{iso[:4]}Q{(int(iso[5:7]) - 1) // 3 + 1}'


def collapse(items, idx_of):
    """D-065 option C. items: dicts with 'cik' and 'entry'."""
    kept, last = [], {}
    for e in sorted(items, key=lambda e: (e['cik'], e['entry'])):
        j = idx_of(e['entry'])
        if e['cik'] in last and j < last[e['cik']] + HOLD_SESSIONS:
            continue
        last[e['cik']] = j
        kept.append(e)
    return kept


def issuer_year_stats(items):
    per = Counter((e['cik'], e['entry'][:4]) for e in items)
    n = len(items)
    over3 = sum(v for v in per.values() if v > 3)
    multi = sum(v for v in per.values() if v >= 2)
    return {'events': n, 'issuers': len({e['cik'] for e in items}), 'issuer_years': len(per),
            'max_in_one_issuer_year': max(per.values()) if per else 0,
            'share_in_issuer_years_over_3': round(over3 / n, 3) if n else 0,
            'share_in_issuer_years_2plus': round(multi / n, 3) if n else 0}


def cut_table(items):
    q = Counter(quarter(e['entry']) for e in items if '2006' <= e['entry'][:4] <= '2025')
    total = sum(q.values())
    rows = []
    for y in range(2018, 2023):
        for n in (1, 2, 3, 4):
            b = f'{y}Q{n}'
            sealed = sum(v for k, v in q.items() if k >= b and k[:4] <= '2025')
            rows.append((b, sealed, sealed / total if total else 0.0))
    return total, rows, min(rows, key=lambda r: abs(r[2] - 0.25))


def quarter_start(b):
    return f'{b[:4]}-{(int(b[5]) - 1) * 3 + 1:02d}-01'


def summary(folder, events_path):
    from cluster_counts_by_year import sessions
    cal = sessions()
    idx_of = lambda d: bisect_left(cal, d)
    allev = json.loads(Path(events_path).read_text())
    ev = {s: [{'cik': e['issuer_cik'], 'entry': e['entry'], 'ticker': e['ticker']} for e in allev if e['set'] == s] for s in ('base', 'refined')}
    years = sorted((json.loads(p.read_text()) for p in Path(folder).glob('year_*.json')), key=lambda r: r['year'])
    res = {s: [r for y in years for r in y['results'] if r['set'] == s] for s in ('base', 'refined')}

    print('=== A. Events per issuer-year (filings only; entry year 2006-2026) ===')
    for label, items in (('base (no D-064/D-065)', ev['base']), ('base + option C', collapse(ev['base'], idx_of)),
                         ('refined (D-064)', ev['refined']), ('refined + option C (D-064 + D-065)', collapse(ev['refined'], idx_of))):
        print(f'{label}: {issuer_year_stats(items)}')

    print('\n=== B. Identity v2 (purchase price vs archive close, split grid); events with a usable ticker ===')
    for s in ('base', 'refined'):
        c = Counter(r['status'] for r in res[s])
        matched = [r for r in res[s] if r['status'] != 'no_price']
        mism = Counter((r['sym'], r['via']) for r in res[s] if r['status'] == 'mismatch')
        print(f'{s}: {dict(c)}; mismatch share of price-matched = {c["mismatch"]}/{len(matched)} = {c["mismatch"] / max(1, len(matched)):.1%}')
        print(f'  split factors seen (split_ok): {dict(Counter(round(r["factor"], 3) for r in res[s] if r["status"] == "split_ok").most_common(12))}')
        print(f'  most frequent mismatch symbols: {mism.most_common(15)}')

    print('\n=== C. Tradable events = identity fine (ok or split_ok) AND $3M floor (15 prior bars); counts only ===')
    variants = {}
    for s in ('base', 'refined'):
        for strict, names in (('fine', FINE), ('loose', LOOSE)):
            tr = [r for r in res[s] if r['status'] in names and r['liquid']]
            variants[(s, strict, 'noC')] = tr
            variants[(s, strict, 'C')] = collapse(tr, idx_of)
    for k, items in variants.items():
        tot, _, best = cut_table(items)
        print(f'{k}: tradable {len(items)} (2006-2025: {tot}); 2026 pilot {sum(e["entry"][:4] == "2026" for e in items)}; '
              f'nearest-25% boundary {best[0]} -> sealed {best[1]} = {best[2]:.1%}')

    primary = variants[('refined', 'fine', 'C')]
    tot, rows, best = cut_table(primary)
    print('\n=== D. D-066 sealed-share table, PRIMARY = refined + option C + identity fine + $3M floor (counts only) ===')
    print('boundary | sealed entries (boundary..2025-12-31) | share of all 2006-2025 tradable entries')
    for b, sealed, share in rows:
        print(f'{b} | {sealed} | {share:.1%}' + ('   <-- nearest 25%' if b == best[0] else ''))
    gap_q = f'{int(best[0][:4]) - (1 if best[0][5] == "1" else 0)}Q{4 if best[0][5] == "1" else int(best[0][5]) - 1}'
    print(f'Chosen under D-066: sealed from {quarter_start(best[0])} through 2025-12-31 = {best[1]} of {tot} = {best[2]:.1%}; '
          f'gap quarter {gap_q} dropped from both sides; development = entries before the gap quarter. '
          f'(D-063 cut was 2020-04-01.)')
    inrange = [e for e in primary if '2006' <= e['entry'][:4] <= '2025']
    dev = [e for e in inrange if quarter(e['entry']) < gap_q]
    sealed = [e for e in inrange if quarter(e['entry']) >= best[0]]
    week = lambda e: __import__('datetime').date.fromisoformat(e['entry']).isocalendar()[:2]
    for label, items in (('development', dev), ('sealed', sealed), ('all 2006-2025', inrange)):
        print(f'independence, {label}: {len(items)} entries, {len({e["cik"] for e in items})} issuers, '
              f'{len({e["entry"] for e in items})} distinct entry dates, {len({week(e) for e in items})} distinct entry weeks')
    print('Entries by quarter (primary, 2006-2025):', dict(sorted(Counter(quarter(e['entry']) for e in inrange).items())))
    print('\n=== E. What D-064 removed: base events with no refined counterpart (same issuer, ticker, entry) ===')
    keep = {(e['issuer_cik'], e['ticker'], e['entry']) for e in allev if e['set'] == 'refined'}
    gone = [e for e in allev if e['set'] == 'base' and (e['issuer_cik'], e['ticker'], e['entry']) not in keep]
    stay = [e for e in allev if e['set'] == 'base' and (e['issuer_cik'], e['ticker'], e['entry']) in keep]
    def level(e):
        ps = sorted(p for _, p in e['purchases'] if p)
        return ps[len(ps) // 2] if ps else None
    def bucket(x):
        return 'no price' if x is None else '<$2' if x < 2 else '$2-5' if x < 5 else '$5-20' if x < 20 else '$20+'
    for label, items in (('removed', gone), ('kept', stay)):
        c = Counter(bucket(level(e)) for e in items)
        print(f'{label}: {len(items)} events; insider purchase price level (as traded): ' + ', '.join(f'{k} {c[k]} ({c[k] / max(1, len(items)):.0%})' for k in ('<$2', '$2-5', '$5-20', '$20+', 'no price')))
    py = Counter((e['issuer_cik'], e['entry'][:4]) for e in allev if e['set'] == 'base')
    rep = sum(1 for e in gone if py[(e['issuer_cik'], e['entry'][:4])] > 3)
    iss = Counter(e['issuer_cik'] for e in gone)
    print(f'removed events from {len(iss)} issuers; {rep} ({rep / max(1, len(gone)):.0%}) sit in issuer-years with more than 3 base events; '
          f'top issuers by removed events (cik, ticker, n): ' + str([(c, next(e['ticker'] for e in gone if e['issuer_cik'] == c), n) for c, n in iss.most_common(12)]))
    base_keys = {(b['issuer_cik'], b['ticker'], b['entry']) for b in allev if b['set'] == 'base'}
    print('refined-only events (a later discretionary crossing once routine filings were removed):',
          sum(1 for e in allev if e['set'] == 'refined' and (e['issuer_cik'], e['ticker'], e['entry']) not in base_keys))
    print('No returns were computed or read.')


# ------------------------------------------------------------------ self-test
def _row(cik, tx, filed, price, issuer='1', ticker='ABC'):
    return {'review_flags': [], 'security_title': 'Common Stock', 'ticker_at_filing': ticker, 'issuer_cik': issuer,
            'owners': [{'cik': cik, 'name': 'Jane Doe', 'relationship': 'Director', 'title': ''}],
            'transaction_dates': [tx], 'filing_date': filed, 'insider_weighted_price': str(price),
            'accession': f'acc-{cik}-{tx}', 'transaction_row_keys': ['k1']}


def selftest():
    import os
    os.environ['ALLOW_WEEKDAY_CALENDAR'] = '1'
    from cluster_counts_by_year import find_events, sessions
    cal = [d for d in sessions() if d >= '2020-01-01'][:260]

    # prior_months wraps the year
    assert prior_months('2020-01-15') == ['2019-12', '2019-11', '2019-10']
    # same price within one cent: three owners at 10.00 / 10.005 / 10.01 flag; 10.00 / 10.01 / 10.02 do not
    mk = lambda ps: [_row(f'o{i}', cal[5], cal[6], p) for i, p in enumerate(ps)]
    assert same_day_same_price(mk([10.00, 10.005, 10.01]))[0] == {0, 1, 2}
    assert same_day_same_price(mk([10.00, 10.01, 10.02]))[0] == set()
    assert same_day_same_price(mk([10.0, 10.0]))[0] == set()                      # only two owners
    assert same_day_same_price(mk([10.00, 10.01, 10.02]), tol=0.02)[0] == {0, 1, 2}   # wider tolerance
    assert same_day_same_price(mk([10.00, 10.00, 10.00]), min_buyers=4)[0] == set()   # stricter owner count
    assert same_day_same_price(mk([10.00, 10.00, 10.00]), tol=0.0)[0] == {0, 1, 2}    # exact price
    r0 = _row('same', cal[5], cal[6], 10.0); r1 = _row('same', cal[5], cal[7], 10.0); r2 = _row('o2', cal[5], cal[8], 10.0)
    assert same_day_same_price([r0, r1, r2])[0] == set()                          # one owner twice is still two owners

    # 1. routine: four owners, same date, same price -> base has the event, refined has none
    routine = [_row(c, cal[30], cal[31 + k], 10.00) for k, c in enumerate('abcd')]
    assert len(find_events(routine, cal)) == 1
    assert len(find_events_refined(routine, cal, False)[0]) == 1 and find_events_refined(routine, cal, True)[0] == []
    # 2. discretionary: four owners, different prices -> kept
    disc = [_row(c, cal[30 + k], cal[31 + k], 10.0 + 0.5 * k) for k, c in enumerate('abcd')]
    ev, _ = find_events_refined(disc, cal, True)
    assert len(ev) == 1 and ev[0]['buyers'] == 4 and ev[0]['n_routine_rows'] == 0
    assert len(ev[0]['owners']) == 4 and all(o[1] == 'Director' for o in ev[0]['owners']), ev[0]['owners']   # buyer roles are carried
    # 2b. distinct purchase dates (C41): same date at different prices is not routine, so the base keeps it; the date rules do not
    oneday = [_row(c, cal[30], cal[31 + k], 10.0 + 0.5 * k) for k, c in enumerate('abcd')]
    assert len(find_events_refined(oneday, cal, True, date_rule='')[0]) == 1
    assert all(find_events_refined(oneday, cal, True, date_rule=r)[0] == [] for r in ('d2', 'd3', 'm4'))
    twodays = [_row(c, cal[30 + (k // 2)], cal[31 + k], 10.0 + 0.5 * k) for k, c in enumerate('abcd')]
    assert len(find_events_refined(twodays, cal, True, date_rule='d2')[0]) == 1
    assert find_events_refined(twodays, cal, True, date_rule='d3')[0] == [] and find_events_refined(twodays, cal, True, date_rule='m4')[0] == []
    ev, _ = find_events_refined(disc, cal, True, date_rule='m4')                   # four buyers on four different days
    assert len(ev) == 1 and ev[0]['distinct_dates'] == 4 and ev[0]['match4']
    # a buyer who bought on two days can supply the missing date: a on days 30 and 31, b, c on day 30, d on day 31 -> 4 buyers, only 2 dates -> m4 fails
    shared = [dict(_row('a', cal[30], cal[32], 10.0), transaction_dates=[cal[30], cal[31]]), _row('b', cal[30], cal[33], 10.5),
              _row('c', cal[30], cal[34], 11.0), _row('d', cal[31], cal[35], 11.5)]
    assert find_events_refined(shared, cal, True, date_rule='m4')[0] == [] and len(find_events_refined(shared, cal, True, date_rule='d2')[0]) == 1
    # the entry moves to the filing that makes the date rule true (not the filing that made the fourth buyer)
    late_dates = [_row(c, cal[30], cal[31 + k], 10.0 + 0.5 * k) for k, c in enumerate('abcd')] + \
                 [_row('e', cal[33], cal[36], 12.0), _row('f', cal[34], cal[38], 12.5)]
    ev0, _ = find_events_refined(late_dates, cal, True, date_rule='')
    ev3, _ = find_events_refined(late_dates, cal, True, date_rule='d3')
    assert ev0[0]['entry'] == cal[35] and ev3[0]['entry'] == cal[39], (ev0[0]['entry'], ev3[0]['entry'])
    assert find_events_refined(late_dates, cal, False, date_rule='d3')[0][0]['entry'] == cal[35]   # the base set ignores the date rule
    # 3. look-back only: a third same-price owner filing AFTER the entry cannot undo the event
    late = [_row('a', cal[30], cal[31], 10.0), _row('b', cal[30], cal[32], 10.0), _row('c', cal[31], cal[33], 10.5),
            _row('d', cal[32], cal[34], 11.0), _row('e', cal[30], cal[36], 10.0)]
    ev, _ = find_events_refined(late, cal, True)
    assert len(ev) == 1 and ev[0]['entry'] == cal[35], ev
    # 4. issuer routine mode (b): same-price clusters in two of the three prior months drop a later discretionary event
    fdate = cal[200]
    m1, m2, m3 = prior_months(fdate)
    first = lambda m: next(d for d in cal if d.startswith(m))
    nxt = lambda d: cal[cal.index(d) + 1]
    hist = []
    for m, price in ((m1, 20.0), (m2, 22.0)):
        d = first(m)
        hist += [_row(f'x{k}', d, nxt(d), price) for k in range(3)]
    cluster = [_row(c, cal[195 + k], cal[196 + k], 30.0 + k) for k, c in enumerate('abcd')]
    ev, st = find_events_refined(hist + cluster, cal, True)
    assert ev == [] and st['dropped_issuer_routine_mode'] == 1, (ev, st)
    assert len(find_events_refined(hist + cluster, cal, False)[0]) == 1
    ev, _ = find_events_refined(hist[:3] + cluster, cal, True)                    # only one routine month: kept
    assert len(ev) == 1
    # look-back only for (b): the same history filed AFTER the event does not drop it
    posthist = [dict(r, filing_date=cal[230]) for r in hist]
    assert len(find_events_refined(posthist + cluster, cal, True)[0]) == 1

    # enrich: purchase lines are attached from the database and filtered to the window
    import sqlite3
    dbm = sqlite3.connect(':memory:')
    dbm.execute('CREATE TABLE purchase_candidates (accession TEXT, transaction_row_key TEXT, payload TEXT)')
    for k in range(2):
        dbm.execute('INSERT INTO purchase_candidates VALUES (?,?,?)', (f'acc{k}', 'r1', json.dumps({
            'transaction_date': cal[10 + 40 * k], 'owners': [{'cik': f'o{k}'}], 'shares': 100, 'price_per_share': 5.0,
            'shares_after': 1000, 'direct_indirect': 'D'})))
    evs = [{'entry': cal[12], 'window_start': cal[0], 'rows': [{'acc': 'acc0', 'keys': ['r1']}, {'acc': 'acc1', 'keys': ['r1']}]}]
    enrich(evs, dbm)
    assert [l['owner'] for l in evs[0]['lines']] == ['o0'] and 'rows' not in evs[0] and 'window_start' not in evs[0], evs   # acc1 is outside the window

    # identity v2
    c10 = {d: 10.0 for d in cal[:30]}
    ratios = lambda prices: ratios_for([(cal[20 + k], p) for k, p in enumerate(prices)], c10)
    assert identity_v2(ratios([10.4]))[0] == 'ok'
    assert identity_v2(ratios([15.0, 15.1, 14.9]))[0:1] == ('split_ok',) and identity_v2(ratios([15.0, 15.1, 14.9]))[2] == 1.5
    assert identity_v2(ratios([15.0]))[0] == 'split_unverified'                    # grid hit but one price only
    assert identity_v2(ratios([2.0, 2.05, 1.95]))[0] == 'split_ok'                 # 1-for-5 reverse split (factor 0.2)
    assert identity_v2(ratios([15.0, 15.1, 14.9, 40.0]))[0] == 'split_ok'          # 3 of 4 inside the band = 75%
    assert identity_v2(ratios([15.0, 40.0, 15.0]))[0] == 'mismatch'                # 2 of 3 = 67%, below the bar
    assert identity_v2(ratios([15.0, 40.0, 90.0]))[0] == 'mismatch'                # unstable
    assert identity_v2(ratios([73.0, 74.0, 72.0]))[0] == 'mismatch'                # 7.3 is off the grid
    assert identity_v2([])[0] == 'unverifiable'

    # collapse (option C): entries 0, 10, 21 sessions apart -> keep 0 and 21; other issuer unaffected
    items = [{'cik': '1', 'entry': cal[100]}, {'cik': '1', 'entry': cal[110]}, {'cik': '1', 'entry': cal[121]}, {'cik': '2', 'entry': cal[105]}]
    kept = collapse(items, lambda d: cal.index(d))
    assert [(e['cik'], e['entry']) for e in kept] == [('1', cal[100]), ('1', cal[121]), ('2', cal[105])], kept
    items2 = [{'cik': '1', 'entry': cal[100]}, {'cik': '1', 'entry': cal[120]}]
    assert len(collapse(items2, lambda d: cal.index(d))) == 1                       # 20 sessions later: still inside the hold

    # cut table: 100 entries in each quarter 2010Q1..2025Q4 (64 quarters) -> sealed from 2022Q1 = 16 quarters = 25.0%
    syn = []
    for y in range(2010, 2026):
        for n in (1, 2, 3, 4):
            syn += [{'cik': 'i', 'entry': f'{y}-{(n - 1) * 3 + 2:02d}-15'}] * 100
    tot, rows, best = cut_table(syn)
    assert tot == 6400 and best[0] == '2022Q1' and abs(best[2] - 0.25) < 1e-9, best
    assert quarter_start('2024Q3') == '2024-07-01'
    print('selftest ok')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?', choices=['events', 'year', 'summary'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--events', default='reports/events_refined.json')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == 'events':
        build_events(a.out or 'reports/events_refined.json')
    elif a.cmd == 'year':
        year_job(int(a.arg), a.events, a.out or f'reports/year_{a.arg}.json')
    elif a.cmd == 'summary':
        summary(a.arg or 'reports', a.events)
    else:
        ap.error('give a subcommand or --selftest')
