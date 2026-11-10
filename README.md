# Insider buying scanner

Scans SEC Form 4 filings for open-market insider purchases, scores clusters of buying
(role, cluster size, first-buy, size vs holdings, liquidity), and alerts on Tier A/B signals.
Runs in the cloud on GitHub Actions: a scan every 30 minutes on weekdays while EDGAR is open (about 6 AM-10 PM Eastern),
an emailed report each night after EDGAR closes, and a 7-day report with the scorecard on Saturday morning.
Alerts only go out when a NEW filing creates or changes a signal; quiet scans send nothing.

Files: `insider_scanner.py` (code) - `test_insider_scanner.py` + `test_new_features.py` (offline tests, 62) -
`.github/workflows/scan.yml` (schedule) - `data/signals.jsonl` (every signal ever raised; lets the
database be rebuilt if GitHub's cache is lost).

## Alert rule (changed Nov 10 2026): the research rule

Scans now alert only on the rule from the insider-buying-research study (repo `insider-buying-research`; D-057, D-064, D-065, D-066 and Entries 36, 37, 41, 66, 67):
four or more different officers or directors (CEO, CFO, other officers, directors; not 10% owners or funds) bought in the open market within the 15 trading sessions before the entry open and their filings are already public; entry is the next regular open after the filing that makes four; the stock must trade at least $3M a day (15-session average); 10b5-1, automatic/dividend-reinvestment/ESPP, IPO/underwriter buys and plan-like same-date-same-price buying (D-064) are left out; after an event the issuer is ignored for 21 sessions (D-065).

Every qualifying cluster is pushed with a **score of 0 to 4**, one point each (a placeholder, not fitted): no CEO and no CFO among the buyers; Nasdaq (ONEQ) lagging SPY by 1.95 points or more over 63 sessions; stock down 15+ ATR over 12 months; stock down 50%+ from its 12-month closing high. A "?" means the data for that condition was unavailable. Score 3 or 4 is sent at Pushover high priority. The research log's sealed-year test (Entry 93) failed, so this is a lead being watched, not a proven edge.

Set `ALERT_RULE: legacy` in `.github/workflows/scan.yml` (or run with `--rule legacy`) to go back to the original tier A/B/C scorer. Tests: `python -m unittest test_insider_scanner test_new_features test_research_rule`.

Secrets (repo Settings > Secrets and variables > Actions): any of `NTFY_TOPIC`, `PUSHOVER_TOKEN` + `PUSHOVER_USER`,
`GMAIL_USER` + `GMAIL_APP_PASSWORD` (+ optional `ALERT_EMAIL`), `SEC_USER_AGENT`. Every channel that is set is used.
Each alert lists every buyer: name, position, $ bought, buy dates, filing date, estimated $ holdings afterwards and the % the buy added to prior holdings (no share counts), plus a score-breakdown table (factor, trigger, points, research basis).

Guards added Nov 5 2026 after the ASPE false positive: IPO/directed-share/underwriter footnotes are
excluded; stocks with < 60 trading days of price history are skipped; joint-reported identical lots
and sister funds count as one insider; per-issuer gap-fill covers quarters the SEC bulk files lack
(flag HISTORY_GAP if that fails); scans use the live feed plus the last 4 daily indexes.

Cluster window: buys by different insiders within 14 days of the latest buy count as one cluster (was 30);
buys within 2 days of each other still get a bonus.

Manual run: Actions tab > "Insider scanner" > Run workflow > pick scan / track / digest / digest-week / backfill / notify-test.
Not investment advice; signals are research leads.

## External scheduler reminder

The user also uses **Cron-job.org** (https://cron-job.org/) as a website/service for running or triggering the Insider Scanner. If asked later how the scanner is run or where to manage its external scheduled trigger, remember **Cron-job.org** and check that account's configured cron jobs. This note records the user's stated setup; the actual Cron-job.org job URL, schedule, and current enabled status have not been verified here. The repository also contains a native GitHub Actions schedule in `.github/workflows/scan.yml`; check both before changing schedules to avoid duplicate runs.
