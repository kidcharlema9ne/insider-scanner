**INSIDER BUYING RESEARCH  
MASTER RESEARCH SPECIFICATION**

Version 0.9 — Consolidated authoritative working specification  
Last updated: November 7, 2026  
Status: Approved methodology preserved; initial implementation scaffolding authorized; historical source selection pending.

# Document control and preservation

This version supersedes v0.6. The approved rules from v0.5 and subsequent discussion are integrated into the relevant methodological sections. The numbered decision log preserves the approval history. No implementation or paid-data purchase is authorized.

Important: this document distinguishes (A) decisions explicitly approved by the user, (B) recommendations or proposals not yet approved, (C) unresolved questions, and (D) implementation details not yet discussed. A proposal must never be treated as an approved rule.

No coding, bulk data downloads, or infrastructure construction is authorized merely by this specification. Implementation begins only after the user explicitly authorizes it.

# 1. Research objective

Develop a rigorous, historically comprehensive quantitative study of whether discretionary corporate insider purchases predict subsequent stock performance across groups of insiders (including directors, executives, and other eligible categories). The eventual application is a scanner evaluating newly disclosed purchases. Individual-insider career histories and records remain available for supplementary examination; identifying a handful of historically best-performing directors is NOT the primary research objective.

The central question is: after an insider’s discretionary purchase becomes publicly known, what investment opportunity is available to an outside investor, and how does that opportunity perform?

This is not primarily a bottom-fishing strategy, a momentum strategy, or a cluster-buying strategy. Purchases should be studied across different market conditions and stock trends, including falling stocks, recoveries, uptrends, and momentum.

The primary analytical observation is the individual investor opportunity created by a public disclosure. Buying episodes are an additional grouping mechanism; they must not replace or erase individual observations.

# 2. Research governance and methodology discipline

- Preserve all decisions and maintain a numbered decision log.

- Keep approved decisions separate from recommendations, unresolved questions, and implementation choices.

- Never silently change an approved methodology or convert a proposal into an approved rule.

- Discuss research design before implementation.

- Avoid unnecessary filters, composite scores, and rankings. Show the underlying measurements separately.

- Retain incomplete observations and identify missing information rather than inventing outcomes.

- Make calculations reproducible and document exact definitions.

- Avoid survivorship bias and look-ahead bias.

- Preserve historical securities, tickers, companies, insiders, transactions, corporate actions, and delisted or bankrupt entities.

- Report sample sizes and uncertainty alongside performance statistics.

- Account for overlapping observations and dependence when interpreting statistical significance.

# 3. Security universe

APPROVED

- Include US exchange-listed common stocks on NYSE, Nasdaq, and NYSE American (formerly AMEX).

- Include all market capitalizations, including micro-cap and small-cap companies.

- Do not impose a minimum share price or market-capitalization threshold.

- Include ADRs and multiple share classes.

- Include historical securities and companies that later disappeared through acquisition, bankruptcy, or delisting.

- Exclude OTC securities initially; OTC coverage may be considered later.

- Exclude ETFs, ETNs, mutual funds, closed-end funds, preferred shares, warrants, rights, bonds/debt, and other non-common securities.

- Map issuers to SEC CIKs, individual securities/share classes, and historical ticker symbols.

- Do not impose a liquidity exclusion; record liquidity measures such as average daily dollar volume.

# 4. Qualifying insider purchases

APPROVED IN PRINCIPLE

- Study CEOs, CFOs, other senior executives, independent directors, other directors, and 10% beneficial owners as separate groups, retaining overlapping role labels. Report an all-qualifying-insiders combined sample as a supplementary reference; do not replace separate group results. For nonduplicative comparisons, also retain a documented mutually exclusive role assignment.

- Focus on genuine discretionary open-market purchases, generally represented by Form 4 transaction code P.

- Exclude stock grants/awards, option exercises, gifts/inheritances, identifiable automatic purchases, and identifiable Rule 10b5-1 purchases.

- Do not assume every code P transaction is necessarily identical; preserve transaction details for review.

- No minimum number of purchases is required for an insider to be included.

- Direct and indirect ownership should be captured where identifiable, with attribution confidence recorded.

APPROVED CLARIFICATION — SECURITY AND INDIRECT OWNERSHIP

- Include discretionary purchases of common shares, direct or through trusts, partnerships, and entities when beneficial ownership is reliably attributable. Exclude derivatives and non-common securities. Flag ambiguous attribution for review rather than automatically including it.

- Exact attribution-confidence coding and unusual security-description parsing remain implementation details.

# 5. Dates, disclosure timing, and investor entry

APPROVED RULES

The system must distinguish: (1) insider transaction date, (2) insider transaction price, (3) public disclosure date and time, (4) hypothetical investor entry date, and (5) hypothetical investor entry price.

The investor entry price is the opening price of the first eligible trading session after the disclosure becomes publicly available, applying these rules:

- Disclosure before market open: same day's opening price.

- Disclosure during market hours: next trading session's opening price.

- Disclosure after market close: next trading session's opening price.

- Weekend or market holiday disclosure: next trading session's opening price.

- Use the actual public filing availability/acceptance timestamp, not the insider's transaction date.

- Each distinct public disclosure opportunity receives its own investor entry and performance path.

- Do not collapse later disclosures into the first disclosure's entry or assume an investor knew about future purchases.

APPROVED — LATE-DISCLOSURE ENTRY RULE

If an insider purchases on Monday but the Form 4 is not publicly disclosed until Friday, the outside investor enters at the opening price of the first eligible trading session after Friday's public disclosure (normally Monday, assuming it is a trading day). Do not use Monday's insider transaction price or any price from before the information became public.

Implementation details still to specify include the authoritative timestamp source, treatment of filing acceptance versus actual public dissemination in edge cases, and any unusual filing/timestamp anomalies.

# 6. Multiple transactions in one disclosure

APPROVED — SAME-DAY AND MULTI-DAY TRANSACTIONS WITHIN ONE DISCLOSURE

When an insider makes multiple purchases at different prices on the same day within the same Form 4/disclosure, aggregate them rather than treating each line as a separate analytical opportunity. Calculate the share-weighted average transaction price, aggregate shares and dollar value, and use one disclosure timestamp, one investor entry price, and one subsequent performance path. Do not count the same stock performance multiple times.

Example: 100 shares at \$50 and 200 shares at \$51 become 300 shares at a share-weighted average price of \$50.6667 (approximately \$50.67).

