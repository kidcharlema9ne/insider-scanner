# Insider buying scanner

Scans SEC Form 4 filings for open-market insider purchases, scores clusters of buying
(role, cluster size, first-buy, size vs holdings, liquidity), and alerts on Tier A/B signals.
Runs in the cloud on GitHub Actions: a scan every 30 minutes on weekdays while EDGAR is open (about 6 AM-10 PM Eastern),
an emailed report each night after EDGAR closes, and a 7-day report with the scorecard on Saturday morning.
Alerts only go out when a NEW filing creates or changes a signal; quiet scans send nothing.

Files: `insider_scanner.py` (code) - `test_insider_scanner.py` + `test_new_features.py` (offline tests, 55) -
`.github/workflows/scan.yml` (schedule) - `data/signals.jsonl` (every signal ever raised; lets the
database be rebuilt if GitHub's cache is lost).

Secrets (repo Settings > Secrets and variables > Actions): any of `NTFY_TOPIC`, `PUSHOVER_TOKEN` + `PUSHOVER_USER`,
`GMAIL_USER` + `GMAIL_APP_PASSWORD` (+ optional `ALERT_EMAIL`), `SEC_USER_AGENT`. Every channel that is set is used.
Each alert lists every buyer: name, position, $ amount, shares, price, buy dates, filing date, holdings afterwards.

Guards added Nov 5 2026 after the ASPE false positive: IPO/directed-share/underwriter footnotes are
excluded; stocks with < 60 trading days of price history are skipped; joint-reported identical lots
and sister funds count as one insider; per-issuer gap-fill covers quarters the SEC bulk files lack
(flag HISTORY_GAP if that fails); scans use the live feed plus the last 4 daily indexes.

Cluster window: buys by different insiders within 14 days of the latest buy count as one cluster (was 30);
buys within 2 days of each other still get a bonus.

Manual run: Actions tab > "Insider scanner" > Run workflow > pick scan / track / digest / digest-week / backfill / notify-test.
Not investment advice; signals are research leads.
