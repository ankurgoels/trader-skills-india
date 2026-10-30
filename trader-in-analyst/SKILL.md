---
name: trader-in-analyst
description: >-
  The Earnings Analyst for NSE stocks. Reads a company's reported quarterly
  numbers straight from the exchange's own result filings (NSE's financial
  results list and the Ind-AS XBRL file behind each one) and sums up what
  changed: revenue, net profit, margins and diluted EPS, quarter by quarter,
  each against the same quarter a year earlier. Flags a stale feed, and EPS
  that moved because a bonus or split changed the share count. Reads an
  earnings call transcript when you paste one. Use when the user says "how did
  Reliance's results look", "analyze the results", "what changed this
  quarter", "is revenue growing", "compare margins", "sum up the call", "when
  does it report", or before trading a stock around its results.
argument-hint: "[symbols]"
---

# trader-in-analyst

Results move Indian stocks more than anything else on the calendar, and the
press release is written to put the best number first. This skill reads the
numbers the company filed with NSE under SEBI's LODR rules, lines them up
quarter by quarter, and says plainly what changed. For a day trader it answers
two questions before a trade: what did the last report say, and is the next
one inside this trade?

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE TCS --standalone --quarters 6 --json
```

No keys. NSE's JSON needs a browser User-Agent and a Referer; the script sends both and pauses between calls.

## What it reads

- `nseindia.com/api/corporates-financial-results?index=equities&symbol=X&period=Quarterly`: the list of filed results (period end, consolidated or not, audited or not, an XBRL link).
- The XBRL file behind each filing (`nsearchives.nseindia.com/corporate/xbrl/INDAS_*.xml`): revenue from operations, finance costs, profit before tax, tax, net profit and diluted EPS for the reporting quarter (context `OneD`; `FourD` is year to date).
- Amounts print in Rs crore. Indian companies file a standalone fourth quarter, so nothing is derived (the US skill's "derived Q4" is gone).
- Year-on-year compares with the filing four quarters earlier, so it fetches four more filings than it prints.
- Earnings calls: not fetched. If the user pastes a transcript, read it and sum up what management said changed: guidance, margins, demand, anything they declined to answer.
- The next results date is in `/trader-in-news` (its `UPCOMING` lines come from NSE's event calendar).

## The rules

- **Filed numbers first.** The table comes from the XBRL the company filed. Use the announcement or press release for context and say which numbers came from where.
- **Consolidated by default**, `--standalone` for the parent alone. Say which you quoted.
- **Say when the data lags.** NSE's feed can trail a result that is already out. When the newest filing is more than 150 days old the tool prints a NOTE (on 29 Oct 2026 RELIANCE's newest filing in the feed was the quarter ended Dec 2024): check the company's announcements before summarising.
- **Bonus issues and splits.** EPS is per share. When EPS moves very differently from net profit the tool says so; compare net profit unless the filing restates EPS.
- **Flag one-offs.** Net profit can include exceptional items and tax effects. Banks and NBFCs report differently (interest income, not "revenue from operations" in the same sense): say the table may not fit them, and read the filing.
- **Compare like with like.** Quarter-on-quarter changes mislead for seasonal businesses; use the year-on-year column.

## Steps

1. Run it for the companies in question (or the symbols on `trader/watchlist.json`).
2. Open the latest results announcement or the XBRL link when the numbers need context.
3. Write the summary: one line on the quarter (revenue, net profit, EPS, growth), one on margins, one on anything unusual (a one-off, a stale feed, a share-count change), and the links. Plain words, real numbers, no adjectives the numbers do not support.
4. If the next results fall inside the planned trade (an overnight hold, or results before the open), say it before `/trader-in-exit` sets the stop: a stop does not protect against a gap, the stock can open past it. MIS positions are squared off the same day, so an intraday trade is not exposed to an overnight gap, but results released during the session can move the stock sharply.

## Example (real run, 29 Oct 2026)

`facts.py RELIANCE --quarters 3` (consolidated, Rs crore): quarter ended 2024-12-31 revenue 243,865 (+7.0% on a year earlier), net profit 21,930 (+11.7%), net margin 9.0%, diluted EPS 13.70 (-46.3%). The tool notes that EPS moved -46% against net profit +12%: Reliance's bonus issue changed the share count, so the EPS comparison is not like for like. It also notes the newest filing it was given is 667 days old.

## What it never does

- Never says a stock is cheap, expensive, a buy or a sell. It reports what the company filed.
- Never invents a number the filings do not have.
- Never hammers NSE: one request per filing, with a pause.

## Safety

Education and tooling, not financial advice and not SEBI-registered investment advice. This skill only reads filings. Nothing places an order except `/trader-in-broker`, after `/trader-in-risk` passes and the user types an explicit yes for that order.