APPROVED — DIFFERENT PURCHASE DATES WITHIN ONE FORM 4. When the same insider purchases the same company/security on multiple dates and reports those purchases in one Form 4, preserve every underlying transaction date, transaction price, dollar amount, and other reported transaction detail. Calculate the aggregate share-weighted average insider transaction price and aggregate purchase dollar value for the filing. Treat the Form 4 as ONE public disclosure opportunity: one disclosure timestamp, one hypothetical investor entry price, and one subsequent stock-performance path. Do not create separate investor entries for the separate transaction dates within that same filing, and do not count the same subsequent stock performance multiple times.

Example: purchases of 1,000 shares at \$50 on Monday, 1,000 at \$52 on Wednesday, and 1,000 at \$55 on Friday, all reported in one Form 4, are retained individually in the transaction record. Their aggregate share-weighted average insider purchase price is \$52.33 and aggregate transaction value is \$157,000. The outside investor nevertheless receives one entry opportunity at the opening price of the first eligible trading session after the Form 4 becomes public.

The aggregate insider transaction price is descriptive of the insider’s purchases; it is not the outside investor’s entry price. The investor entry remains determined solely by public disclosure timing.

# 7. Buying episodes

APPROVED UPDATE — TEN-TRADING-SESSION GAP RULE (November 6, 2026; supersedes the five-session rule below)

Consecutive qualifying purchases by the same insider in the same company/security belong to one buying episode when the gap between purchase dates is no more than **10 trading sessions**. A gap greater than 10 trading sessions starts a new episode. This replaces the previously approved five-session threshold; the earlier wording is retained below as historical context, not an active rule.

APPROVED — FIVE-TRADING-SESSION GAP RULE (November 5, 2026; SUPERSEDED)

Consecutive qualifying purchases by the same insider in the same company/security belong to the same buying episode when the gap between purchases is no more than five trading sessions. A gap greater than five trading sessions starts a new episode.

Episodes are supplementary descriptive groupings. They must never replace the individual disclosure-level investor opportunities or their separate entry prices and performance outcomes.

USER'S EXPLICIT CLARIFICATION

Purchases on different dates may be batched into one episode, but the episode must not be treated as though the investor could have entered at the first purchase's price. The investor entry associated with each purchase/disclosure must reflect when that purchase was actually disclosed and the corresponding entry opportunity.

APPROVED — NO SYNTHETIC EPISODE-LEVEL INSIDER PURCHASE PRICE

Do not calculate an artificial average insider purchase price across different purchase dates in a buying episode. Preserve the actual transaction prices and dollar values for each purchase/disclosure. The same-day, same-disclosure share-weighted aggregation rule and the multi-day, same-Form-4 aggregation rule apply within their respective disclosures.

APPROVED — OPPORTUNITY-LEVEL AND EPISODE-LEVEL SUCCESS REPORTING

Report success at both levels. Each separate public disclosure/investor entry remains an individual opportunity observation. In addition, calculate episode-level success by counting each buying episode once. An episode is successful for a specified criterion and horizon if at least one individual opportunity within that episode meets that criterion. Report the number of individual opportunities and the number of distinct episodes so the two denominators are always visible.

Do not let episode-level reporting replace, erase, or merge the individual opportunity records or their separate entry prices and performance paths. Episode success is a supplementary grouping statistic, not a synthetic trade or a claim that all opportunities could have been entered at one price.

The exact operational success criteria for each performance measure, horizon, and benchmark comparison remain subject to the definitions in Section 15 and the unresolved questions. No episode-wide purchase price or representative entry price is approved.

- 
- 
- 

# 8. Performance measurement

APPROVED — THREE PERFORMANCE MEASURES REPORTED SEPARATELY; NO COMPOSITE SCORE

- Maximum appreciation: highest subsequent intraday High relative to the investor entry price.

- Maximum adverse movement: lowest subsequent intraday Low relative to the investor entry price. This is maximum adverse excursion (MAE), not conventional peak-to-trough drawdown; label it accurately.

- Ending return: horizon-end Close relative to the investor entry price.

Primary stock-performance calculations and reporting are in ATR units (“total ATRs”), using ATR(14) calculated from the 14 completed trading sessions preceding entry and fixed at the entry point. Do not recalculate ATR during the measurement horizon. Retain stock percentage returns as supplementary information, but do not make percentages the primary stock-performance measure. The entry session's High and Low are included in excursion calculations, but its range is not used to calculate entry ATR.

Example: investor entry is \$50 and the fixed ATR is \$2. A subsequent high of \$60 represents +5 ATR; a subsequent low of \$46 represents -2 ATR; an ending close of \$56 represents +3 ATR.

- Apply stock-split adjustments consistently.

- Include dividends in ending returns using total-return logic.

- Maximum appreciation and maximum adverse excursion are based on intraday price High/Low.

- Whenever a stock ATR return is displayed, place its named, point-in-time market benchmark alongside it for the same entry and exit dates. Display the benchmark move and excess in units of the stock’s fixed entry ATR under D-053. Preserve the underlying stock and benchmark percentage returns and their difference for calculation and audit.

# 9. Measurement horizons

APPROVED

The user selected calendar-day horizons of 15, 30, 60, and 90 days, plus six months. The shorter calendar periods are converted approximately to trading-session counts:

- 15 calendar days → 11 trading sessions.

- 30 calendar days → 21 trading sessions.

- 60 calendar days → 43 trading sessions.

- 90 calendar days → 64 trading sessions.

- Six months → the actual six-calendar-month anniversary; if the market is closed on that date, use the last trading session on or before the anniversary.

For the four shorter horizons, the entry session counts as the first session. High/low excursion calculations include the entry session. Ending return uses the close of the final session in the horizon.

# 10. Benchmarks and market context

APPROVED

- NYSE-listed stocks: S&P 500 / SPY.

- Nasdaq-listed stocks: Nasdaq Composite / ONEQ, except large Nasdaq companies that are S&P 500 constituents, which use the S&P 500.

- NYSE American stocks: Russell 2000 / IWM.

- QQQ may be used as a secondary comparison for large Nasdaq growth names, not as the default benchmark.

