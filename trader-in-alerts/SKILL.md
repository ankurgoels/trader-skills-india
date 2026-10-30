---
name: trader-in-alerts
description: >-
  Price Alerts. Rings when a price, a stop or the opening bell hits. Turns
  the trade plan into three alerts in one go (the stop, the target and "flat
  by close" at your flat-by time), plus above / below / stop / target levels,
  percent moves from the previous close, any time of day, and the NSE
  opening bell, each ringing once so you are not spammed. Knows NSE hours
  with the 2026 holidays (2027 once NSE publishes it) and no early closes, works
  out IST itself, fetches free delayed quotes (Yahoo chart JSON, SYMBOL.NS)
  one ticker at a time, and writes trader/prices.json for sizing and the
  risk check. Use when the user says "alert me when", "tell me if RELIANCE hits",
  "watch my stop", "watch my trade", "remind me to close by 3:10 PM", "is the
  market open", "when does the market open", "get me a price", or right
  after /trader-in-exit writes a plan.
argument-hint: "[ticker] [price]"
---

# trader-in-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when a stop alert rings,
nothing is sold by this skill. With a bracket order the stop-loss and the
take-profit already sit at the broker and do the work; the alerts tell the
user what happened and when it is time to be flat.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat by close from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 358.32
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 370.04
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:10 --label "flat by close" --before-close
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol KO --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write             # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan tickers
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-10-19 15:10"` pins the clock (IST); `--offline DIR`
reads saved quote files instead of the network.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-in-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest quotes, merged in, for trader-in-budget and trader-in-risk |
| `trader/portfolio.json` | the tickers held, for `quote --holdings` |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the IST clock passed `at` ("15:10") on a trading day | once per trading day |
| `opening_bell` | the NSE is open | once per trading day |

A rule with `"date"` is watched on that IST date only; `--from-plan`
rules carry the plan's date, so yesterday's stop never rings today. A `time`
rule with `"before_close": true` moves earlier on an early-close day; NSE has none, so it rings at its set time.

## Quotes

- `yahoo` (default): `query2.finance.yahoo.com/v8/finance/chart/<TICKER>`, an
  unofficial free JSON endpoint, one request per ticker, half a second apart.
  On a 429 it waits and tries once more; on a 429 or a 5xx after that it
  tries `query1`. It identifies itself as `day-trader-skill/2.0`.
- Quotes use `SYMBOL.NS` (`M&M` is URL-encoded). Stooq was US-only and is gone. Yahoo often answers 429; then use the Zerodha connector below.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts
  and for checking a size, not for timing an order. The broker's price is the
  one that fills. Each price in `trader/prices.json` keeps its quote time, and
  trader-in-risk only uses one under 15 minutes old.
- If both are down, read the price from the Zerodha connector (`get_ltp` or `get_quotes`, read only) and write it into
  `trader/prices.json` as `{"as_of": "...Z", "prices": {"RELIANCE": 366.48}}`.

## The NSE clock

Regular session 9:15 a.m. to 3:30 p.m. IST (pre-open 9:00 to 9:15), closed on weekends and on these weekday holidays, transcribed from a broker page that summarises NSE's circular (re-check nseindia.com):

- 2026: Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3, Apr 14, May 1, May 28, Jun 26, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25.
- 2027: not published yet (NSE publishes mid-December). The tool warns that the list covers 2026 only.
- Muhurat session: Sunday 8 Nov 2026, 14:20 to 15:30. The tool treats Sundays as closed and does not model it.
- No early-close days. From 3 Aug 2026 F&O stocks stop continuous trading at 15:15 for a closing auction (all stocks at 15:30 from 7 Dec 2026, per secondary sources).

IST is UTC+5:30 all year, so the tool needs no time zone database.
files and ignores the computer's own zone. For any other year it says the
holiday list is unknown.

## Steps

1. Right after trader-in-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by time.
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. Each run fetches only the tickers in today's
   rules and rings each alert once. A check reads the latest delayed quote;
   it is not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang in one line each. A stop or target alert means the
   bracket order has probably filled: check `get_open_position` and record the
   fill with trader-in-broker. "Flat by close" means close anything still open:
   trader-in-broker `flatten`, then trader-in-risk, then the user's yes. Never act
   for them.

## Example

RELIANCE on Wed 2026-10-28: entry 1,167.40, stop 1,165.20, target 1,171.80, flat by 15:10 (illustrative prices). `add --from-plan` writes `reliance-plan-stop`, `reliance-plan-target` and `reliance-flat-by` for that day. A `check` at 10:53 with a quote between the stop and the target:

```
NSE OPEN (2026-10-28 10:53 IST, regular session).
Nothing hit. 3 rule(s) watched today, RELIANCE Rs 1,168.10.
```

At 3:10 PM:

```
ALERT Flat by close: it is 15:10 IST (set for 15:10). Zerodha squares MIS off at 15:25. If RELIANCE is still
open, close it: trader-in-broker flatten --symbol RELIANCE builds the sell ticket, then trader-in-risk and your yes.
```

It rings once. The next morning the plan's three alerts are no longer watched; with `add --opening-bell`, the bell rings at 9:15.

## Rules

- An alert is a fact about a price or the clock. Say it as a fact.
- Never present a quote as live. Free quotes are delayed and unofficial.
- Confirm every new rule back to the user: ticker, type, level, day.

## What it never does

It never places, cancels or changes an order, never claims a quote is
live, and never predicts where a price is going.

## Safety

- Education and tooling, not financial advice and not SEBI-registered investment advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-in-broker, and only when all three hold: trader-in-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No options, margin, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
