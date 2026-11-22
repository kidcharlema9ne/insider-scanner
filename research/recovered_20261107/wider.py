from matrix_warm import *
from bisect import bisect_left

data = json.loads(from_zip(sys.argv[1], 'free_year_candidates.json'))
calendar = sorted(data['metadata']['price_sha256_by_date'])
by_security = defaultdict(lambda: defaultdict(list))
for row in rows:
    if not calendar[0] <= row['filing_date'] <= '2026-09-30':
        continue
    if flags.intersection(row['review_flags']) or not title.fullmatch(' '.join((row['security_title'] or '').split())):
        continue
    owners = row['owners']
    if len(owners) != 1 or not owners[0]['cik']:
        continue
    owner = owners[0]
    if not {'Director','Officer'}.intersection(owner['relationship'].split(',')) or entity.search(owner['name']):
        continue
    if not row['transaction_dates'] or not row['ticker_at_filing']:
        continue
    i = bisect_right(calendar, row['filing_date'])
    key = row['issuer_cik'], row['ticker_at_filing'], row['security_title'].upper()
    by_security[key][i].append(row)

def run(window):
    events = {}
    status = {}
    for key, by_date in by_security.items():
        seen = []
        active_event = None
        for i in range(min(by_date), len(calendar)):
            entry = calendar[i]
            start = calendar[max(0, i-window)]
            seen = [r for r in seen if any(start <= d < entry for d in r['transaction_dates'])]
            before = {r['owners'][0]['cik'] for r in seen}
            current = by_date.get(i, [])
            new = [r for r in current if any(start <= d < entry for d in r['transaction_dates'])]
            seen.extend(new)
            after = {r['owners'][0]['cik'] for r in seen}
            if len(before) < 4:
                active_event = None
            if len(before) < 4 <= len(after):
                cfo = any('Officer' in r['owners'][0]['relationship'].split(',') and
                          re.search(r'\b(?:CFO|chief financial officer)\b',r['owners'][0]['title'] or '',re.I)
                          for r in seen)
                r = min(current,key=lambda r:(r.get('outcome_status')!='ok',r['filing_date'],r['accession']))
                assert not r.get('next_open_date') or r['next_open_date']==entry
                active_event=(key,i)
                events[active_event] = r,cfo,len(after)
            if active_event is not None:
                status[key,i] = active_event
    return events, status

short_all,_ = run(15)
wide_all,wide_status = run(30)
def in_scope(events):
    return {k:v for k,v in events.items() if v[0]['filing_date'] >= '2026-01-01'}
short,wide = in_scope(short_all),in_scope(wide_all)
base,_ = select(True,'same')
assert {(i,t,r['ticker_at_filing'],cfo,n) for i,t,r,cfo,n in base} == {
    (key[0],calendar[i],r['ticker_at_filing'],cfo,n) for (key,i),(r,cfo,n) in short.items()
}
both = short.keys() & wide.keys()
only15 = short.keys() - wide.keys()
only30 = wide.keys() - short.keys()
earlier = defaultdict(list)
for k in only15:
    w = wide_status[k]
    assert w[1] < k[1]
    earlier[w].append(k)

def stats(label, keys, events, h='21'):
    q=[]
    for key,i in sorted(keys):
        row,cfo,_=events[key,i]
        if not has(row,h):continue
        entry=calendar[i]; a=row['horizons'][h]; end=a['end_date']
        stock=D(a['next_open']['end_return_atr'])
        scale=D(row['next_open'])/D(row['atr14'])
        b=[(D(etfs[s][end]['close'])/D(etfs[s][entry]['open'])-1)*scale for s in ('SPY','ONEQ','IWM')]
        q.append((key[0],i,cfo,stock,*b,stock-b[0],stock-b[1],stock-b[2]))
    if not q:return
    col=list(zip(*q))
    print(label,h,len(keys),len(q),len(set(col[0])),len(set(col[1])),sum(col[2]),*[f'{mean(x):+.3f}' for x in col[3:]],
          'median',f'{median(col[7]):+.3f}','beats',sum(x>0 for x in col[7]),'stock-up',sum(x>0 for x in col[3]))

print('SCOPE',len(short),len(wide),len(both),len(only15),len(only30))
print('ISSUERS',len({key[0] for key,i in short}),len({key[0] for key,i in wide}),len({key[0] for key,i in wide}-{key[0] for key,i in short}))
print('only15 mapped',len(earlier), 'earlier 30 only',len(earlier.keys()&only30),'earlier 30 shared',len(earlier.keys()&both),'prepilot',len(earlier.keys()-wide.keys()))
leads=[min(k[1] for k in earlier[w])-w[1] for w in earlier.keys()&only30]
print('earlier lead',len(leads),median(leads),min(leads),max(leads))
print('CFO flip on shared',Counter((short[k][1],wide[k][1]) for k in both))
for k,e in [('15',short),('30',wide)]:
    for h in ('21','43','64','6m'):
        stats(k,e,e,h)
        for cfo in (True,False):
            stats(f'{k} CFO={cfo}',[key for key,v in e.items() if v[1]==cfo],e,h)
stats('shared 15',both,short)
stats('shared 30',both,wide)
stats('15-date no new 30-entry',only15,short)
stats('30-only dates',only30,wide)
stats('30-only earlier than matching 15',earlier.keys()&only30,wide)
stats('30-only no matching 15 during active stretch',only30-earlier.keys(),wide)