- **D-053, approved November 7, 2026.** Every stock ATR return in a report or project update must have the applicable index name or ETF symbol and the matched benchmark return immediately alongside it, at the same horizon. Display the benchmark move in stock ATR units by multiplying its same-window decimal return by the stock entry price and dividing by the stock’s fixed pre-entry ATR(14). Report paired excess as stock ATR return minus benchmark move in stock ATR units. Retain underlying percentage fields for audit. A benchmark’s own ATR, if shown separately, is a different measure.
- Use the mapping above at the entry date, including the S&P 500 exception for Nasdaq stocks, and keep the assignment fixed over the holding period. For subgroup means or medians, use the same paired observations and weighting for stock, benchmark and excess. Name any benchmark mix and show the matched and missing counts. If classification or prices are unavailable, display “benchmark unavailable” beside the stock return. Any all-cohort ETF reference must be explicitly labeled as a provisional comparison.

- Industry and market conditions (rising, falling, or flat) are descriptive variables, not filters. In addition to the primary approved market benchmark, report sector and industry benchmark returns separately when reliable point-in-time classifications and historical series are available. A matched-stock comparison against similar stocks without contemporaneous qualifying insider purchases is an optional research extension, not a prerequisite for the initial study.

APPROVED — POINT-IN-TIME BENCHMARKS; INDUSTRY HISTORY OPEN

- Select the benchmark based on exchange and verified index membership on investor entry date; keep it fixed for the horizon. Flag uncertain historical membership; never backfill present-day membership.

- Historical industry-classification sources and mapping details remain open.

- Exact rules for benchmark selection when listings, index membership, or company classifications change.

# 11. Corporate actions, delistings, and terminal outcomes

APPROVED PRINCIPLES

- Adjust consistently for stock splits.

- Include dividends in ending total returns.

- For acquisitions, use actual cash and/or stock consideration.

- For bankruptcies, use actual recovery or loss where available.

- For delistings, use final realizable value where available.

- If an outcome cannot be established reliably, mark it incomplete; do not invent a terminal price or return.

IMPLEMENTATION DETAILS NOT YET FINALIZED

The approved principles are to use actual cash consideration for cash acquisitions; actual stock consideration and resulting security value for stock acquisitions; both components for mixed consideration; actual bankruptcy distributions/recoveries where available; and final realizable value for delistings where available. If the terminal outcome cannot be established reliably, mark the observation incomplete rather than inventing a value. Detailed mechanics remain to be specified, including valuation dates for stock consideration, fractional shares, contingent consideration, dividend reinvestment, and bankruptcy distribution timing.

# 12. Insider identity and career history

APPROVED

- Track individuals across companies and across their full available careers.

- Make it possible to report lifetime, per-company, and per-position performance.

- Record the insider's role at the time of each purchase.

- Record new appointments and recent role changes where identifiable.

- Disambiguate individuals carefully; do not merge people merely because they share a name.

# 13. Purchase size and ownership significance

APPROVED

Report the insider’s purchase dollar value and its significance relative to the estimated dollar value of the insider’s existing company-stock ownership immediately before the purchase. Emphasize dollar amounts rather than share counts. Share counts may be retained internally where necessary for calculations.

Calculate purchase significance as: purchase dollar value ÷ estimated market value of the insider’s pre-purchase company-stock ownership × 100. Also report the dollar value of the existing ownership and, where reliably determinable, the post-purchase ownership value. This measure describes the purchase relative to the insider’s existing investment in that company; it is not a percentage of personal net worth.

Example: a \$100,000 purchase divided by \$500,000 of existing company-stock ownership equals 20%. Label this as 'purchase relative to existing company ownership.' It is not a percentage of personal net worth. SEC filings cannot establish an insider's total personal net worth.

APPROVED — OWNERSHIP DENOMINATOR

- Primary purchase-significance denominator is market value of beneficially owned common shares immediately before purchase, including reliably attributable direct and indirect shares. Exclude options and unvested awards from the primary denominator; disclose separately if available. Reconstruct ownership from contemporaneous SEC disclosures, preferring same-filing holdings and transaction details, then prior Form 4/5 and other reliable contemporaneous disclosures. Preserve source and uncertainty.

- Report unavailable when reliable pre-purchase holdings cannot be established; identify verified zero ownership as a new position, not an infinite percentage. Joint/indirect attribution and stale ownership require explicit flags.

- How to report missing, stale, or incomplete ownership information.

# 14. Filing amendments

APPROVED PRINCIPLES

- Use the latest valid amended information for corrected transaction facts.

- Preserve the original filing and amendment history.

- Avoid double-counting the original and amended transaction.

- Preserve actual public disclosure timing and avoid look-ahead bias.

Implementation edge cases, including material amendments made after an initial investor entry, require documented rules. A later amendment must not retroactively give the hypothetical investor information that was not publicly available at the original entry time.

# 15. Statistical reporting

APPROVED REPORTING PRINCIPLES

- For each insider, horizon, and performance measure, report arithmetic average, median, win/success rate, observation count, distribution, and confidence intervals where appropriate. Stock performance and stock-based success calculations use ATR units as the primary measurement; percentage returns remain supplementary. Present the applicable benchmark and paired excess next to stock ATR returns in stock ATR units under D-053. Retain their percentage equivalents for audit.

- Also report the number of distinct insiders, companies, and buying episodes represented.

- Do not impose a minimum purchase count for inclusion.

- Do not create a composite score or hide the underlying results behind an overall ranking.

- Account for dependence caused by overlapping horizons, repeated purchases, and common market/company shocks when interpreting significance.

APPROVED — DEPENDENCE-AWARE INFERENCE AND MULTIPLE TESTING

- Use cluster-aware bootstrap confidence intervals, retaining individual opportunities in raw performance calculations and resampling buying episodes for insider-level uncertainty; account additionally for company and calendar-time dependence in broader group analyses. Flag estimates unreliable where too few independent units exist. Report sample sizes and episodes.

- When many hypotheses are tested, report false-discovery-rate adjustments in addition to raw effects and confidence intervals. The primary inferential objective is group-level predictive value of insider buying, not selection of a few best historical directors. Predefine tested groups and comparisons before examining outcomes when feasible.

- Report separate maximum-appreciation and ending-return success rates, each accompanied by maximum adverse excursion. Working thresholds are \>0 ATR for maximum appreciation and \>0 ATR for ending return; zero outcomes and optional additional appreciation thresholds remain open. Benchmark outperformance is based on percentage excess return, not mixing ATR and percentage units.

