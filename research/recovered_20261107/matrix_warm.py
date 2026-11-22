from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal as D
from statistics import mean, median
from zipfile import ZipFile
import csv, io, json, re, sys

def from_zip(path, name):
    with ZipFile(path) as archive:
        return archive.read(name)

rows = json.loads(from_zip(sys.argv[1], 'free_year_candidates.json'))['opportunities']
etfs = defaultdict(dict)
for bar in csv.DictReader(io.StringIO(from_zip('1.zip', 'market_benchmark_bars.csv').decode())):
    etfs[bar['symbol']][bar['date']] = bar
days = sorted(etfs['SPY'])
flags = {'filing_affirms_10b5_1','possible_10b5_1','possible_non_discretionary','not_acquisition','missing_numeric_amount'}
title = re.compile(r'(?:class [a-z0-9]+ )?common (?:stock|shares)(?:,?\s+(?:no par value|(?:par value )?\$\d+(?:\.\d+)?(?: par value)?(?: per share)?\.?))?', re.I)
entity = re.compile(r'\b(?:LLC|LLP|LLLP|LP|LTD|Limited|Inc|Corp|Corporation|Holdings|Partners|Capital|Fund|Trust|Foundation|Management|Group|Company|PLC|Investments|Advisors|Associates)\b', re.I)
cohort = [r for r in rows if '2025-12-01' <= r['filing_date'] <= '2026-09-30'
          and not flags.intersection(r['review_flags']) and title.fullmatch(' '.join((r['security_title'] or '').split()))]
assert sum(r['filing_date'] >= '2026-01-01' for r in cohort) == 6604

def select(use_entity, strategy, offset=0, same_ticker=True):
    disclosures = defaultdict(lambda: defaultdict(list))
    for row in cohort:
        owners = row['owners']
        if len(owners) != 1 or not owners[0]['cik']:
            continue
        owner = owners[0]
        if not {'Director', 'Officer'}.intersection(owner['relationship'].split(',')):
            continue
        if use_entity and entity.search(owner['name']):
            continue
        if not row['transaction_dates'] or not row['ticker_at_filing']:
            continue
        day = days[bisect_right(days, row['filing_date'])]
        key = (row['issuer_cik'], row['ticker_at_filing'], row['security_title'].upper()) if same_ticker else (row['issuer_cik'],row['ticker_at_filing'])
        disclosures[key][day].append(row)
    events = []
    exact = []
    for by_day in disclosures.values():
        seen = []
        for entry, current in sorted(by_day.items()):
            i = bisect_right(days, entry)-1
            start = days[max(0, i-15+offset)]
            def active(items):
                return {r['owners'][0]['cik']: r for r in items if any(start <= d < entry for d in r['transaction_dates'])}
            before = active(seen)
            seen.extend(current)
            after = active(seen)
            if current[0]['filing_date'] < '2026-01-01':
                continue
            if strategy == 'previous':
                prior_start = days[max(0, i-16+offset)]
                before = {r['owners'][0]['cik']: r for r in seen[:-len(current)] if any(prior_start <= d < entry for d in r['transaction_dates'])}
            if strategy == 'first' and events and any(x[0] == current[0]['issuer_cik'] and x[2]['ticker_at_filing'] == current[0]['ticker_at_filing'] for x in events):
                continue
            if len(before) < len(after) == 4:
                exact.append(current[0])
            if len(before) < 4 <= len(after):
                cfo = any('Officer' in r['owners'][0]['relationship'].split(',') and re.search(r'\b(?:CFO|chief financial officer)\b',r['owners'][0]['title'],re.I)
                          for r in seen if r['owners'][0]['cik'] in after and any(start <= d < entry for d in r['transaction_dates']))
                row = min(current, key=lambda r: (r.get('outcome_status')!='ok',r['filing_date'],r['accession']))
                assert not row.get('next_open_date') or row['next_open_date'] == entry
                events.append((row['issuer_cik'], entry, row, cfo, len(after)))
    return events, exact

def has(row, horizon='21'):
    return row['horizons'].get(horizon, {}).get('status') == 'ok'

if __name__ == '__main__' and len(sys.argv)==2:
    for e in (False,True):
        for s in ('same','previous','first'):
            for o in (0,1,-1):
                for t in (True,False):
                    a,b = select(e,s,o,t)
                    out=Counter(x[3] for x in a if has(x[2]))
                    print(e,s,o,t,len(a),len(b),sum(has(r) for r in b),dict(out),sum(has(x[2],'6m') for x in a))
