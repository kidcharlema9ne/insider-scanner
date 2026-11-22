# Leads digest (read this first; the log is for going deeper)

Purpose: one page so a new chat does not have to read the 600-line `research_docs/SHARED_LOG.md`. Every line points to the log entry that holds the script and run link. This page repeats numbers from the log and creates none; if it disagrees with the log, the log governs. Last refreshed: 9 Nov 2026, after Entry 86 (C41a/b row; other rows last refreshed after Entry 70).

## How to read the log cheaply
- Latest entries only: `tail -n 40 research_docs/SHARED_LOG.md`, or `grep -n '^## Entry' research_docs/SHARED_LOG.md | tail -5`.
- One entry: `awk '/^## Entry 52 /{p=1} p{print} /^## Entry 53 /{exit}' research_docs/SHARED_LOG.md`.
- Deep dives by topic: survivorship = Entries 38, 40, 44, 49, 65; costs = 45, 70; stops = 62, 63, 69, 70; sizing = 64; score = 51; deep fall = 36, 42, 49, 52, 66, 67; Nasdaq lag = 37, 39, 41; basing = 59-61.

## Base rule (Michael's words, D-064/065/066/068)
Four or more distinct officers/directors bought (purchase date) within 15 sessions before entry, all filed; $3M daily dollar volume; enter next open after the filing that makes four; 21-session price-only hold; results in ATR with SPY beside them. Development 2006-2020 n=1,372: +0.154 ATR over SPY gross, about zero after assumed costs (Entries 28, 45). A lead, not an edge. Sealed years 2021-2025 stay closed; Michael is not ready.

