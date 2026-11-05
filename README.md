# Insider buying scanner

Scans SEC Form 4 filings for open-market insider purchases, scores clusters of buying
(role, cluster size, first-buy, size vs holdings, liquidity), and alerts on Tier A/B signals.
Runs in the cloud on GitHub Actions (weekdays ~7:17 AM and ~6:41 PM Eastern; Saturday forward-return report).

Files: `insider_scanner.py` (code) - `test_insider_scanner.py` (offline tests, 35) -
`.github/workflows/scan.yml` (schedule) - `data/signals.jsonl` (every signal ever raised; lets the
database be rebuilt if GitHub's cache is lost).

Secrets (repo Settings > Secrets and variables > Actions): `NTFY_TOPIC` (required for phone alerts),
optional `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL`, `SEC_USER_AGENT`.

Guards added Nov 5 2026 after the ASPE false positive: IPO/directed-share/underwriter footnotes are
excluded; stocks with < 60 trading days of price history are skipped; joint-reported identical lots
and sister funds count as one insider; per-issuer gap-fill covers quarters the SEC bulk files lack
(flag HISTORY_GAP if that fails); scans use the live feed plus the last 4 daily indexes.

Manual run: Actions tab > "Insider scanner" > Run workflow > pick scan / track / backfill / notify-test.
Not investment advice; signals are research leads.