- Exact distribution summaries and any subgroup minimum sample-size display conventions.

# 16. Historical coverage and data integrity

APPROVED PRINCIPLES

- Go back as far historically as reliable data permit.

- Preserve historical securities, tickers, issuers, insiders, roles, transactions, amendments, disclosure timestamps, corporate actions, delisted companies, bankruptcies, and incomplete records.

- Do not assume a present-day security universe or a data provider's coverage is historically complete.

- Verify actual historical start dates and coverage for SEC filings, prices, timestamps, corporate actions, and delisting outcomes before claiming a period is covered.

- Retain missing or incomplete observations with explicit data-quality flags.

## Approved disclosure timing

Use SEC EDGAR acceptance time as the disclosure-time proxy; flag demonstrated publication discrepancies. Apply already approved first-eligible-opening entry rules; do not simulate intraday entries.

## Approved dividends and total returns

Include ordinary cash dividends without reinvestment in ending return when reliable historical dividend data are obtainable. Maximum appreciation and maximum adverse excursion use split-adjusted price High/Low only. Calculate fixed pre-entry ATR(14) consistently with split-adjusted prices, without treating dividend adjustments as actual intraday prices. If free dividend data are too difficult or costly, user prefers dropping dividend inclusion; this is conditional and requires explicit disclosure and confirmation before changing the methodology.

## Approved corporate actions and amendments

Cash acquisitions: actual cash consideration, then zero-interest cash through remaining horizon. Stock acquisitions: follow replacement shares; mixed: track both. Preserve actual bankruptcy/delisting outcomes or flag incomplete. Preserve original and amended Form 4 filings; use corrections for historical facts but preserve what was publicly knowable at original entry and prevent double-counting.

## Approved missing-data reporting

Retain incomplete observations. Include each opportunity in every horizon and metric for which sufficient reliable data exist, and exclude it only from calculations that cannot be established. Report eligible and missing counts by metric and horizon; do not invent returns or assume missing outcomes are neutral.

## Historical data feasibility — approved process, sourcing still open

Assess free SEC, price, corporate-action, delisting, membership, and ownership sources in a small feasibility study before building infrastructure. Seek longest reliable coverage including disappeared companies. If free sources are inadequate, present paid options and costs for approval; no paid purchase or coding authorized.

# 17. Approved contextual analyses and validation

## Insider-role groups — approved

Report CEOs, CFOs, other senior executives, independent directors, other directors, and 10% beneficial owners separately. Preserve overlapping roles, including a distinct analysis of all purchases by 10% owners even if those insiders are executives or directors. Retain a mutually exclusive grouping for nonduplicative category comparisons and an overall qualifying-purchase sample as a supplementary reference. Exact precedence for mutually exclusive classification remains an implementation decision; no group is assumed to outperform before testing.

## Sector/industry supplementary comparisons — approved

Keep the approved exchange/index benchmark as primary. Add point-in-time sector and industry returns as separately displayed supplementary comparisons, where reliable historical classification and return series exist. Similar-stock non-purchase matched controls are optional future research, not a mandatory initial component. Do not combine benchmark returns into a composite.

## Pre-disclosure stock and market conditions — approved

At each investor entry, record separately: prior stock returns over 5, 21, 63, 126, and 252 completed trading sessions (percent and clearly defined ATR-normalized units); distance from trailing 52-week high and low and location within the 52-week range; ATR(14) dollars and as percent of price, with realized volatility when useful; average daily dollar trading volume, market capitalization, and stock price; benchmark and industry returns over preceding 21, 63, and 126 completed sessions, market position relative to 200-day moving average, and stock-versus-industry prior relative performance. These are explanatory measurements, not inclusion filters. All pre-entry indicators must use only information available by the hypothetical entry open, normally ending at the prior completed session. Exact windows, split handling, and missing-history flags are to be documented before execution.

## Earnings timing — approved

Record both the insider’s actual transaction date relative to earnings announcements and the public disclosure/investor entry date relative to earnings announcements. Distinguish purchases before earnings from purchases after earnings; use signed trading-session distances and preserve exact announcement timestamp when available (before open, during session, after close). Earnings announced after a purchase must not be used as a contemporaneously known explanatory variable in predictive models, though subsequent event distance may be used for retrospective descriptive analysis. Do not exclude earnings-adjacent purchases. Historical earnings data sourcing remains open.

## Out-of-sample validation — approved

Use a chronological development period followed by a later untouched validation period where sufficient reliable history exists. Any candidate predictive relationships, filters, or scanner rules must be selected using only development-period information and evaluated on subsequent data without retuning to the validation results. Exact split dates, minimum historical coverage, embargo/purging for overlapping forward-return horizons, and reporting protocol are to be specified before analysis; do not assume illustrative dates are approved.

# 17A. Conditional fallback if reliable OHLCV data cannot be obtained

APPROVED CONDITIONAL PREFERENCE — Keep full daily OHLCV and observed ATR(14), eligible opening-price entry, intraday maximum appreciation, and intraday maximum adverse excursion as the primary methodology. Investigate TradeStation historical daily bars, including its discontinued-symbol lookup, before deciding that OHLCV is unavailable. No switch has been authorized yet.

If sufficiently reliable OHLCV is unavailable for part of the historical sample, a separately labeled close-only fallback may be considered instead of abandoning those observations. Such a fallback cannot recreate historical opening entry prices or intraday extrema. Its entry timing and price convention must be expressly approved before use; never substitute a pre-disclosure close as an investable post-disclosure entry.

PROPOSED, NOT APPROVED — Compute a close-based daily volatility estimate from the preceding 14 completed sessions, then optionally express it in estimated-ATR-equivalent units using an empirically tested multiplier. The user raised 1.6 as a possible multiplier. Do not treat 1.6 as an approved universal constant or claim this is observed ATR.

Technical clarification: under an idealized continuous Gaussian price process, expected high-low range is approximately 1.596 times the standard deviation of close-to-close price changes; it is approximately 2.0 times the mean absolute close-to-close change. Actual ATR additionally includes overnight gaps. Therefore define the estimator (standard deviation versus mean absolute change), corporate-action adjustments, lookback, and calibration sample before selecting a conversion factor.

Close-only outputs must be distinctly labeled: ending close-to-close returns, maximum subsequent closing price, minimum subsequent closing price, and estimated rather than observed volatility. Report Tier 1 OHLCV and Tier 2 close-only results separately, with overlap validation if possible. Do not silently pool their extrema, entry prices, or ATR values as identical.

