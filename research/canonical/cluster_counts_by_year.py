"""Count four-plus-buyer clusters by year from SEC filings alone (no prices, no returns).

PROVISIONAL helper for choosing the sealed-period cut date (D-059). It applies the same
filters and the same 15-session / purchase-date / already-public logic as the recovered
selector (research/recovered_20261107/wider.py) but:
  * uses an NYSE trading calendar instead of the price-file calendar,
  * has no $3M liquidity floor and no price or ticker-to-security check,
  * counts every crossing from fewer than four to four-plus distinct buyers.
So raw counts are an upper bound on tradable trades. It never reads a return.

Usage: python cluster_counts_by_year.py [--db path.sqlite3] [--out reports/cluster_counts_by_year.json]
       python cluster_counts_by_year.py --selftest
"""
import argparse, hashlib, json, os, re, sqlite3, sys, tempfile
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

FLAGS = {'filing_affirms_10b5_1', 'possible_10b5_1', 'possible_non_discretionary', 'not_acquisition', 'missing_numeric_amount'}
TITLE = re.compile(r'(?:class [a-z0-9]+ )?common (?:stock|shares)(?:,?\s+(?:no par value|(?:par value )?\$\d+(?:\.\d+)?(?: par value)?(?: per share)?\.?))?', re.I)
ENTITY = re.compile(r'\b(?:LLC|LLP|LLLP|LP|LTD|Limited|Inc|Corp|Corporation|Holdings|Partners|Capital|Fund|Trust|Foundation|Management|Group|Company|PLC|Investments|Advisors|Associates)\b', re.I)
WINDOW = int(os.environ.get('CLUSTER_WINDOW', '15'))   # sessions of purchase dates before entry; 15 = rule in force (D-057); other values are exploratory variants (C38)
DB_KEY = 'sec/insider-transactions/derived/purchase_candidates.sqlite3'


def sessions():
    """NYSE sessions as ISO strings, 2005-06-01 .. 2026-12-31."""
    try:
        import pandas_market_calendars as mcal
        days = mcal.get_calendar('NYSE').valid_days('2005-06-01', '2026-12-31')
        return [d.strftime('%Y-%m-%d') for d in days]
    except ImportError:
        if os.environ.get('ALLOW_WEEKDAY_CALENDAR') != '1':
            raise
        import datetime as dt
        d, out = dt.date(2005, 6, 1), []
        while d <= dt.date(2026, 12, 31):
            if d.weekday() < 5:
                out.append(d.isoformat())
            d += dt.timedelta(days=1)
        return out


def usable(row):
    if FLAGS.intersection(row['review_flags']):
        return False
    if not TITLE.fullmatch(' '.join((row['security_title'] or '').split())):
        return False
    owners = row['owners']
    if len(owners) != 1 or not owners[0]['cik']:
        return False
    owner = owners[0]
    if not {'Director', 'Officer'}.intersection(owner['relationship'].split(',')):
        return False
    if ENTITY.search(owner['name']):
        return False
    return bool(row['transaction_dates']) and bool(row['ticker_at_filing'])


def find_events(rows, cal):
    by_security = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not usable(row):
            continue
        i = bisect_right(cal, row['filing_date'])
        if i >= len(cal):
            continue
        key = row['issuer_cik'], row['ticker_at_filing'], row['security_title'].upper()
        by_security[key][i].append(row)
    events = []
    for key, by_idx in by_security.items():
        if len({r['owners'][0]['cik'] for rs in by_idx.values() for r in rs}) < 4:
            continue
        seen = []
        for i in sorted(by_idx):
            entry, start = cal[i], cal[max(0, i - WINDOW)]
            ok = lambda r: any(start <= d < entry for d in r['transaction_dates'])
            seen = [r for r in seen if ok(r)]
            before = {r['owners'][0]['cik'] for r in seen}
            seen.extend(r for r in by_idx[i] if ok(r))
            after = {r['owners'][0]['cik'] for r in seen}
            if len(before) < 4 <= len(after):
                events.append({'issuer_cik': key[0], 'ticker': key[1], 'entry': entry, 'buyers': len(after)})
    return events


def summarize(events):
    by_year = Counter(e['entry'][:4] for e in events)
    total = len(events)
    ordered = sorted(e['entry'] for e in events)
    cut = {}
    for share in (0.5, 0.25, 1 / 3):
        k = int(total * (1 - share))
        cut[f'latest_{share:.3f}_starts_after_entry'] = ordered[k - 1] if 0 < k <= total else None
    return {'total_events': total, 'by_entry_year': dict(sorted(by_year.items())),
            'distinct_issuers': len({e['issuer_cik'] for e in events}), 'share_cut_dates': cut}


def load_rows(db_path, start='2005-12-01'):
    """Group transaction rows into one record per filing/issuer/security with the repo's own function."""
    from sec_bulk_importer import disclosure_opportunities
    db = sqlite3.connect(db_path)
    for row in disclosure_opportunities(db):
        if row['filing_date'] and row['filing_date'] >= start:
            yield row


def fetch_db(tmp):
    from r2_storage import BUCKET, client
    s3, path = client(), Path(tmp) / 'purchase_candidates.sqlite3'
    s3.download_file(BUCKET, DB_KEY, str(path))
    meta = s3.head_object(Bucket=BUCKET, Key=DB_KEY).get('Metadata', {}).get('verified-sha256')
    digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    if meta != digest:
        raise SystemExit('Database checksum mismatch')
    return str(path)


def selftest():
    os.environ['ALLOW_WEEKDAY_CALENDAR'] = '1'
    import datetime as dt
    cal = [d for d in sessions() if d >= '2020-01-01'][:60]
    def row(cik, tx, filed):
        return {'review_flags': [], 'security_title': 'Common Stock', 'owners': [{'cik': cik, 'name': 'Jane Doe', 'relationship': 'Director', 'title': ''}],
                'transaction_dates': [tx], 'ticker_at_filing': 'ABC', 'issuer_cik': '1', 'filing_date': filed}
    # four distinct buyers, last filing brings the count to four
    rows = [row('a', cal[30], cal[31]), row('b', cal[31], cal[32]), row('c', cal[32], cal[33]), row('d', cal[33], cal[34])]
    ev = find_events(rows, cal)
    assert len(ev) == 1 and ev[0]['entry'] == cal[35] and ev[0]['buyers'] == 4, ev
    # old purchase filed late does not count (purchase more than 15 sessions before entry)
    late = rows[:3] + [row('d', cal[10], cal[34])]
    assert find_events(late, cal) == []
    # repeat purchases by one person count once
    assert find_events([row('a', cal[30], cal[31]), row('a', cal[31], cal[32]), row('b', cal[32], cal[33]), row('c', cal[33], cal[34])], cal) == []
    # entity-like owner excluded
    ent = [dict(r) for r in rows]; ent[0] = dict(ent[0], owners=[{'cik': 'a', 'name': 'Acme Capital LLC', 'relationship': 'Director', 'title': ''}])
    assert find_events(ent, cal) == []
    print('selftest ok')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--db'); ap.add_argument('--out', default='reports/cluster_counts_by_year.json'); ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit()
    with tempfile.TemporaryDirectory() as tmp:
        db = a.db or fetch_db(tmp)
        events = find_events(load_rows(db), sessions())
    report = summarize(events)
    report['note'] = ('PROVISIONAL: filings only, NYSE calendar, no $3M floor, no price or security-mapping check, no returns. '
                      'Early-2006 counts may be low because the archive starts with 2006 Q1 filings.')
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
