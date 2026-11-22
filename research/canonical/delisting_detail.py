"""C36 (declared 9 Nov 2026, BEFORE any run; Michael: "go ahead" to classifying the unexplained names).  Follow-up to Entry 74 (C35).  Counts and name lists only; no
return is joined; development entries only (D-068).

TARGET SET: refined events 2006-2020 with NO price series in the archive (Entry 38 census) that are either (a) 'delisted or deregistered' within 59 days of entry
by the C35 rule (the 41 names of Entry 74) or (b) any no-price event entered in 2008 or 2009 (the years with 31% and 24% missing and 17 of the 23 later bankruptcies).
Per company, re-read from the SEC submissions index: name, SIC code and description, state, and the forms in the window.
BANK FLAG: SIC 6021, 6022, 6029, 6035, 6036 (commercial banks and savings institutions) or a name containing BANK, BANCORP, BANCSHARES, SAVINGS, FINANCIAL with SIC 6711 or 6199.
FDIC MATCH (candidate only, for the eye): the FDIC failed-bank list (tries the FDIC csv; if the download fails the section says so) matched to a company by
normalised distinctive name tokens (generic words such as BANK, BANCORP, FINANCIAL, INC, CORP, HOLDING removed; one token set must contain the other), the same state,
and a failure closing date 0 to 365 days after entry.  Reported at 59, 120 and 365 days.  A name match is NOT proof that the stock was wiped out; it is a flag.
OUTPUT: (1) every name in the 41 with SIC, state, forms seen in the window; (2) for the 2008-2009 no-price names: bank versus not bank, how many have a
Form 15 or 25 within 365 days, and the FDIC-candidate counts; (3) the same bank share and FDIC-candidate counts for all no-price events by year;
(4) the deep-fall bound of Entry 74 recomputed with B = FDIC-candidate matches within 59 days (scenario shares 100%, 50%, 25%), same assumptions.

Usage:  python delisting_detail.py run YEAR_FOLDER --out FILE
        python delisting_detail.py --selftest
"""
import csv, io, json, os, re, sys, time, urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, assert_allowed
import earnings_dates as ed
import delisting_check as dc

BANK_SIC = {'6021', '6022', '6029', '6035', '6036'}
NAME_BANK = re.compile(r'BANK|BANCORP|BANCSHARES|SAVINGS|FINANCIAL')
GENERIC = {'the', 'bank', 'banks', 'bancorp', 'bancshares', 'bancorporation', 'financial', 'corp', 'corporation', 'inc', 'co', 'company', 'holding', 'holdings',
           'group', 'of', 'and', 'trust', 'savings', 'national', 'federal', 'fsb', 'state', 'ltd', 'llc', 'na', 'fsb', 'association', 'community', 'services', 'banking'}
FDIC_URLS = ['https://www.fdic.gov/bank/individual/failed/banklist.csv', 'https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list/banklist.csv']


def toks(name):
    return {t for t in re.sub(r'[^a-z0-9 ]', ' ', name.lower()).split() if t not in GENERIC and len(t) > 1}


def is_bank(sic, name):
    return str(sic) in BANK_SIC or (bool(NAME_BANK.search(name.upper())) and str(sic) in ('6711', '6199'))


def fdic_match(name, state, entry, failed, win):
    E = date.fromisoformat(entry)
    c = toks(name)
    hits = []
    for f in failed:
        d = (f['closing'] - E).days
        if 0 <= d <= win and f['state'] == state:
            t = f['tokens']
            if t and c and (t <= c or c <= t):
                hits.append((f['name'], f['closing'].isoformat()))
    return hits