FEASIBILITY STATUS — User has TradeStation desktop and will test Symbol Lookup with “Include symbols no longer trading” and a historical delisted security. This is a test of availability, not proof of universe-wide coverage. A \$79 historical OHLCV archive remains a possible paid fallback; no purchase has been authorized.

# 18. Numbered decision log — preserved history

| ID    | Topic                                   | Status                            | Decision                                                                                                                                                                                                                   |
|-------|-----------------------------------------|-----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| D-001 | Research objective and primary unit     | Approved                          | Individual publicly disclosed investor opportunities are primary; episodes are supplementary.                                                                                                                              |
| D-002 | US security universe                    | Approved                          | NYSE, Nasdaq, NYSE American common stocks; all market caps; OTC excluded initially; specified non-common securities excluded.                                                                                              |
| D-003 | Qualifying purchases                    | Approved in principle             | Discretionary open-market insider purchases; exclude grants, exercises, gifts, identifiable automatic/10b5-1 purchases.                                                                                                    |
| D-004 | Investor entry timing                   | Approved                          | Entry at opening price of first eligible session after public disclosure. Late-disclosure case approved: Monday purchase disclosed Friday → entry at next eligible session's open.                                         |
| D-005 | Performance measures                    | Approved                          | Maximum appreciation, maximum adverse excursion, and ending return shown separately; no composite.                                                                                                                         |
| D-006 | ATR methodology                         | Approved                          | ATR(14) from 14 completed sessions before entry; fixed at entry.                                                                                                                                                           |
| D-007 | Horizons                                | Approved                          | 15/30/60/90 calendar days converted to 11/21/43/64 sessions, plus six calendar months.                                                                                                                                     |
| D-008 | Historical depth                        | Approved principle                | Go back as far as reliable data permit; preserve delisted and incomplete observations.                                                                                                                                     |
| D-009 | Benchmarks                              | Approved core mapping             | NYSE S&P 500/SPY; Nasdaq Composite/ONEQ except S&P 500 constituents; NYSE American Russell 2000/IWM; QQQ secondary.                                                                                                        |
| D-010 | Insider career history                  | Approved                          | Track individuals across companies, roles, and careers.                                                                                                                                                                    |
| D-011 | Purchase size/ownership significance    | Approved                          | Dollar value and purchase relative to existing company-stock ownership; not personal net worth.                                                                                                                            |
| D-012 | Filing amendments                       | Approved principles               | Use corrected facts, preserve history, avoid double-counting and look-ahead.                                                                                                                                               |
| D-013 | Five-session episode gap                | Approved 2026-11-05               | Same insider/company/security purchases remain in an episode if gap is no more than five trading sessions; greater gap starts a new episode.                                                                               |
| D-014 | Same-day multiple transactions          | Approved 2026-11-05               | Aggregate same-day same-disclosure purchases using share-weighted average transaction price; one analytical opportunity/path.                                                                                              |
| D-015 | Multi-day transactions in one Form 4    | Approved 2026-11-06               | Preserve each dated transaction; aggregate the filing’s insider transaction price using share weights and aggregate dollars; one public disclosure opportunity, investor entry, and performance path.                      |
| D-016 | Episode-level success reporting         | Approved 2026-11-06               | Report opportunity-level and episode-level success. Count each episode once; an episode meets a criterion if at least one constituent opportunity meets it.                                                                |
| D-017 | Episode-level insider purchase price    | Approved 2026-11-06               | Do not calculate a synthetic average insider purchase price across different purchase dates in an episode; preserve actual transaction prices and dollar values.                                                           |
| D-018 | ATR-based stock success measurement     | Approved principle 2026-11-06     | Use ATR units as the primary stock-performance and stock-based success measure; retain stock percentages as supplementary. Benchmark returns and excess returns remain percentages. Exact success definitions remain open. |
| D-019 | Corporate actions and terminal outcomes | Approved 2026-11-06               | Use actual cash/stock/mixed acquisition consideration, bankruptcy recoveries, and final realizable delisting values where available; unknown outcomes remain incomplete.                                                   |
| D-020 | Purchase significance                   | Approved core approach 2026-11-06 | Emphasize purchase dollar value and its relation to estimated pre-purchase company-stock ownership value; share count is not a headline measure. Ownership denominator details remain open.                                |
| D-021 | Success measures                        | Approved                          | Separate maximum appreciation and ending return success rates; MAE alongside each; working \>0 ATR thresholds, zero convention open.                                                                                       |
| D-022 | Ownership denominator                   | Approved                          | Actual attributable beneficial common shares before purchase; options/unvested awards excluded; missing flagged.                                                                                                           |
| D-023 | Dependence                              | Approved                          | Preserve opportunities; cluster-aware bootstrap with episode, company, and calendar-time dependence as appropriate.                                                                                                        |
| D-024 | Disclosure timestamp                    | Approved                          | EDGAR acceptance proxy; first eligible opening; documented exceptions.                                                                                                                                                     |
| D-025 | Benchmark membership                    | Approved                          | Point-in-time membership and exchange; fixed over horizon; uncertainty flagged.                                                                                                                                            |
| D-026 | Indirect purchases                      | Approved                          | Include attributable common-share purchases; exclude derivatives; flag ambiguous cases.                                                                                                                                    |
| D-027 | Acquisition proceeds                    | Approved                          | Cash held at zero interest; follow replacement shares; mixed consideration tracked.                                                                                                                                        |
| D-028 | Amendments                              | Approved                          | Preserve history, correct facts, prevent double counting, preserve point-in-time knowledge.                                                                                                                                |
| D-029 | Dividend treatment                      | Approved conditional              | Cash dividends without reinvestment for ending returns if reliable; price-only excursions; user prefers omission if free-data burden prohibitive, subject to explicit confirmation.                                        |
| D-030 | Ownership reconstruction                | Approved                          | Use contemporaneous filing evidence; mark unreliable ratios missing; verified zero means new position.                                                                                                                     |
| D-031 | Bootstrap method                        | Approved                          | Cluster-aware episode bootstrap with broader company/time adjustments; flag insufficient independent samples.                                                                                                              |
| D-032 | Primary research focus                  | Approved clarification            | Assess predictive performance of insider purchases across groups; scanner eventual goal; individual career analysis supplementary.                                                                                         |
| D-033 | Multiple comparisons                    | Approved                          | False-discovery-rate adjustment for multiple tested hypotheses; preserve raw statistics.                                                                                                                                   |
| D-034 | Data feasibility                        | Approved process                  | Small free-source feasibility assessment before implementation; consider paid data if needed; purchase requires approval.                                                                                                  |
| D-035 | Incomplete observations                 | Approved                          | Metric- and horizon-specific eligibility; report missing counts; never invent outcomes.                                                                                                                                    |
| D-036 | Insider role groups                     | Approved                          | Separate CEO, CFO, other executives, independent/other directors, and 10% owners; preserve overlapping roles; combined reference sample.                                                                                   |
| D-037 | Supplementary benchmarks                | Approved                          | Primary market benchmark unchanged; add sector and industry comparisons; matched-stock controls optional.                                                                                                                  |
| D-038 | Entry-time conditions                   | Approved                          | Record specified historical momentum, range position, volatility, liquidity, size, and market/industry context; no filters.                                                                                                |
| D-039 | Earnings timing                         | Approved                          | Study actual insider purchase dates before/after earnings; preserve separate disclosure and investor-entry timing; no earnings exclusion.                                                                                  |
| D-040 | Purchase / market cap ratio             | Declined                          | Do not add purchase value divided by company market capitalization as a required measure.                                                                                                                                  |
| D-041 | Out-of-sample validation                | Approved                          | Chronological development and later untouched validation, subject to historical data feasibility; no tuning on validation results.                                                                                         |
| D-042 | Close-only contingency                  | Approved conditional preference   | Preserve OHLCV as primary; if unavailable, investigate separately labeled close-only analysis, with entry convention and estimator still requiring approval.                                                               |
| D-043 | ATR proxy 1.6 multiplier                | Proposed / unresolved             | User suggested 1.6; conversion must distinguish close-to-close standard deviation from mean absolute change, and be empirically calibrated before adoption.                                                                |
| D-044 | TradeStation feasibility                | Planned test                      | User will check discontinued-symbol lookup in TradeStation desktop; no historical coverage conclusion yet.                                                                                                                 |

