"""Reproduce the January–September 2026 provisional market-regime pilot."""

from collections import Counter, defaultdict
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from zipfile import ZipFile
import csv, io, json, re, sys

from price_outcomes import atr14

stock_source, etf_source = map(Path, sys.argv[1:3])
with ZipFile(stock_source) as archive:
    candidates = json.loads(archive.read('free_year_candidates.json'))['opportunities']
with ZipFile(etf_source) as archive:
    metadata = json.loads(archive.read('market_benchmark_source.json'))
    prices = defaultdict(dict)
    for bar in csv.DictReader(io.StringIO(archive.read('market_benchmark_bars.csv').decode())):
        symbol, date = bar['symbol'], bar['date']
        assert date not in prices[symbol]
        prices[symbol][date] = bar
symbols = ('SPY','ONEQ','IWM')
days = sorted(prices['SPY'])
assert all(sorted(prices[s]) == days for s in symbols)
assert len(days) == metadata['session_count']
spy = [prices['SPY'][day] for day in days]
contexts = {}
for i, day in enumerate(days):
    if i < 22:
        continue
    start, end = days[i-22], days[i-1]
    assert start < end < day
    spy_atr = atr14(spy, i)
    direction = (D(prices['SPY'][end]['close']) - D(prices['SPY'][start]['close'])) / spy_atr
    regime = 'Down' if direction <= D('-0.5') else 'Up' if direction >= D('0.5') else 'Flat'
    returns = {s: D(prices[s][end]['close']) / D(prices[s][start]['close']) - 1 for s in symbols}
    contexts[day] = regime, returns
flags = {'filing_affirms_10b5_1','possible_10b5_1','possible_non_discretionary','not_acquisition','missing_numeric_amount'}
title = re.compile(r'(?:class [a-z0-9]+ )?common (?:stock|shares)(?:,?\s+(?:no par value|(?:par value )?\$\d+(?:\.\d+)?(?: par value)?(?: per share)?\.?))?', re.I)
cohort = [r for r in candidates if '2026-01-01' <= r['filing_date'] <= '2026-09-30'
          and not flags.intersection(r['review_flags']) and title.fullmatch(' '.join((r['security_title'] or '').split()))]
assert len(cohort) == 6604
counts = Counter()
groups = defaultdict(list)
for row in cohort:
    prior = row.get('entry_features', {}).get('prior_returns', {}).get('21')
    if not prior:
        counts['No stock lookback'] += 1
        continue
    entry = row['next_open_date']
    if entry not in contexts:
        counts['No market lookback'] += 1
        continue
    move = D(prior['percent']) / 100
    if move >= 0:
        counts['Stock flat or up'] += 1
        continue
    regime, returns = contexts[entry]
    if not all(move < returns[s] for s in symbols):
        counts['Stock down, did not lag all three'] += 1
        continue
    counts['Stock down, lagged all three'] += 1
    groups[regime].append(row)
assert sum(counts.values()) == len(cohort)

results = {}
for regime in ('Down','Flat','Up'):
    rows = groups[regime]
    results[regime] = {}
    for horizon in ('11','21','43','64','6m'):
        outcomes = []
        for row in rows:
            h = row['horizons'].get(horizon,{})
            if h.get('status') != 'ok':
                continue
            entry, exit = row['next_open_date'], h['end_date']
            assert entry <= exit
            stock = D(h['next_open']['end_return_atr'])
            scale = D(row['next_open']) / D(row['atr14'])
            matched = {s: (D(prices[s][exit]['close']) / D(prices[s][entry]['open']) - 1) * scale for s in symbols}
            outcomes.append((row['issuer_cik'],entry,stock,matched))
        if not outcomes:
            continue
        def stats(values):
            return {'mean':float(mean(values)), 'median':float(median(values))}
        stock = stats([x[2] for x in outcomes])
        comparisons = {s: {'etf':stats([x[3][s] for x in outcomes]), 'excess':stats([x[2]-x[3][s] for x in outcomes])} for s in symbols}
        by_date = defaultdict(list)
        for item in outcomes:
            by_date[item[1]].append(item)
        equal_date = {
            'stock': float(mean(mean(x[2] for x in observations) for observations in by_date.values())),
            **{s: {
                'etf': float(mean(mean(x[3][s] for x in observations) for observations in by_date.values())),
                'excess': float(mean(mean(x[2]-x[3][s] for x in observations) for observations in by_date.values())),
            } for s in symbols},
        }
        bound = [float(mean(x[2]-choose(x[3].values()) for x in outcomes)) for choose in (max,min)]
        results[regime][horizon] = {'n':len(outcomes),'missing_horizon':len(rows)-len(outcomes),
                                    'issuers':len({x[0] for x in outcomes}),'entry_dates':len({x[1] for x in outcomes}),
                                    'stock':stock,'comparisons':comparisons,'assignment_mean_excess_bounds':bound, 'equal_entry_date':equal_date}
print(json.dumps({'counts':counts, 'results':results, 'market_source':metadata['source'],
                  'market_archive_sha256':sha256(etf_source.read_bytes()).hexdigest(),
                  'stock_archive_sha256':sha256(stock_source.read_bytes()).hexdigest()}, indent=2))