def load_fdic():
    for u in FDIC_URLS:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'insider-buying-research failed-bank-list reader'})
            raw = urllib.request.urlopen(req, timeout=60).read().decode('cp1252', errors='replace')
            rows = list(csv.DictReader(io.StringIO(raw)))
            out = []
            for r in rows:
                r = {k.strip(): v.strip() for k, v in r.items() if k}
                nm, st, cd = r.get('Bank Name', ''), r.get('ST') or r.get('State', ''), r.get('Closing Date', '')
                dt = None
                for fmt in ('%d-%b-%y', '%B %d, %Y', '%m/%d/%Y', '%d-%b-%Y'):
                    try:
                        dt = datetime.strptime(cd, fmt).date()
                        break
                    except ValueError:
                        pass
                if nm and dt:
                    out.append({'name': nm, 'state': st, 'closing': dt, 'tokens': toks(nm)})
            if out:
                print(f'FDIC failed-bank list loaded from {u}: {len(out)} banks, closings {min(f["closing"] for f in out)} to {max(f["closing"] for f in out)}')
                return out
        except Exception as e:
            print(f'FDIC list not loaded from {u}: {type(e).__name__}: {e}')
    print('FDIC failed-bank list NOT AVAILABLE; FDIC-candidate sections are skipped')
    return []


def run(year_dir, out):
    agent = os.environ['SEC_USER_AGENT'].strip()
    ev = []
    for fn in sorted(Path(year_dir).glob('year_*.json')):
        for r in json.loads(Path(fn).read_text())['results']:
            if r['set'] != 'refined' or r['entry'] > DEV_END or r['status'] != 'no_price':
                continue
            assert_allowed(r['entry'])
            ev.append({'cik': str(r['cik']).zfill(10), 'entry': r['entry'], 'sym': r['sym']})
    ciks = sorted({e['cik'] for e in ev})
    print(f'no-price development events {len(ev)}; {len(ciks)} companies (all years; the bank-share table by year needs all)')
    meta, cache = {}, {}
    for n, c in enumerate(ciks):
        time.sleep(0.2)
        js = ed.get(f'{ed.BASE}CIK{c}.json', agent)
        if not isinstance(js, dict):
            continue
        rows = dc.extract(js.get('filings', {}).get('recent', {}))
        for fl in js.get('filings', {}).get('files', []):
            if fl.get('filingTo', '9999') >= '2005-01-01' and fl.get('filingFrom', '0000') <= '2022-01-01':
                time.sleep(0.2)
                ex = ed.get(ed.BASE + fl['name'], agent)
                if isinstance(ex, dict):
                    rows += dc.extract(ex)
        cache[c] = rows
        meta[c] = {'name': js.get('name', ''), 'sic': str(js.get('sic', '')), 'sicDesc': js.get('sicDescription', ''),
                   'state': (js.get('addresses', {}).get('business') or {}).get('stateOrCountry', '')}
        if n % 100 == 0:
            print(f'  {n}/{len(ciks)}', flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'meta': meta, 'rows': cache}))
    failed = load_fdic()
    for e in ev:
        m = meta.get(e['cik'])
        e['found'] = m is not None
        if not m:
            continue
        e.update({'name': m['name'], 'sic': m['sic'], 'sicDesc': m['sicDesc'], 'state': m['state'], 'bank': is_bank(m['sic'], m['name'])})
        for w in dc.WINDOWS:
            e[f'c{w}'] = dc.classify(e['entry'], cache[e['cik']], w)
            e[f'f{w}'] = fdic_match(m['name'], m['state'], e['entry'], failed, w) if failed else []
        E = date.fromisoformat(e['entry'])
        e['forms59'] = sorted({f'{r[1]}{(" " + r[2]) if r[2] else ""}' for r in cache[e['cik']] if 0 <= (date.fromisoformat(r[0]) - E).days <= 59})
    report(ev, bool(failed))