# 19. Open issues — not approved as methodology changes

- Actual historical source coverage, cost, and feasibility, including delisted securities, SEC filing timestamps, dividends, and point-in-time index membership; paid data selection remains open.

- Operational zero-return convention and any additional appreciation success thresholds; do not infer approval from working \>0 ATR definitions.

- Exact implementation of clustered bootstrap for company/calendar-time dependence, effective sample size diagnostics, and group-level testing design; principle approved.

- Unusual corporate-action mechanics (contingent/fractional consideration, bankruptcy distribution timing, delisting terminal values), timestamp anomalies, and amended filings with newly revealed transactions.

- Historical industry classification and difficult indirect/joint ownership attribution; explicit missing-data flags required.

- Data infrastructure, programming, bulk downloads, and paid purchases are not authorized.

Historical earnings announcement timestamps and dates, historical sector/industry benchmarks, role-classification precedence for mutually exclusive views, and sufficient history for proposed lookbacks.

Exact out-of-sample date split, overlap-aware separation of training/validation observations, and validation protocol after feasibility results.

# 20. Version history and checkpoint

- v0.2: Episode gap and same-day aggregation decisions.

- v0.4: Multi-day Form 4, episode reporting, ATR reporting, terminal outcomes, and purchase significance.

- v0.5: Success measures, ownership denominator, statistical dependence, timestamps, benchmark history, indirect purchases, acquisitions, amendments; historical sourcing open.

v0.8 (November 6, 2026): Recorded conditional close-only fallback, clarified the proposed 1.6 ATR-proxy relationship and its limitations, and documented pending TradeStation discontinued-symbol test. No changes to primary methodology.

- v0.7 (November 6, 2026): Approved separate insider-role analyses, sector/industry supplementary benchmarks, contextual measures, purchase-versus-earnings timing, and chronological out-of-sample testing; explicitly declined purchase/market-cap ratio. No implementation authorized.

- v0.6 (November 6, 2026): Consolidated v0.5 decisions into core sections; approved dividend methodology with conditional free-data preference, ownership reconstruction, clustered bootstrap, group-level research objective, multiple testing, feasibility assessment, and missing-observation reporting.

CHECKPOINT: Decisions and proposed implementation contingencies recorded through D-044. Original OHLCV/ATR methodology remains primary and unchanged. Close-only fallback is conditional and not activated; 1.6 multiplier and entry convention are unresolved. Await TradeStation desktop delisted-symbol test before deciding on data purchase or implementation.

# 21. November 6, 2026 continuation — data-source research and implementation authorization

## Approved / explicitly authorized

- D-045: User authorizes beginning initial implementation without historical price data, using a provider-agnostic architecture. Authorization covers project structure, schemas, SEC Form 4 ingestion design, historical security identification, calculation specifications and small local tests. It does not authorize paid purchases, mass historical downloads, or large cloud deployments.

- D-046: Preserve approved investor-entry-at-eligible-open and full daily OHLCV/observed ATR as primary methodology. Do not activate close-only fallback merely for convenience.

- D-047: User prefers a low-maintenance automated system, minimal manual downloads and inexpensive infrastructure; GitHub for code, separate object storage for historical data are proposed architecture, not yet selected services.

## Research findings — not approvals or verified guarantees

- WIKI Prices: approximately 3,199 symbols, OHLCV through March 2018, some delisted; incomplete historical universe and no 2018–2026 coverage. Kaggle Huge Stock Market Dataset: approximately 8,539 stock/ETF files through November 2017; systematic delisted inclusion and point-in-time universe not established. Neither recommended as sole final universe without an audit.

- MarketParquet advertises a \$79 one-time full historical daily OHLCV archive beginning 2000, with delisted stocks, and a free recent-year sample. Public documentation describes one Parquet file per trading date, with date/timestamp, symbol, asset_type, open/high/low/close/volume; split adjusted, dividends not included. Historical 2008 LEH and Washington Mutual WM original common shares and historical issuer mapping have NOT been independently verified.

- MarketParquet documents bulk date-range manifest API, including daily stock files; optional \$15/month updates. Vendor advertises thousands of delisted stocks, but the claim is not an independent completeness audit. Historical ticker reuse (Washington Mutual WM versus current Waste Management WM) illustrates need for point-in-time security mapping, not date-only matching.

