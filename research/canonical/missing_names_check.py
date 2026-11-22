"""Why do 944 refined events have no price series (Entry 38)?  Diagnostic only; no returns, nothing changes the primary set.

DECLARED BEFORE RUNNING:
 1. Pattern table of the raw ticker strings of no_price events (development years), to see formatting problems.
 2. For each no_price event try fixed, mechanical variants of the symbol: strip non-letters/digits (parentheses),
    '.'->'-', '-'->'.', drop a trailing share-class letter after '.'/'-', each with and without the -DELISTED suffix.
    A variant counts as RECOVERABLE if it appears in the archive on any of ~24 sampled sessions of the entry year.
 3. Counts by year: recoverable by variant type vs still missing.  Name lists of still-missing events (issuer cik,
    symbol, entry) for the 2008-2009 sample, so a few can be checked by hand against public sources.
Recovered symbols are NOT verified by the purchase-price identity check here; a recovered match is a lead only.
"""
import json, re, sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def variants(sym):
    """Mechanical alternatives to a cleaned symbol; returns [(kind, symbol)] without the original."""
    out = []
    s = re.sub(r'[^A-Z0-9.\-]', '', sym).strip('.-')
    if s != sym:
        out.append(('strip_punct', s))
    for a, b, kind in (('.', '-', 'dot_to_dash'), ('-', '.', 'dash_to_dot')):
        if a in s:
            out.append((kind, s.replace(a, b)))
    m = re.fullmatch(r'([A-Z0-9]+)[.\-][A-Z]', s)
    if m:
        out.append(('drop_class', m.group(1)))
    seen, res = {sym}, []
    for k, v in out:
        if v and v not in seen:
            seen.add(v)
            res.append((k, v))
    return res


def archive_symbols(s3, year, every=10):
    from archive_coverage_audit import list_dates, read_file
    keys = list_dates(s3, 'stock', year)
    keys = keys[::every] + keys[-1:]
    syms = set()
    with ThreadPoolExecutor(8) as pool:
        for _, _, t in pool.map(lambda k: read_file(s3, k), keys):
            syms.update(t['symbol'])
    return syms


def classify(events, syms_by_year, delisted):
    """events: no_price results with sym, entry, raw. -> list of (event, kind or None, found symbol)."""
    res = []
    for e in events:
        y = int(e['entry'][:4])
        have = syms_by_year.get(y, set()) | syms_by_year.get(y - 1, set())
        hit = None
        for kind, v in variants(e['sym']):
            for cand, tag in ((v, ''), (v + delisted, '+delisted')):
                if cand in have:
                    hit = (kind + tag, cand)
                    break
            if hit:
                break
        res.append((e, hit))
    return res


def run(events_json, year_dir):
    from archive_coverage_audit import DELISTED, normalize_ticker
    from r2_storage import client
    s3 = client()
    allev = json.loads(Path(events_json).read_text())
    raw = {(e['issuer_cik'], e['entry']): e['ticker'] for e in allev if e['set'] == 'refined'}
    nop = []
    for fn in sorted(Path(year_dir).glob('year_*.json')):
        d = json.loads(Path(fn).read_text())
        for r in d['results']:
            if r['set'] == 'refined' and r['status'] == 'no_price' and r['entry'] <= '2020-12-31':
                r['raw'] = raw.get((r['cik'], r['entry']), '')
                nop.append(r)
    print(f'no_price refined events, development years: {len(nop)}')
    pat = Counter(re.sub(r'[A-Z]', 'A', re.sub(r'[0-9]', '9', r['raw'].upper())) for r in nop)
    print('raw ticker shape (A=letter, 9=digit):', pat.most_common(12))
    years = sorted({int(r['entry'][:4]) for r in nop})
    syms_by_year = {y: archive_symbols(s3, y) for y in sorted(set(years) | {y - 1 for y in years})}
    print('sampled archive symbols per year:', {y: len(v) for y, v in syms_by_year.items()})
    res = classify(nop, syms_by_year, DELISTED)
    by = defaultdict(Counter)
    for e, hit in res:
        by[e['entry'][:4]][hit[0] if hit else 'still_missing'] += 1
    kinds = sorted({k for c in by.values() for k in c})
    print('\nyear | ' + ' | '.join(kinds))
    for y in sorted(by):
        print(y, '| ' + ' | '.join(str(by[y][k]) for k in kinds))
    tot = Counter(k for c in by.values() for k, v in c.items() for _ in range(v))
    print('total:', dict(tot))
    print('\nrecovered examples (raw -> found):', [(e['raw'], h[1]) for e, h in res if h][:20])
    miss = [e for e, h in res if not h and e['entry'][:4] in ('2008', '2009')]
    print(f'\nstill missing, 2008-2009: {len(miss)}; sample (symbol, issuer cik, entry):')
    for e in sorted(miss, key=lambda e: e['entry'])[::max(1, len(miss) // 40)]:
        print(f"  {e['sym']:8s} cik {e['cik']} {e['entry']}")


def selftest():
    assert ('strip_punct', 'PULB') in variants('(PULB)')
    assert ('dot_to_dash', 'BRK-B') in variants('BRK.B') and ('drop_class', 'BRK') in variants('BRK.B')
    assert variants('ABC') == []
    syms = {2008: {'PULB', 'XYZ-DELISTED'}, 2007: set()}
    ev = [{'sym': '(PULB)', 'entry': '2008-05-01'}, {'sym': '(XYZ)', 'entry': '2008-06-01'}, {'sym': 'QQQ', 'entry': '2008-06-01'}]
    r = classify(ev, syms, '-DELISTED')
    assert r[0][1] == ('strip_punct', 'PULB') and r[1][1] == ('strip_punct+delisted', 'XYZ-DELISTED') and r[2][1] is None
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        selftest()
    else:
        run(*sys.argv[1:3])
