# SEC-to-prices unattended execution contract

Owner instruction (2026-11-06): complete all ten SEC preparation steps sequentially without asking for intermediate approval. Stop only when historical daily prices must be acquired or a genuine external blocker requires user action. No paid purchases authorized. D-051 is binding: historical entry is the NEXT REGULAR TRADING SESSION OPEN after the actual SEC quarterly FILING_DATE; historical acceptance timestamps are NOT required. Before changing methodology read research_docs/DECISION_LOG.md and research_docs/MASTER_SPECIFICATION.md.

## Ordered stages and acceptance gates
1. Repository inventory: identify existing source, workflows, tests and missing components; record commit.
2. Archive completeness: all published 2006 Q1–2026 Q3 quarterly ZIPs present in R2 with verified SHA-256 and ZIP integrity; record missing quarters.
3. Field audit: verify real quarterly schema, filing dates, P/A codes, insider roles, holdings, footnotes and provenance; record missingness.
4. Gap classification: separate obtainable fields, optional enrichments and true blockers. Do not make acceptance timestamps a blocker.
5. Purchase classification: code P acquisition, 10b5-1/non-discretionary review flags, amendment and duplicate safeguards; test real and synthetic examples.
6. Candidate DB: idempotent SQLite import, original rows, filing-level disclosure grouping, historical identity and ownership flags; report counts and integrity.
7. Research engine: candidate and episode grouping, insider history and explanatory metadata; do not conflate episode success with individual entry.
8. Price interface: documented daily OHLCV schema, split handling, delistings, historical mapping, benchmarks and ATR(14) fixed from pre-entry bars. Reuse existing free-year sample.
9. Tests: unit/integration/regression checks on actual archived SEC quarters and sample prices; fail on missing required outputs; record missing coverage.
10. Documentation: write run status, manifests, test results, unresolved data-quality issues and exact price-acquisition handoff.

## Operating rules
- Work continuously through runnable stages; don't stop for conversational confirmations.
- A successful unit test is not proof of full historical completeness. Mark stages complete only after their stated acceptance gates.
- On recoverable errors, retry with bounded backoff and resume; on genuine blockers, write actionable diagnostic and stop rather than falsely reporting completion.
- Use GitHub Actions and Cloudflare R2 for unattended execution. Never commit credentials or bulk data to Git.
- Send user one meaningful notification when ready for historical daily prices, or one actionable blocker notification. No routine per-filing alerts.
- Historical paid data purchase and any methodology change require user authorization.

## Existing infrastructure (verified 2026-11-06)
- Historical archive workflow: .github/workflows/sec-bulk-historical-archive.yml (run 42288337419 in progress at inspection).
- Candidate DB builder: build_historical_sec_database.py; workflow .github/workflows/build-historical-sec-database.yml.
- Parser: sec_bulk_importer.py; outcomes: price_outcomes.py; scanner alerts: scanner_alerts.py.
- Tests: test_sec_bulk_importer.py, test_price_outcomes.py, test_form4_parser.py, test_scanner_alerts.py.
- Historical entry D-051 documented in research_docs/DECISION_LOG.md and research_docs/HISTORICAL_DATA_RUNBOOK.md.
- 251 free-year MarketParquet daily objects are documented in research_docs/FREE_YEAR_HANDOFF.md.

This contract is an execution checklist, not a claim that every stage has been implemented or passed.
