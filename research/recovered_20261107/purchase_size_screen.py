import contextlib
import io

with contextlib.redirect_stdout(io.StringIO()):
    from liquidity_tiers import *

def purchase_dollars(row):
    amount = D(row['aggregate_dollars'] or 0)
    return amount if amount.is_finite() and amount > 0 else D(0)

def active_purchases(minimum=None):
    events = {}
    for key, by_date in by_security.items():
        seen = []
        for i in range(min(by_date), len(calendar)):
            entry = calendar[i]
            start = calendar[max(0, i-15)]
            def eligible(row):
                dates = row['transaction_dates']
                if minimum is None:
                    return any(start <= day < entry for day in dates)
                return all(start <= day < entry for day in dates) and purchase_dollars(row) >= minimum

            seen = [r for r in seen if eligible(r)]
            before = {r['owners'][0]['cik'] for r in seen}
            current = by_date.get(i, ())
            new = [r for r in current if eligible(r)]
            seen.extend(new)
            after = {r['owners'][0]['cik'] for r in seen}
            if len(before) < 4 <= len(after):
                r = min(new if minimum is not None else current,
                        key=lambda r:(r.get('outcome_status')!='ok',r['filing_date'],r['accession']))
                if r['filing_date'] < '2026-01-01':
                    continue
                whole = [a for a in seen if all(start <= day < entry for day in a['transaction_dates'])]
                values = [purchase_dollars(a) for a in whole]
                cfo = any('Officer' in a['owners'][0]['relationship'].split(',') and
                          re.search(r'\b(?:CFO|chief financial officer)\b',a['owners'][0]['title'] or '',re.I)
                          for a in seen)
                events[key,i] = (r,max(values,default=D(0)),sum(values),len(seen)-len(whole),
                                 sum(x<=0 for x in values),cfo)
    return events

def eligible_trades(events):
    return {k:v for k,v in events.items() if has(v[0])
            and D(v[0]['entry_features']['average_daily_dollars_15'])>=3_000_000}

def narrow(k,v):
    entry=calendar[k[1]]
    j=days.index(entry)
    regime=(D(spy[days[j-1]]['close'])-D(spy[days[j-16]]['close']))/mean(
        true_range(i) for i in range(j-14,j))
    drop=-D(v[0]['entry_features']['prior_returns']['15']['atr'])
    return regime>=D('.5') and 2<=drop<=5

def show(label,e):
    if not e:
        print(label,0)
        return
    s,b,x=zip(*(returns(v[0]) for v in e.values()))
    above=sorted(x)
    print(label,len(e),len({k[1] for k in e}),len({k[0][0] for k in e}),*[f'{a:+.4f}' for a in (
        mean(s),mean(b),mean(x),median(x))],sum(a>0 for a in s),sum(a>0 for a in x),
        f'{mean(above[:-1]):+.4f}' if len(e)>1 else 'NA',
        'Narrow',sum(narrow(k,v) for k,v in e.items()))

base_events=active_purchases()
assert {k:v[0] for k,v in base_events.items()}=={k:v[0] for k,v in short.items()}
base=eligible_trades(base_events)
assert len(base)==91
price_setup={k:v for k,v in base.items() if narrow(k,v)}
assert len(price_setup)==15
print('coverage',sum(v[3]>0 for v in base.values()),sum(v[3] for v in base.values()),
      sum(v[4]>0 for v in base.values()),min(v[1] for v in base.values()))
print('quartiles max/total',[(i,quantiles) for i,quantiles in
      ((i,[sorted(v[i] for v in base.values())[j] for j in (22,45,68)]) for i in (1,2))])
show('baseline',base)
for lower,upper in [(0,25_000),(25_000,50_000),(50_000,100_000),(100_000,500_000),(500_000,D('Infinity'))]:
 show(f'largest band {lower}-{upper}',{k:v for k,v in base.items() if lower<=v[1]<upper})
for size in (25_000,50_000,100_000,250_000,500_000):
 selected={k:v for k,v in base.items() if v[1]>=size}
 show(f'largest >= {size}',selected)
 show(f'  in price setup {size}',{k:v for k,v in selected.items() if k in price_setup})
for size in (100_000,250_000,500_000,1_000_000):
 show(f'cluster total >= {size}',{k:v for k,v in base.items() if v[2]>=size})
for size in (25_000,50_000,100_000):
 screened=eligible_trades(active_purchases(D(size)))
 print('shared entry',size,len(base.keys()&screened.keys()),'new entry dates',len(screened.keys()-base.keys()))
 show(f'four qualifying purchases >= {size}',screened)
