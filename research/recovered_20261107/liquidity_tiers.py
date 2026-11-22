import contextlib
import io

with contextlib.redirect_stdout(io.StringIO()):
    from wider import *

original = json.loads(from_zip('matrix.zip', 'free_year_candidates.json'))
current = json.loads(from_zip(sys.argv[1], 'free_year_candidates.json'))
for key in ('database_sha256', 'price_sha256_by_date'):
    assert original['metadata'][key] == current['metadata'][key]
for a,b in zip(original['opportunities'],current['opportunities'],strict=True):
    b.get('entry_features',{}).pop('average_daily_dollars_15',None)
    assert a==b

spy = etfs['SPY']
def true_range(k):
    bar = spy[days[k]]
    prior = D(spy[days[k-1]]['close'])
    high, low = D(bar['high']), D(bar['low'])
    return max(high-low, abs(high-prior), abs(low-prior))

def returns(row, horizon='21'):
    entry=row['next_open_date']
    h=row['horizons'][horizon]
    end=h['end_date']
    scale=D(row['next_open'])/D(row['atr14'])
    stock=D(h['next_open']['end_return_atr'])
    bench=(D(spy[end]['close'])/D(spy[entry]['open'])-1)*scale
    return stock,bench,stock-bench

sample=[]
for (key,i),(row,cfo,n) in short.items():
    if not has(row):
        continue
    entry=calendar[i]
    index=days.index(entry)
    regime=(D(spy[days[index-1]]['close'])-D(spy[days[index-16]]['close']))/mean(
        true_range(k) for k in range(index-14,index))
    features=row['entry_features']
    decline=-D(features['prior_returns']['15']['atr'])
    adv=D(features['average_daily_dollars_15'])
    narrow=cfo and 2<=decline<=5 and regime>=D('.5')
    tier=3 if narrow else 2 if cfo else 1
    sample.append((tier,adv,D(row['next_open']),entry,key[1],row))

assert Counter(t[0] for t in sample)=={3:10,2:47,1:80}
with ZipFile('zero.zip') as z:
    known=json.loads(z.read('free_year_zero_buyer_price_candidates.json'))
for tier,adv,opening,entry,ticker,_ in sample:
    if tier==3:
        assert adv==D(known[entry]['stocks'][ticker]['average_daily_dollars_15'])
assert sum(tier==3 and adv>=3_000_000 for tier,adv,*_ in sample)==7

def stats(group,horizon='21'):
    values=list(zip(*(returns(t[-1],horizon) for t in group)))
    excess=values[2]
    return [len(group),len({t[3] for t in group}),round(median(t[1] for t in group)),
            sum(t[2]<5 for t in group),*[round(mean(v),4) for v in values],round(median(excess),4),
            sum(v>0 for v in excess),round(mean(sorted(excess)[:-1]),4)]

for tier in (3,2,1,0):
    group=[t for t in sample if not tier or t[0]==tier]
    kept=[t for t in group if t[1]>=3_000_000]
    dropped=[t for t in group if t[1]<3_000_000]
    print(tier,'all',stats(group),'kept',stats(kept),'dropped',stats(dropped))
    paired=[t for t in kept if has(t[-1],'43')]
    print(tier,'paired 21',stats(paired),'43',stats(paired,'43'))