def report(ev, have_fdic):
    ev = [e for e in ev if e.get('found')]
    c59 = [e for e in ev if e['c59'] == 'delisted_or_deregistered']
    print(f'\n=== (1) The {len(c59)} no-price events delisted or deregistered within 59 days (C35 class 3): name | SIC | state | entry | bank | forms in window | FDIC candidate within 365 days ===')
    for e in sorted(c59, key=lambda e: e['entry']):
        fd = '; '.join(f'{n} ({d})' for n, d in e['f365'][:2]) if have_fdic else 'n/a'
        print(f'  {e["sym"]:7s} {e["name"][:38]:38s} | {e["sic"]} {e["sicDesc"][:28]:28s} | {e["state"]:2s} | {e["entry"]} | {"BANK" if e["bank"] else "-   "} | {", ".join(e["forms59"])[:70]} | {fd}')
    print(f'  banks among them: {sum(e["bank"] for e in c59)} of {len(c59)}')
    if have_fdic:
        print(f'  with an FDIC candidate within 59 / 120 / 365 days: {sum(bool(e["f59"]) for e in c59)} / {sum(bool(e["f120"]) for e in c59)} / {sum(bool(e["f365"]) for e in c59)}')
    g = [e for e in ev if e['entry'][:4] in ('2008', '2009')]
    print(f'\n=== (2) No-price events entered in 2008-2009: n={len(g)} ===')
    bk = [e for e in g if e['bank']]
    print(f'  banks (by SIC or name): {len(bk)} ({len(bk) / len(g):.0%}); not banks {len(g) - len(bk)}')
    for lab, grp in (('banks', bk), ('non-banks', [e for e in g if not e['bank']])):
        c = Counter(e['c365'] for e in grp)
        print(f'  {lab}: within 365 days ' + ', '.join(f'{k} {c.get(k, 0)}' for k in dc.CLASSES) + f'; delisted/deregistered or bankrupt within 59 days: {sum(e["c59"] in dc.CLASSES[:1] + dc.CLASSES[2:3] for e in grp)}')
    if have_fdic:
        print(f'  FDIC candidate within 59 / 120 / 365 days: all {sum(bool(e["f59"]) for e in g)} / {sum(bool(e["f120"]) for e in g)} / {sum(bool(e["f365"]) for e in g)}; banks {sum(bool(e["f59"]) for e in bk)} / {sum(bool(e["f120"]) for e in bk)} / {sum(bool(e["f365"]) for e in bk)}')
        for e in sorted([e for e in g if e['f59']], key=lambda e: e['entry'])[:25]:
            print(f'    inside the hold: {e["sym"]} {e["name"][:34]} entry {e["entry"]} -> {e["f59"][0][0]} closed {e["f59"][0][1]}')
    print('\n=== (3) All no-price events by entry year: n | banks | FDIC candidate within 59 / 365 days ===')
    for y in sorted({e['entry'][:4] for e in ev}):
        gg = [e for e in ev if e['entry'][:4] == y]
        print(f'  {y}: {len(gg):4d} | {sum(e["bank"] for e in gg):3d} | ' + (f'{sum(bool(e["f59"]) for e in gg):3d} / {sum(bool(e["f365"]) for e in gg):3d}' if have_fdic else 'n/a'))
    if have_fdic:
        B = sum(bool(e['f59']) for e in ev)
        B2 = sum(bool(e['f59']) for e in ev if e['entry'] >= '2011-01-01')
        print(f'\n=== (4) Bound for the deep-fall rule, B = FDIC-candidate no-price events inside the 59-day hold: all years {B}, 2011-20 {B2} (same assumptions as Entry 74: each a -55% wipe-out, x = -9.4 ATR, -10.9 for 2011-20) ===')
        for label, n, mean, Bx, x in (('2006-2020', 269, 1.123, B, -9.4), ('2011-2020', 161, 0.600, B2, -10.9)):
            for s in (1.0, 0.5, 0.25):
                m = s * Bx
                print(f'  {label}: {s:.0%} of {Bx} would be extra deep-fall wipe-outs (m={m:.1f}): implied excess {(n * mean + m * x) / (n + m):+.3f}')
    print('\nSEC filings and a name match to the FDIC list only; candidates are flags, not proof of a wipe-out; no return joined.')


def selftest():
    assert toks('First Bancorp of Smithtown Inc') == {'first', 'smithtown'}
    failed = [{'name': 'Smithtown Bank', 'state': 'NY', 'closing': date(2009, 5, 1), 'tokens': toks('Smithtown Bank')}]
    assert fdic_match('Smithtown Bancorp Inc', 'NY', '2009-03-15', failed, 59)
    assert not fdic_match('Smithtown Bancorp Inc', 'NJ', '2009-03-15', failed, 59)
    assert not fdic_match('Smithtown Bancorp Inc', 'NY', '2009-03-15', failed, 30)
    assert is_bank('6022', 'Anything') and is_bank('6711', 'Foo Bancorp') and not is_bank('3674', 'Foo Bancorp')
    print('selftest ok: tokens, FDIC match, bank flag')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
        sys.exit(0)
    if sys.argv[1] == 'run':
        run(sys.argv[2], sys.argv[sys.argv.index('--out') + 1])
