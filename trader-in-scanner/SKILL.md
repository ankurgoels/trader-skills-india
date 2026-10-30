---
name: trader-in-scanner
description: >-
  Chart Scanner for the Indian market (NSE). Builds a day-trading list from
  NSE's EQUITY_L.csv (EQ series, minus ASM/GSM surveillance stocks, MIS-eligible
  at Zerodha), runs a pre-market scan of daily closes (20-day closing-high
  breakout, bull flag, reclaimed the 20-day average, oversold, oversold bounce)
  and an opening-range breakout scan on 5-minute bars from the 9:15 AM IST open,
  then writes trader/watchlist.json. Free Yahoo (.NS) data. Use when the user
  says "scan NSE", "Indian market", "find me setups in India", "Nifty
  breakouts", "NSE opening range breakouts", "pre-market scan India", "build my
  NSE watchlist", or at the start of an Indian trading day.
---

# trader-in-scanner

The India version of trader-in-scanner. It reads charts and lists the ones that match
a rule. A scan is a list of charts that match a rule, not a list of stocks to buy,
and a setup on a chart is not a prediction. SEBI's own study found over 91% of
individual F&O traders lost money in FY25; the scanner does not change that, and
this is education and tooling, not SEBI-registered investment advice.

`/home/ankur/.agents/skills/trader-in-scanner` below is this skill's folder.

```bash
python3 "/home/ankur/.agents/skills/trader-in-scanner/scan.py" universe                      # -> trader/universe.txt
python3 "/home/ankur/.agents/skills/trader-in-scanner/scan.py" daily                         # before the open -> trader/watchlist.json
python3 "/home/ankur/.agents/skills/trader-in-scanner/scan.py" daily --symbols RELIANCE,TCS,M&M   # or --watchlist FILE, --limit 200
python3 "/home/ankur/.agents/skills/trader-in-scanner/scan.py" orb                           # after 9:35 AM IST -> trader/watchlist.json
python3 "/home/ankur/.agents/skills/trader-in-scanner/scan.py" orb --at 10:00                # cut the clock at 10:00 AM IST
```

Flags: `--min-price 20`, `--min-volume` (daily 500,000, orb 0), `--or-minutes 15`,
`--max-confirm 200`, `--now "2026-10-28 10:00"` (IST), `--offline PATH`, `--no-write`,
`--show N`, `--json`; `universe` also takes `--min-mis 2` and `--no-mis`. Exit code 0
when the scan found something, 1 when it found nothing or could not run.

## Files

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: `SYMBOL\|Name`, raw NSE symbols (`M&M`, `BAJAJ-AUTO`) |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 15:00 IST) |

## The universe

`universe` downloads, in this order:

1. `nsearchives.nseindia.com/content/equities/EQUITY_L.csv`: keep series `EQ` only (no BE/BZ trade-for-trade, no SME, no ETFs).
2. `nseindia.com/api/reportASM` and `/api/reportGSM`: drop every symbol on either list. If either list can't be read the command stops rather than build a list that could include them.
3. `api.kite.trade/margins/equity` (Zerodha's public file): keep only symbols with `mis_multiplier` of at least 2. `--no-mis` skips this.

On 29 Oct 2026 that gave 2,368 EQ stocks, 167 dropped for ASM/GSM, 786 for no MIS leverage, 1,415 kept. NSE needs a browser User-Agent; the script sends one. Refresh weekly, or daily if you trade the edges.

## The daily scan (before the open, or after 3:30 PM)

Yahoo spark returns closes for 20 symbols a request (`SYMBOL.NS`, `&` is URL-encoded). The five setups are computed from daily closes only:

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

Hits are listed most traded first (price times volume). Today's bar is left out until 3:30 PM IST.

## The opening-range breakout scan (during the session)

NSE opens at 9:15 AM IST (pre-open call auction 9:00 to 9:15; the 9:15 bar opens at the auction price). The range is the first 15 minutes: the 9:15, 9:20 and 9:25 bars. A hit is the first completed 5-minute bar to CLOSE above the range high, at that bar's close time. The earliest useful run is 9:35 AM; 10:00 is the classic.

Stage 1 reads every symbol's 5-minute closes and keeps a chart only if a completed bar after the range closed at or above the range's highest close (necessary, so no breakout is lost). Stage 2 fetches each candidate's real highs and lows, at most `--max-confirm` (200), most traded first, and prints PARTIAL with the count skipped. A chart is usable only when every 5-minute bar from 9:15 to the cutoff is there.

The default last entry is 15:00 IST: Zerodha squares MIS positions off at 15:25 (15:12 for stocks in the closing auction, Rs 50 + GST per order), so a later breakout leaves no time. It prints one plain line and writes nothing before 9:35, on a weekend or NSE holiday, after the close, or after `no_entries_after`.

## Calendar and data limits

- IST is UTC+5:30 all year. Holidays are the `NSE_HOLIDAYS` table in `scan.py` (2026 only; NSE publishes 2027 in mid-December, so add it then, or 2027 weekdays count as open). The Muhurat session (Sun 8 Nov 2026, 14:20 to 15:30) is not modelled: the scanner treats it as closed.
- Closing auction: from 3 Aug 2026 F&O stocks stop continuous trading at 15:15; from 7 Dec 2026 all stocks stop at 15:30 (secondary sources, circular not opened). It only matters for late-day bars.
- Yahoo is free, unofficial and often answers 429. query2 first, query1 on a 429 or 5xx, one retry after 5 s. When no chart comes back the scan says so instead of printing "No setups". Yahoo's 5-minute history is about 60 days.
- Partial results are said as partial: "Fetched 1,380 of 1,415 charts (35 failed or had no data)". Never round a partial scan up to "the whole market".
- Fallbacks if Yahoo keeps refusing: Zerodha `get_historical_data` (needs a Kite login), Upstox keyless candles (unstable, untested here), TradingView's scanner (latest bar only, and its terms bar automated use).

## Steps

1. Weekly: `scan.py universe`.
2. Before the open: `scan.py daily`. Tell the user the counts (fetched, liquid, scanned, hits) and the top few by setup.
3. After 9:35 AM IST: `scan.py orb`. Tell the user how many usable charts broke their range and when; a later hit is closer to the price now.
4. The user picks one chart. Hand it on: `/trader-in-news SYMBOL`, then `/trader-in-entry SYMBOL`. Never pick for them.

## Rules

- Say what was scanned: symbols, charts back, usable, and the time of the data (IST).
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy, never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not financial advice and not SEBI-registered investment advice. A rules check is not a recommendation.
- Paper trading by default. Going live is the user's own decision, in their own config.
- Nothing here places an order. No F&O, options, margin beyond MIS, or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the desktop config, never in the chat.
