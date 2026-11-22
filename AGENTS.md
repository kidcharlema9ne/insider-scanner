# Insider Buying Research operating instructions

[Michael’s GitHub master index](https://github.com/kidcharlema9ne/Master-Index) locates projects by nickname, including the live Gmail sender, timers and reports.


**Futures data.** For ANY futures task ("find my futures"), read [FUTURES_DATA.md](FUTURES_DATA.md) first: where the daily futures prices live (Cloudflare R2, readable only through GitHub Actions secrets in this repo), how to fetch them, and the standing rules for futures work.

**Read order (keep it small).** Read [docs/LEADS_DIGEST.md](docs/LEADS_DIGEST.md) first (one page: base rule, leads, not-supported list, caveats, open items), then only the last two entries of the log (`grep -n '^## Entry' docs/SHARED_LOG.md | tail -3`, then read from the second-to-last heading). Open older entries one at a time, only when the digest points to them. Refresh the digest when a lead's status changes.

**Shared log (ChatGPT + Claude).** The full log is [docs/SHARED_LOG.md](docs/SHARED_LOG.md); do not read all of it. Before ending a chat, append a dated entry there with your results, the exact script, the branch and the workflow run link. Do not quote a number that has no committed script and run link. Mark entries CONFIRMED, REPORTED or PROVISIONAL as described in the log.

Read [the master specification](docs/MASTER_SPECIFICATION.md), [decision log](docs/DECISION_LOG.md), and [current handoff](docs/FREE_YEAR_HANDOFF.md) when resuming the study.

Whenever reporting an ATR return, put the applicable named, same-window benchmark beside it in stock ATR units. If it cannot be verified, display benchmark unavailable on the same row. Follow [D-053 in the master specification](docs/MASTER_SPECIFICATION.md#10-benchmarks-and-market-context).

After every substantive project update, give a concrete recommended next action and briefly explain why it comes next. If that action is already authorized, take it in the same turn. If blocked, identify the specific blocker and the action that resolves it. If a decision is required, give options and recommend one. Include a short checkpoint before switching chats.

**Candidate factors.** [docs/CANDIDATES.md](docs/CANDIDATES.md) lists leads found in the pilot data (SPY regime, price setup, no CEO or CFO among buyers, purchase size, ownership). They are candidates, not rules. Add new ones there with their script and run link; carry them as separate named factors into the frozen-rule test.

**Michael's determinations.** Read [docs/MICHAEL_DETERMINATIONS.md](docs/MICHAEL_DETERMINATIONS.md) at the start of every chat. It holds what Michael himself has decided or proposed (for example his scoring-system idea) in his words. Add to it only when he asks; never rewrite an existing item.
