# First calls checklist (Q4 reports, Feb–Mar 2027)

**Goal:** lock 5 calls in January, before each event, and reveal each once its horizon ends. That gives you a live, verifiable record by spring interview season.

## The rule for every earnings call
- `horizon_start_date` = **the report date**. Companies report after the close, so the baseline is the last close *before* the news.
- `horizon_end_date` = **5 trading days later**.
- **Commit at least 1 day before `horizon_start_date`.** The CLI refuses later commits unless you pass `--allow-late` and say so publicly.
- **Reveal on or after `horizon_end_date`.**

## Your five names

| Name | Event | When it reported last time | Commit by | Horizon | Reveal on/after |
|---|---|---|---|---|---|
| HOOD | Q4 FY2026 earnings | Q4 2025: Feb 10, 2026, after close ([Robinhood IR](https://investors.robinhood.com/events/event-details/robinhood-q4-and-full-year-2025-earnings)) | the day before the confirmed date | report date → +5 trading days | horizon end |
| COIN | Q4 FY2026 earnings | Q4 2025: around Feb 12, 2026 (inferred, not confirmed) | the day before the confirmed date | report date → +5 trading days | horizon end |
| NVDA | Q4 FY2027 earnings | Usually late February (not confirmed in this research) | the day before the confirmed date | report date → +5 trading days | horizon end |
| CBRS (Cerebras) | Q4 FY2026 earnings | First public report: Q1 on Jun 23, 2026 ([Cerebras IR](https://investors.cerebras.ai/news-releases/news-release-details/cerebras-systems-sets-date-first-quarter-2026-financial-results)). Fiscal year looks like calendar year, so Q4 likely Feb–Mar 2027 (unconfirmed) | the day before the confirmed date | report date → +5 trading days | horizon end |
| PURR | price horizon (no earnings) | n/a | **Jan 14, 2027** | Jan 15 → Jan 29, 2027 | Jan 29, 2027 |

> **Confirm every report date on the company's investor-relations page** in early January (they announce dates 2–4 weeks ahead). The dates above are last year's pattern, not this year's schedule.

## Steps for each call (about 30 minutes each)
1. **Write the note**, e.g. `~/research/hood-q4.md`. Cover:
   - the thesis in 3 sentences
   - the 3 KPIs that decide it, with consensus vs. your view
   - what would make you wrong
   - the confidence and why

   The note's SHA-256 is locked into the call, so you can't swap it later.
2. **Make the call file:**
   ```
   receipts template HOOD --event "Q4 FY2026 earnings" --start <REPORT_DATE> --end <REPORT_DATE+5 trading days> \
     --direction up --confidence 0.65 > ~/research/hood-q4.json
   ```
   Confidence must be between 0.50 and 0.99 with at most 2 decimals. Be honest: Brier scoring punishes overconfidence.
3. **Commit:**
   ```
   receipts commit ~/research/hood-q4.json ~/research/hood-q4.md --password-keychain research-receipts-testnet
   ```
   It prints the receipt number and the explorer link. Post the link on X ("locked my HOOD call, reveal Feb X") so the timestamp is public.
4. **Back up** `~/.research-receipts/` (Time Machine is fine). A lost salt means the call can never be revealed.
5. **After the horizon:**
   ```
   receipts reveal <ID> --password-keychain research-receipts-testnet
   receipts sync && receipts score && receipts export --out ~/data/research-receipts/receipts.json
   ```
   Publish the note alongside the reveal for the full story.

## Mission Board
Add these as milestones:
```
cd ~/Developer/operation-jarvis && python3 tools/mission_board.py milestone add "Lock HOOD/COIN/NVDA/CBRS/PURR receipts" --group "January"
```

## Honesty rules
- Commit every call you make for the record, including ones you expect to lose. Locked receipts are shown publicly, so skipping reveals is visible.
- Under 10 scored calls, the page says "too few to judge", because it is.
- If you take a job at a bank or broker, check with compliance before publishing more stock calls.
