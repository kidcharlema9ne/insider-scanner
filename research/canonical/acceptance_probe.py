"""Probe (no returns): can GitHub Actions read SEC acceptance times for historical Form 4 filings?

Samples 24 accessions spread over 2006-2020 from the purchase-candidate database and fetches the first 6 KB of each original
submission text (Range request, SEC fair-access User-Agent from the SEC_USER_AGENT secret, <= 2 requests per second).
Prints HTTP status, the ACCEPTANCE-DATETIME header (Eastern local time, D-051 runbook) and the filing date from the database.
Stops on the first 403 or 429 (runbook: diagnose, do not hammer).
"""
import os, re, sqlite3, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ACC = re.compile(rb'<ACCEPTANCE-DATETIME>\s*(\d{14})')


def sample(db_path, n=24):
    db = sqlite3.connect(db_path)
    rows = db.execute("SELECT accession, filing_date, issuer_cik FROM purchase_candidates "
                      "WHERE filing_date BETWEEN '2006-01-01' AND '2020-12-31' GROUP BY accession ORDER BY accession").fetchall()
    step = max(1, len(rows) // n)
    return rows[::step][:n]


def fetch_header(cik, accession, agent):
    url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}.txt'
    req = urllib.request.Request(url, headers={'User-Agent': agent, 'Range': 'bytes=0-6143', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


def main():
    from cluster_counts_by_year import fetch_db
    agent = os.environ['SEC_USER_AGENT'].strip()
    with tempfile.TemporaryDirectory() as tmp:
        picks = sample(fetch_db(tmp))
    ok = 0
    for acc, filed, cik in picks:
        try:
            status, body = fetch_header(cik, acc, agent)
            m = ACC.search(body)
            ok += bool(m)
            print(f'{acc} filed {filed} cik {cik}: HTTP {status}, ACCEPTANCE-DATETIME {m.group(1).decode() if m else "NOT FOUND"}', flush=True)
        except urllib.error.HTTPError as e:
            print(f'{acc} filed {filed} cik {cik}: HTTP {e.code}', flush=True)
            if e.code in (403, 429):
                print('STOP: SEC refused; not retrying.')
                break
        except Exception as e:
            print(f'{acc}: {type(e).__name__} {e}', flush=True)
        time.sleep(0.5)
    print(f'{ok}/{len(picks)} headers with an acceptance time')


if __name__ == '__main__':
    main()