- TradeStation desktop discontinued-symbol lookup: Lehman LEH not found in prior user search; WAMUQ Washington Mutual Incorporated appears but historical bars were still loading; availability of pre-failure NYSE daily history unconfirmed. TradeStation not presently selected as main historical source.

- No published MarketParquet telephone opening hours or verified support phone number found in publicly checked website/documentation. Do not claim a specific opening time.

## Unresolved verification and implementation choices

- Before purchase: confirm pre-September-2008 daily OHLCV for original Lehman Brothers LEH and Washington Mutual WM, and issuer/ticker identity mapping; obtain response through vendor contact if possible. No purchase authorized.

- Choose storage host, GitHub integration and credentials strategy after user approval; do not commit secrets or paid licensed raw data to a public repository.

- Design importer for daily date-partitioned Parquet with date/timestamp schema normalization and independent security master. Plan reconciliation of CIK, filing issuer, ticker, security class, exchange, listing dates and corporate actions; flag ambiguous matches.

- Design reproducible SEC Form 4 ingestion with acceptance timestamp and individual purchase/disclosure opportunity, retaining same-day weighted aggregations and ten-session episodes per the November 6 approved update.

- Design modular OHLCV/ATR and benchmark calculations; postpone full historical execution until data validated. Any code or tests must not silently redefine approved metrics.

- Historical source selection, archive completeness, dividends/corporate actions, earnings data, point-in-time benchmarks and sample coverage remain unresolved.

## Version history addition

v0.9 (November 6, 2026): Preserves v0.8 in full; records data-provider investigation, conditional \$79 vendor decision, historical identity-mapping risk, and explicit authorization for initial implementation scaffolding without bulk data. No substantive research metric changed.

# 22. November 6, 2026 — episode and signal-campaign update

**APPROVED — TWO DISTINCT GROUPING LEVELS**

- **Buying episode:** same insider and same security; consecutive qualifying purchase dates separated by **10 or fewer trading sessions** belong to the same episode. More than 10 trading sessions starts a new episode. Supersedes the prior five-session gap.
- **Signal campaign:** a separate, broader grouping of repeated purchases by the same insider in the same security over an **90-calendar-day separation window** (confirmed November 6, 2026). Group consecutive qualifying purchases when no gap exceeds 90 calendar days, and start a new campaign after a longer gap. The threshold is definitively **90 calendar days, not trading sessions**.
- **Keep these separate:** disclosure-level investor opportunities, 10-session buying episodes, and longer signal campaigns are distinct units. Preserve every filing's public-disclosure timestamp, eligible investor entry, and full outcome path. Do not create synthetic entry prices or merge disclosure-level observations.
- **Profitability and statistical interpretation:** report campaign-level profitability/success separately from episode-level and disclosure-level results, including all three denominators. Do not treat repeated profitable purchases in a sustained bull market as independent evidence of insider skill. Campaign success metric/aggregation (e.g., any constituent opportunity profitable versus first opportunity profitable, benchmark-adjusted return, or another measure) remains to be specified; do not silently substitute the existing episode 'any opportunity succeeds' definition.
- **Governance:** this is an explicit user-approved change to the episode window and addition of a three-month campaign concept; the campaign success criterion remains an implementation question. Preserve existing horizon metrics (11/21/43/64 trading sessions and six-calendar-month horizon) unchanged.

## November 6, 2026 — historical filing-date entry rule (approved supersession)

For the historical Form 4/4-A insider-purchase study, use the **actual SEC filing date** from the SEC quarterly Insider Transactions bulk dataset. Define the first investor entry as the **regular-session open on the next trading day strictly after the filing date**, regardless of time of day. This explicitly supersedes the earlier acceptance-timestamp-sensitive same-day premarket entry rule for this historical study. Do not assume the filing occurred two days after the insider transaction. Exact SEC acceptance timestamps and individual filing downloads are **not required for entry timing**. Label the rule as a conservative next-session approximation; the SEC quarterly ZIP publication date is not the individual filing date. Keep transaction eligibility, all outcome horizons, ATR metrics, episode/campaign grouping, and other approved methods unchanged. Verify bulk dataset coverage and relevant fields before a full 20-year ingestion.

## November 6, 2026 — additional filing-date versus next-open outcome comparison

Preserve the approved **next-trading-session open after actual filing date** as the primary tradable investor entry. Additionally compute a **filing-date closing-price reference** and returns measured from that close for the same approved outcome horizons, alongside next-open-based returns, plus the filing-close-to-next-open gap (percent and where applicable ATR units). Keep the two series distinctly labeled and compare their results without silently conflating them. Filing-date close may precede publication for after-hours filings, so this reference is **descriptive/non-executable**, not a claimed investor entry. Align horizons explicitly to the respective reference dates and disclose any horizon offset. Retain original transaction date and actual SEC filing date; do not add a presumed two-day lag after filing.


# Approved implementation clarification — SEC alert latency vs stock-price freshness (November 6, 2026)

The scanner shall send prompt SEC filing-based Pushover alerts without waiting for a current-day or previous-day MarketParquet daily OHLCV update. Each alert must explicitly label the last available daily bar date; no stale bar is to be represented as a live quote. Research outcome updates are run on completed daily bars as they arrive. Real-time stock-price data is not required for the initial scanner or historical research engine; optional live quotes may be added later. This does not change the approved next-session-open investor entry convention or make filing-date-close a tradable price.

## November 7, 2026 — entry direction and pullback depth

D-054 carries forward the two approved entry-context measurements from the Word v0.10 specification, where they were numbered D-048. At investor entry, pullback depth is the highest intraday high over the 63 completed sessions minus the last completed close, divided by the stock’s fixed pre-entry ATR(14). Signed 21-session price change is the last completed close minus the close 21 sessions earlier, divided by the same ATR. It requires 22 closes. Missing history stays missing. Both are continuous context fields.

**D-055 — Approved first market-regime comparison.** Use the same 21 close-to-close intervals ending at the last completed session before entry for stock direction, relative performance versus the assigned entry-date benchmark, and SPY regime. For this comparison, a laggard is a stock with both a negative prior stock move and negative stock-minus-assigned-benchmark performance. Classify SPY as flat when its absolute 21-session change is less than 0.5 of its own pre-entry ATR(14), down at or below −0.5 ATR, and up at or above +0.5 ATR. Use only completed bars. Compare subsequent outcomes at the approved horizons by regime, with named matched benchmarks, paired excess in stock ATR units, and counts. Missing benchmark assignments remain flagged. Any proxy comparisons must be labeled. These are study strata and do not change eligibility.

