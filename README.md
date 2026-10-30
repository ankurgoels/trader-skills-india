# Trader skills for India

11 Claude skills for day trading on the NSE: scan the market for setups, track announcements, time every entry and exit, replay every outcome before you risk a rupee, and size and check orders before they reach Zerodha.

Free, MIT, no signup, no API key. The tools are plain Python that read free public data: NSE's own files and filings (EQUITY_L, ASM/GSM lists, corporate announcements, XBRL results, bulk/block deals, SEBI insider and SAST filings, FII/DII flows), Zerodha's public margin file, Google News and Yahoo Finance charts (`SYMBOL.NS`).

> **Derived from [Jake Schincariol's day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)** (MIT), the US version of this pack. The method, the structure and most of the code are his; this repo changes the market, clock, rules, costs, data sources and broker for India. The skills here are named `trader-in-*` so they can sit next to the US `trader-*` skills. Both copyright notices are in `LICENSE`.

Nothing here places an order on its own. No trade goes through until you say yes, and dry run is the default.

## Install

Paste this into Claude:

```
https://github.com/ankurgoels/trader-skills-india

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add ankurgoels/trader-skills-india
/plugin install trader-skills-india@trader-skills-india
```

Installed as a plugin, the skills are namespaced (`/trader-skills-india:trader-in-scanner`). To get plain `/trader-in-scanner`, copy the folders:

```bash
git clone https://github.com/ankurgoels/trader-skills-india.git
cp -r trader-skills-india/trader-in-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's `.claude/skills/`. The tools need Python 3.8 or newer and nothing to pip install. Order placement needs the Zerodha Kite connector in Claude (see `trader-in-broker`).

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-in-scanner` | Chart Scanner | Builds the NSE day-trading list (EQ series, minus ASM/GSM, MIS-eligible) and scans it for opening-range breakouts, flags and oversold bounces. |
| `/trader-in-news` | News Monitor | New NSE announcements, results and board-meeting dates, headlines, and how far each stock is from yesterday's close. |
| `/trader-in-entry` | Entry Timer | Watches a setup bar by bar from the 9:15 open and tells you the moment to get in. |
| `/trader-in-exit` | Exit Planner | Sets your stop and target before you enter, on the stock's tick, and refuses a target that can't pay the costs. |
| `/trader-in-timemachine` | Time Machine | Replays the rest of the session 10,000 times from the stock's own 5-minute bars, plus every past time the setup fired. |
| `/trader-in-risk` | Risk Manager | Checks every trade against your limits: whole shares, stop required, max loss, entry window, daily limits. |
| `/trader-in-budget` | Budget Manager | Sizes every position to your budget (in rupees) and your max loss per trade. |
| `/trader-in-broker` | Order Executor | Zerodha Kite tickets, dry run by default, never without your yes. |
| `/trader-in-alerts` | Price Alerts | Rings when a price, a stop, the opening bell or your flat-by time hits. |
| `/trader-in-analyst` | Earnings Analyst | Quarterly results from NSE's Ind-AS XBRL filings, year on year. |
| `/trader-in-insiders` | Insider and flow tracker | Bulk and block deals, promoter trades (SEBI PIT), SAST filings, FII/DII flows. Replaces the US congress-trades skill. |

## What is different from the US pack

| | US pack | India pack |
| --- | --- | --- |
| Session and clock | NYSE 9:30 to 16:00 ET, daylight saving | NSE 9:15 to 15:30 IST (UTC+5:30, no DST), pre-open 9:00 to 9:15 |
| Holidays | NYSE list, early closes | NSE 2026 list, no early closes (add 2027 when NSE publishes it) |
| Universe | Nasdaq Trader symbol lists | NSE `EQUITY_L.csv`, minus ASM/GSM, with a Zerodha MIS multiplier of 2 or more |
| Prices | cents | rupees, per-stock tick (Rs 0.01 under 250, 0.05 to 1,000, 0.10 above, the last assumed) |
| Orders | Alpaca brackets, fractional shares | whole shares, Zerodha `place_order`, no brackets: entry then a separate SL-M stop |
| Day-trade rule | pattern-day-trader check | none in India; auto square-off (Zerodha MIS 15:25, 15:12 for closing-auction stocks) and ~0.083% round-trip costs instead |
| Filings | SEC EDGAR 8-K and XBRL | NSE announcements, event calendar and Ind-AS XBRL |
| Smart money | congress trades (STOCK Act) | SEBI PIT, SAST, bulk/block deals, FII/DII (India has no politician-trade disclosures) |
| Paper trading | Alpaca paper account | none: `"paper": true` is a dry run and Claude does not call `place_order` |

The research behind these choices, with sources and what was not verified, is in [`docs/research-report.md`](docs/research-report.md).

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 15:10                                           (while it is open)
news / analyst / insiders                                                     (on a schedule)
```

An example with illustrative prices (RELIANCE, a Wednesday):

1. **`/trader-in-scanner`** after 9:35 AM IST lists the charts that closed above their 9:15 to 9:30 opening range.
2. **`/trader-in-news`** shows the announcements, any results or board meeting in the next 7 days, and the move.
3. **`/trader-in-entry`** says waiting, then triggered: the first 5-minute close above the range high, say 1,167.40.
4. **`/trader-in-exit`** sets the stop at the range midpoint (1,165.20, risk 2.20 a share) and the 2R target (1,171.80), flat by 15:10. A target that doesn't clear ~0.09% of costs is refused.
5. **`/trader-in-timemachine`** replays the rest of the day 10,000 times and says how often the target, the stop or neither comes first, with its honest verdict.
6. **`/trader-in-budget`** with a Rs 1,00,000 account and a Rs 500 max loss sizes whole shares (64 here, bound by the 75% position cap) and writes a bracket-shaped proposal.
7. **`/trader-in-risk`** checks it: PASS or BLOCK, with the reason.
8. **`/trader-in-broker`** shows the ticket. In a dry run it stops there. Live (`"paper": false`, your decision), you type yes for that exact order, Claude calls Zerodha's `place_order`, and Claude's own Allow once / Deny card asks again. The stop is then its own ticket.
9. **`/trader-in-alerts`** rings on the stop, the target and at 15:10.

## The tools

All standard-library Python.

```bash
python3 trader-in-scanner/scan.py universe                              # NSE EQ stocks, minus ASM/GSM, MIS-eligible
python3 trader-in-scanner/scan.py daily                                 # pre-market setups
python3 trader-in-scanner/scan.py orb --at 10:00                        # opening-range breakouts so far
python3 trader-in-news/news.py --tickers RELIANCE M\&M --hours 12       # announcements, headlines, upcoming results
python3 trader-in-entry/entry.py check RELIANCE --setup orb
python3 trader-in-exit/exit.py plan --symbol RELIANCE --entry 1167.40 --or-high 1170.3 --or-low 1160.15 --write
python3 trader-in-timemachine/timemachine.py run --write
python3 trader-in-budget/size.py --write                                # -> trader/orders.json
python3 trader-in-risk/check.py                                         # PASS / BLOCK per order
python3 trader-in-broker/ticket.py show                                 # the tickets, READY or not
python3 trader-in-alerts/alerts.py add --from-plan
python3 trader-in-analyst/facts.py RELIANCE TCS                         # quarters, growth, EPS
python3 trader-in-insiders/flows.py deals                               # bulk and block deals
```

There is no automated test suite yet. The tools were checked by running them live against NSE where it answered, and offline on synthetic bars for the entry, exit, budget, risk, broker and time machine chain. Yahoo returned HTTP 429 from the test host, so the Yahoo-based fetches (`.NS` charts) have not been run live.

## Fine print

**Not financial advice, and not SEBI-registered investment advice.** This is software that reads public data and does arithmetic. It does not know your situation and cannot see the future. Most people who day trade lose money; SEBI's FY25 study found over 91% of individual F&O traders lost money (an F&O study, no cash-intraday figure was verified). Talk to a SEBI-registered adviser if you need advice.

**No trade goes through until you say yes.** Only `/trader-in-broker` can lead to an order, and only after `/trader-in-risk` passes that exact order and you type yes for it in the chat. Set the Zerodha order tools to "Needs approval" in Claude, never "Always allow". No F&O, margin beyond MIS, short selling or leverage unless you turn them on.

**Zerodha has no paper account.** Every order sent through Kite is real, so `"paper": true` means a dry run. Whether SEBI's retail algo-trading framework affects placing orders through the Kite API from an AI assistant was not researched: check Zerodha's notices before going live.

**Intraday has no bracket or OCO order on Kite.** Do not rest the stop and the target as two sells on the same MIS shares: both could fill and leave you short.

**The Time Machine is a simulation, not a prediction.** A stop is a plan, not a guarantee. The data is free and unofficial: Yahoo, NSE's website JSON and Google News can lag, change, or refuse requests, and NSE's terms on scripted access were not found.

**Calendar and rules to keep current.** The holiday list covers 2026. The closing-auction timings (from 3 Aug 2026 for F&O stocks, from 7 Dec 2026 for all) and the tick size above Rs 1,000 come from secondary sources or are assumed; check NSE's circulars.

**Taxes.** Intraday equity gains are treated as speculative business income in India; nothing here is tax advice.

## Files

```
trader-in-scanner/     SKILL.md, scan.py
trader-in-news/        SKILL.md, news.py
trader-in-entry/       SKILL.md, entry.py
trader-in-exit/        SKILL.md, exit.py
trader-in-timemachine/ SKILL.md, timemachine.py
trader-in-risk/        SKILL.md, check.py
trader-in-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-in-broker/      SKILL.md, ticket.py
trader-in-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-in-analyst/     SKILL.md, facts.py
trader-in-insiders/    SKILL.md, flows.py
docs/                  research-report.md
.claude-plugin/        plugin.json, marketplace.json
```

## License

MIT, see `LICENSE`. Original work copyright Jake Schincariol; changes for the Indian market by the trader-skills-india contributors.
