# Sealed-year hypotheses (FROZEN 9 Nov 2026, approved by Michael: "That's fine. Test them all. Let's go.")

Status: FROZEN on 9 Nov 2026 (approved by Michael in chat, 10:42 ET, after the draft was explained; he accepted the three hypotheses and the rounded sizes, and said to test them all). Written by Claude. No sealed-period return had been read when this file was frozen. One deviation is recorded in `research/canonical/sealed_run.py`: the 1%-of-daily-dollar-volume cap is not applied (no dollar-volume files for the sealed years; the cap never bound in the development portfolio, Entry 82). Under D-059 and D-068 the sealed run happens once, with one to three hypotheses declared in advance, and nothing changes afterward.

Sealed set: entries 2021-04-01 through 2025-12-31 (460 of 1,844 tradable 2006-2025 entries, D-068). The 2026 pilot is in-sample and is never part of it. Development years (through 2020-12-31) are not re-tested here.

## The rule being frozen (plain words; every number fixed now)
- Signal: four or more distinct officers or directors bought on the open market (purchase date) within 15 sessions, all filed; the stock trades at least $3 million a day; buy at the next regular open after the filing that makes four.
- ATR: average true range of the 14 sessions before entry. All returns are in ATR units with SPY's same-window return in stock-ATR units beside them (D-053).
- Exit: 3 ATR fixed stop below the entry open (filled at the stop, or at the open on a gap) or the close of session 42, whichever comes first.
- Cost: 0.10 ATR round trip (Michael's standing figure), shown net.
- Size, in units U (1U = 0.1% of equity per 1 ATR of movement, $100,000 start, no leverage, whole shares, 1% of average daily dollar volume cap): 1.0U base, plus
  - 12-month fall in ATRs (close 252 sessions before entry to the last close before entry, divided by the entry ATR): nothing up to 8 ATR, then +0.11U per ATR of fall, flat from 20 ATR (maximum +1.32U);
  - Nasdaq lagging SPY (ONEQ minus SPY over 63 sessions at or below -0.0195, the development fifth cut, NOT recomputed on sealed data): +1.00U;
  - no CEO and no CFO among the buyers: +0.20U.
  Total capped at 4.0U (largest possible uncapped total 3.52U). The 8U open-risk cap is not enforced, as in the development portfolio; the peak open size is reported.
- These sizes are the Entry 91/92 full-development fit rounded to simple numbers (+0.206U, +0.990U, +0.108U per ATR). The rounding is fixed now and is not tuned.

## Hypotheses (three)
H1, the sized system (what Michael would trade). $100,000 portfolio on all sealed entries with the rule and sizes above. PASS only if ALL hold:
 (a) alpha to SPY (daily regression, annualised) is above zero;
 (b) the sized portfolio's Sharpe AND Calmar are both above those of the same trades at flat 1.0U (the scaling adds risk-adjusted value, as it did out of era in Entry 91);
 (c) the maximum drawdown is shallower than SPY's over the same dates.
 FAIL if alpha is zero or below. If (a) holds but (b) or (c) does not, the result is NOT SHOWN.
H2, deep fall. Among sealed entries, those with a 12-month fall of 15 ATR or more (development: +0.60 ATR gross over SPY at 21 sessions, Entry 36 and 67), 21-session hold with no stop. PASS if the mean excess over SPY net of 0.10 ATR is above zero AND exceeds the mean of the other sealed entries AND the chance of the difference from shuffling excess inside the entry week (10,000 draws) is 10% or less. Fewer than 40 such entries = INCONCLUSIVE.
H3, Nasdaq lagging. Among sealed entries with ONEQ-minus-SPY over 63 sessions at or below -0.0195 (development: +0.60 gross, weaker in 2011-2020), same hold and same pass rule as H2. Fewer than 40 entries = INCONCLUSIVE.
The Nasdaq LEADING side is not a hypothesis (it was not sized and is weaker in the log); it may be reported descriptively only.

## Reporting rules (fixed now)
- One run, committed code, selftested on development years first (must reproduce the development portfolio of Entry 82 and the Entry 91 sizes before any sealed entry is read), workflow link in the log.
- Every number with SPY beside it, week-block 95% ranges, the three episodes' equivalents (2022 drawdown) shown, trade counts, by-year table, and the shuffle chances; false-discovery adjustment across H1-H3 shuffle statistics reported next to the raw values (D-033).
- Pass, fail and inconclusive are decided by the rules above and nothing else. No variant, cutoff, size or stop is changed after the run; the sealed years are then spent for this idea. The live Form 4 scanner continues to supply genuine forward data.
- Not hypotheses, not run: stop variants, other holds, other fall measures, anything found in development after this file is approved.

## Caveats written in advance
Every number above came from post hoc development data; the effect sat mostly in 2006-10 and in three crash periods; survivorship (Entry 65) and real fills are not in any number; 460 entries make a modest sample, so an INCONCLUSIVE result is likely for H2 and H3 even if the idea is real; the 2021-25 market (2022 drawdown, strong 2023-25 rally) differs from the development years.

## Decisions Michael made before freezing
All three hypotheses kept; rounded sizes accepted; pass rules as drafted (he did not ask for stricter ones).
