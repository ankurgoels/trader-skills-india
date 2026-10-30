---
name: trader-in-broker
description: >-
  Order Executor for Zerodha (Kite) on the NSE. Sends approved orders to your
  broker, dry run by default, never without your yes. Shows each order as a
  plain ticket (a bracket shows its stop-loss, take-profit and the max loss at
  the stop) plus the exact JSON for the Zerodha MCP's place_order, records your
  yes word for word, then Claude's own Allow once / Deny card asks again.
  Builds the sell ticket that closes a day trade by your flat-by time, records
  fills, and logs each trade's max loss so trader-in-risk can hold the daily
  limit. Covers connecting the Zerodha Kite connector (login link, no keys in
  chat) and setting order tools to "Needs approval". Use when the user says
  "place the order", "buy it", "execute", "send it to Zerodha", "close my
  position", "flatten", "get me out", "connect Zerodha", "set up Kite", or
  after /trader-in-risk passes.
argument-hint: "[order number]"
---

# trader-in-broker

The Order Executor is the only skill in this pack that can lead to a real
order, so it is the strictest. An order reaches the market only after three
separate gates, every time, for every order:

1. **trader-in-risk passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user clicked Allow once** on Claude's own permission card, which
   appears because the order tool is set to "Needs approval".

Two yeses from the user, one PASS from the rules. No yes, no order.

**Zerodha has no paper account.** Every order sent through Kite is real. So
`"paper": true` (the default) means a dry run: tickets, yes and the log work,
but Claude does NOT call `place_order`. Going live means the user sets
`"paper": false` in their own config, themselves.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id ID --filled-qty 64 --filled-price 1167.40
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 64 --price 1171.80
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 64
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets, checks that a reply
is a real yes for that order, builds the flatten ticket, and keeps the log in
`trader/state/broker.json`. `--now "2026-10-28 10:00"` pins the clock (IST).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-in-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-in-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `fill` and by `result --filled-qty` |
| `trader/plan.json` | the flat-by time for `flatten` |
| `trader/config.json` | `paper` (true = dry run), `product` (MIS by default; CNC for delivery) |

## Setup: Zerodha Kite connector

The Zerodha MCP is a connector (tools `mcp__...ZERODHA__*`): `login`, `get_profile`, `get_positions`,
`get_orders`, `place_order`, `modify_order`, `cancel_order`, `place_gtt_order` and more.

1. Call `login`. It returns a Kite link; the user opens it and authorizes in the browser. Claude never
   sees a password or a key. The session lasts the day, so log in again each morning.
2. In Customize > Connectors > tool permissions, set **`place_order`, `modify_order`, `cancel_order`,
   `place_gtt_order`, `modify_gtt_order`, `delete_gtt_order` to Needs approval**. Never Always allow.
   Read-only tools (`get_profile`, `get_positions`, `get_orders`, `get_holdings`, `get_quotes`,
   `get_ltp`, `get_historical_data`) can be allowed.
3. Check it: `get_profile` (read only) and confirm it is the user's own account.
4. In Claude Code instead, keep the order tools on ask in `.claude/settings.json`:
   `"permissions": {"ask": ["mcp__claude_ai_ZERODHA__place_order"]}`.

**How the proposal maps to Kite.** The proposal is bracket-shaped (entry, stop, target) because that is how
trader-in-budget and trader-in-risk check it. Kite has no bracket orders and no OCO for intraday (MIS),
so the ticket places the ENTRY with `place_order` (`product` MIS, `order_type` MARKET or LIMIT, `validity`
DAY). After it fills, place the STOP as a separate `SL-M` order with its own yes and Allow once. Do NOT also
rest the target as a sell: on MIS both sells could fill and leave you SHORT. Treat the target as an alert
and sell by hand. If Kite rejects `SL-M` for a stock, use `SL` with a limit a few ticks under the trigger.
Zerodha squares MIS off at 15:25 (15:12 for stocks in the closing auction) and charges Rs 50 + GST per
squared-off order, so the flat-by default is 15:10.

**Not researched:** whether SEBI's retail algo-trading framework affects placing orders through the Kite
API from an AI assistant. Check Zerodha's notices before going live.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT READY or BLOCKED goes back to
   `/trader-in-risk`.
2. Show ONE ticket and ask: "Place this order? Reply yes or no." One order per question. Never offer
   "yes to all".
3. Run `ticket.py approve --index N --reply "<the user's reply, word for word>"`. If it prints "Not
   recorded", the reply was not an explicit yes for this order (for example "sure", "yes to all", or a yes
   that names a different stock or amount). Ask again. Never turn a reply into a yes yourself.
4. Only after "Recorded your yes", and only when `paper` is false, call `place_order` with exactly the JSON
   the ticket printed. Claude's card appears: Allow once or Deny. In a dry run, stop here and say so.
5. Record what happened: `ticket.py result --index N --status placed --broker-id <id> --filled-qty Q
   --filled-price P` (from `get_orders` or `get_positions`), or `--status denied`, or `--status failed` with
   `--note`. A failed order is not retried without a new check and a new yes. The log keeps the entry's max
   loss for trader-in-risk's daily limit.
6. When the entry fills, show the stop leg as its own ticket and repeat 3 to 5 for it.

## Steps: while it is open, and out by the close

- trader-in-alerts watches the stop, the target and the flat-by time (`alerts.py add --from-plan`).
- When the stop or a manual target sell fills, record it:
  `ticket.py fill --symbol RELIANCE --side sell --qty 64 --price 1165.20`.
- By `flat_by` (15:10 IST), anything still open gets closed:
  1. Ask Zerodha how many shares are held: `get_positions` (read only; product MIS).
  2. `ticket.py flatten --symbol RELIANCE --qty 64` writes a market sell for those shares to
     `trader/orders.json`.
  3. `/trader-in-risk`. A sell that only closes what the user holds is never blocked by the daily limits or
     the entry window.
  4. `ticket.py show`, then the user's yes for that one order, as above.
  5. A resting stop-loss still holds the same shares: `get_orders` shows it; `cancel_order` it first
     (Needs approval), then `place_order` with the ticket, then `result`.

## Example (dry run)

```
ORDER 1 of 1, DRY RUN (Zerodha has no paper account: nothing is sent), Zerodha
  BUY 64 RELIANCE, market, good for today
  stop-loss 1165.20
  take-profit 1171.80
  max loss about Rs 140.80 if the stop fills at 1165.20 (it can fill worse in a fast market)
  READY: trader-in-risk PASS, waiting for your yes
```

With `paper` false the same ticket prints `{"variety": "regular", "exchange": "NSE", "tradingsymbol":
"RELIANCE", "transaction_type": "BUY", "quantity": 64, "product": "MIS", "validity": "DAY", "order_type":
"MARKET"}`. The user replies "yes". Claude records it, calls `place_order`, and the card shows that JSON with
Allow once and Deny. The `why` and the plan stay in the file; they are never sent.

## What it never does

- Never places an order without all three gates, and never two orders on one yes.
- Never places orders from a scheduled or background task: nobody is there to say yes.
- Never asks for, reads, stores or repeats passwords, tokens or API keys.
- Never sets `"paper"` to false. The user does that themselves.
- Never calls F&O, GTT or modify tools on its own.
- Never promises a fill price: a market order and a stop fill at whatever the market gives.

## Safety

- Education and tooling, not financial advice and not SEBI-registered investment advice. A PASS is a rules check, not a recommendation.
- Dry run by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-in-broker, and only when all three hold: trader-in-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No F&O, margin beyond MIS, short selling or leverage unless the config allows it and the user confirms.