**Open design question.** The tentative pullback-depth bands of under 2 ATR, 2 to under 5 ATR, and 5 ATR or more, and further insider-role and cluster splits, remain proposals for subsequent analysis.


# What we have learned so far

November 7, 2026 · Exploratory pilot findings

The January–September 2026 pilot produced two leads for independent testing: larger clusters of distinct buyers and purchases after mild stock declines when the broad market was flat or rising. CFO participation may add information within a large cluster. The pilot has yet to establish a reliable trading edge.

The pilot screened 6,604 Form 4 purchase candidates, with forward prices through November 5. The public investor enters at the next regular-session open after filing. Returns below are price-only ending returns at 21 trading sessions, measured in the stock’s fixed pre-entry ATR. SPY, ONEQ, and IWM use the same entry and exit dates and the same stock ATR scale. The individual historical benchmark assignment is unavailable in this pilot, so the ETFs are shown separately.

## Results at 21 trading sessions

| Pilot group | Entries | Stock | SPY | ONEQ | IWM |
| --- | ---: | ---: | ---: | ---: | ---: |
| All screened buys | 4,546 | +0.02 | +0.15 | +0.23 | +0.09 |
| CFO buys | 287 | −0.10 | +0.09 | +0.16 | +0.07 |
| CEO buys | 736 | −0.29 | +0.15 | +0.22 | +0.08 |
| Non-officer directors | 2,050 | +0.09 | +0.14 | +0.22 | +0.08 |
| Four distinct buyers | 101 | +0.79 | +0.05 | +0.05 | +0.18 |
| Five or more distinct buyers | 64 | +0.59 | +0.15 | +0.12 | +0.32 |
| First four-plus entry, CFO among buyers | 57 | +0.97 | +0.07 | +0.11 | +0.08 |
| First four-plus entry, no CFO identified | 80 | +0.59 | +0.13 | +0.12 | +0.27 |
| Stock down 0.5 to <2 ATR, SPY flat¹ | 132 | +0.63 | +0.06 | +0.10 | −0.23 |
| Stock down 0.5 to <2 ATR, SPY up¹ | 455 | +0.26 | +0.06 | −0.04 | −0.03 |
| Stock down 5+ ATR, SPY down¹ | 211 | +0.48 | +0.50 | +0.75 | +0.46 |

¹ Equal weight per entry date. All other rows give each stock entry or disclosure equal weight. Samples can overlap. In particular, the pooled first four-plus entry and the separate four- and five-plus-buyer groups answer different questions and should stay separate.

## What held up in the pilot

- **Number of buyers.** Count different officers and directors who bought the same stock in the preceding 15 trading sessions and whose filings were already public. Repeat purchases by one person count once. Four and five-plus buyers beat all three references at 21 sessions even with equal weight per entry date. One and two buyers lagged all three across all five tested holding periods. The 21-session excess over SPY was +0.74 ATR for four buyers (95% interval −0.38 to +1.95) and +0.44 ATR for five-plus (−0.51 to +1.40). Neither passed the statistical test. Four buyers also beat the three references at six months, based on 39 entries and limited independent calendar coverage.
- **CFO participation.** CFO buys did better than CEO buys overall at 21 sessions, and non-officer directors were roughly in line with the same-date references. The mean CFO-minus-CEO stock difference shrank to about +0.01 ATR across the 114 companies where both bought, with unmatched dates and benchmark unavailable for that within-company comparison. Within first four-plus clusters, CFO participation was associated with +0.44 ATR more excess over SPY (95% interval −1.30 to +2.42, raw p=0.61). The direction held with equal date weighting and among exactly-four-buyer entries. Incomplete filing roles mean some buyers in the no-identified-CFO group may have been CFOs.
- **Stock decline and market direction.** The stock measure is the net change over 21 completed sessions before the actual insider purchase, scaled by that stock’s pre-purchase ATR. A 0.5 to under 2 ATR decline in a flat or rising SPY market beat all three ETF references even with equal date weighting. Those groups spanned 49 and 97 entry dates, respectively. Stocks down at least 5 ATR showed little advantage during broad declines after equal date weighting. They averaged −0.43 stock ATR versus +0.02 SPY, 0.00 ONEQ and −0.06 IWM when SPY had been rising (162 entries, disclosure-weighted).
- **Broad market decline alone.** Using one-, three-, or six-month SPY lookbacks before purchase, every market-down band with data lagged all three references at the 21-session horizon. The deepest one- and three-month groups and the moderate six-month decline group were the same 70 disclosures across nine entry dates. Treat that as one set of observations viewed through three lookbacks.
- **Entry timing.** Use the next regular open after filing for investable results. The filing-day close is a separate descriptive reference because the filing can become public after that close. The pilot showed that changing the entry reference could change the sign of the typical result.

## Candidates for a future score

- Retain distinct buyer count and stock decline crossed with the broad-market regime as the first two candidate scoring inputs. Retain CFO participation within four-plus clusters as a secondary interaction. The pilot gives less support to CFO status by itself, very deep stock declines, and broad market declines by themselves.
- Before looking at a separate period’s returns, specify the buyer window, decline bands, 21-session primary horizon, benchmark mapping, and how repeated issuers and overlapping dates will be handled. Verify each security’s benchmark as of entry. Use more historical price coverage so the test spans separate market episodes.
- Keep the underlying results separate by feature, horizon, and sample. A future score is a proposal. Choose weights and evaluate any combined score only after individual features and their overlap are tested on separate data.

## Source reports

- [Buyer counts, statistical tests, and CFO participation](https://chatgpt.com/library?file_id=libfile_d742aa48034c8191a4aee1d54e1c64dc&account_id=personal)
- [Stock decline and market regime matrix](https://chatgpt.com/library?file_id=libfile_aca3eb087cc0819196c9493fe80ed2b9&account_id=personal)
- [Broad market lookbacks](https://chatgpt.com/library?file_id=libfile_e178bf4db29c819184d8ed68c825be97&account_id=personal)
- [Project handoff and source runs](https://github.com/kidcharlema9ne/insider-scanner/blob/main/research_docs/FREE_YEAR_HANDOFF.md)