## Leads (all post hoc / exploratory; none is an edge)
| Lead | What | Headline (excess over SPY, ATR) | Status | Entries |
|---|---|---|---|---|
| C8 / D1 / F | Deep 12-month fall. D1 = fell-most fifth (cut -15.3 ATR) = the fixed rule F: down 15+ ATR over 12 months | D1 +0.593 (n=255); F +0.599 (n=269, ~1.5 a month); 2011-2020 +0.565 (n=175); pay sits in falls of 50%+ | Lead; survivorship and costs unresolved | 36, 38, 42, 44, 45, 49, 52, 67 |
| C16 / N | Nasdaq lagging SPY over 63 sessions (lowest fifth) | +0.60; one-month effect; no mechanism | Lead; weaker in 2011-2020 | 37, 39, 41, 42, 58 |
| D1 and N together | Both | +1.434 (n=52, 0.29 a month) | Thin | 51, 64 |
| C26 percent drawdown (P) | Down 50%+ from the 252-session closing high | +0.468 (n=444, ~2.5 a month; +0.638 without the 3 episodes); a step at 50%, not a ladder; weaker than F; P and F together +0.662 (n=218), P adds an unproven +0.33 on top of F | Lead (second ruler for C8); graded points not supported | 66, 67 |
| C29 excursions and stops on F | Absolute MAE/MFE and trailing stops on F (n=269) | 1 month stock +0.817 ATR (SPY +0.218); 2 months +1.559 (SPY +0.435); T20 stock +1.088 (SPY +0.197); A4 stock +1.464 (SPY +0.566); MAE reached -4 ATR in 6% (1 mo) / 16% (2 mo); stops do not beat the plain 2-month hold | Descriptive, post hoc, NEW CODE | 69 |
| C30 costs and stop grid on F | Model costs (published 2013 spread table + square-root impact) and 7 stops x 5 holds on F | Round-trip cost 0.04 (mild) / 0.11 (realistic) ATR vs the standing 0.10 assumption; F excess net of realistic cost +0.49 (21 sessions), +1.02 (42); no stop beats the plain hold; 2 months = 3-4 months, 6 months era-dependent; no cell best in both eras | Descriptive, post hoc, model costs, NEW CODE | 70 |
| C23 basing | Inside D1, choppy last 2-3 months beats orderly slide | +0.80 (n=170) vs +0.17 (n=85) | Weak lead (best of 12 = 31.8%) | 59-61 |
| C41a/b insider history | Buyers' own record, cohort 2008-04 to 2020 (n=1,165, excess +0.130). EARLIER-BUY SCORE > 0 (mean excess of the buyers' earlier buys, min 2): n=308 +0.274 vs n=182 -0.112; passed all five consistency tests (both eras, 10 of 13 years, same-month, outside deep fall, both variants) but is mostly an AVOID signal on 42% of events (skipping the 182 lifts the cohort to about +0.175); week-shuffle chance 23% / 12.5%. NET SELLER (all sales): +0.378 vs +0.074 fails 2 of 5 tests and is essentially a 33-trade plan-sales-only cell (+1.319). Planned-buy filter (removing regular buyers) does not help. Entry 88 (portfolio test, $100k engine): veto of score <= 0 lowers CAGR +5.98% to +5.08%, bonus at +0.105U changes nothing (+6.04%), both +5.19%; the veto is no better than a random skip of the same size (64% of draws did better); on 42-session stop paths the flag separates only inside F | Earlier-buy score: lead, found and tested on the same cohort, PROVISIONAL code; NOT supported as a sizing veto or bonus in the portfolio (Entry 88). Net seller: not supported. Planned-buy filter: not supported | 85, 86, 88 |
| Score (Michael's idea) | Points for R1 (no CEO/CFO), N, D1 | 0/1/2/3 points = -0.04/+0.29/+0.63/+1.21 (n=17) | Descriptive only; weights not set | 51, MICHAEL_DETERMINATIONS 1 |

## Not supported (do not re-test)
Requiring the four buyers to buy on different dates (Entry 87, C42: excess falls from +0.154 to +0.121, +0.115 and +0.057 as the rule tightens; the trades it removes did as well or better), removing buyers who buy on a regular schedule (Entry 85), net seller before buying (Entry 86), CEO/CFO as a stand-alone filter, purchase size, director count, officer titles, short look-backs (3 months or less), SPY regime alone, oversold RSI and distance below short averages, bounce off the 12-month low (C20), SPY-200-day gate (C22), "moved up" after a base (C23). Longer holds than 21 sessions (Entry 46). Fixed stops (Entry 63: no gain in excess). 10-session trailing stop (Entry 62): +0.185 excess in 15 sessions, but a few big winners (net of the standing 0.10 ATR cost: +0.085 excess).

## Standing caveats
- Survivorship: 16.5% of events have no price series (31% in 2008); bounds in Entries 38 and 44. Entry 65: only 1 of 1,276 trades ended inside the hold, so the archive cannot measure wipe-outs; the D1 lead survives an assumed 1-3% wipe-out rate at -55% and fails at about 5% or more. No survivorship pattern across years or eras. Only a second price source with delisting history can settle it.
- Costs: Standing cost per Michael: 0.10 ATR round trip (the older 0.25 ATR columns are retired, not to be quoted). Entry 70's model cross-check (published spreads + impact): 0.04-0.11 ATR round trip for F at 0.1-1% of daily volume; the base rule (+0.154 gross) is still thin; the deep-fall group trades $14-20M a day, a quarter under $6M (Entries 45, 54, 57, 70). Still model estimates, no quotes or fills.
- Concentration: three large episodes (2008Q4, 2011Q3, 2020Q1) and a few spells; independent sample is tens of market periods.
- Liquidity inverted-U (C21): base rule pays at $5-25M a day, about zero above $25M.

## Open items
1. C27: dd252 >= 50% vs a fixed -15 ATR 12-month fall (not the quintile), alone and both, inside the score (Entry 66 next step).
2. Second price source with delisted history (decision for Michael), then re-price the missing 2011-2020 names.
3. Survivorship by dollar-volume band for F and N (cost part done for F in Entry 70); real fills to pin the cost model.
4. Michael's open scoring decisions: MICHAEL_DETERMINATIONS item 1.
