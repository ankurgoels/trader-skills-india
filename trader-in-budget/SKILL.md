---
name: trader-in-budget
description: >-
  Budget Manager for the Indian market (NSE, rupees). Sizes every position to your budget and your max loss per
  trade. Reads the trade plan from trader-in-exit (entry, stop, target), finds
  the whole shares that fit inside four limits (max loss per trade, position
  cap, max order, cash after your buffer), says which limit decided it, and
  writes ONE bracket order (entry, stop-loss, take-profit) to
  trader/orders.json as a bracket proposal (trader-in-broker splits it into a Kite entry order and an SL order). A stop
  too far away for your max loss is a plain refusal, not a smaller order.
  Nothing is placed. Use when the user says "how many shares", "size this
  trade", "how much should I buy", "I have Rs 1,00,000", "I only want to risk Rs 500
  a trade", "set my rules", "keep 10% in cash", or after /trader-in-exit writes
  a plan.
argument-hint: "[budget in rupees]"
---

# trader-in-budget

The Budget Manager turns a plan ("buy RELIANCE at 364.18, stop 358.32") into an
exact order ("buy 8 shares"), inside rules the user sets once. The stop
decides the size: the further away the stop, the fewer shares. It writes a
proposal only. trader-in-risk checks it and trader-in-broker asks the user yes or
no. Day trading loses most people money. Sizing to a max loss keeps each
loss small; it does not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                        # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write        # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 364.00 --json  # a limit order at 364.00
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights RELIANCE=40,ITC=60 --config split.json   # weights mode, below
```

`--now "2026-10-19 10:15"` pins the clock (IST). A plan for
another day is refused: make a new one with trader-in-exit.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the rules (start from `config.example.json` in this folder) |
| `trader/plan.json` | the trade: entry, stop, target, setup, flat-by time (trader-in-exit writes it) |
| `trader/prices.json` | optional: a fresh price above the plan's entry means a bigger risk (trader-in-alerts writes it) |
| `trader/portfolio.json` | optional: its cash caps the size (trader-in-broker keeps it) |
| `trader/orders.json` | the one proposed bracket order it writes with `--write` |

## Step 1: set the rules once

If `trader/config.json` does not exist, copy `config.example.json` into
`trader/config.json` and ask the user for each value in plain words:

- **budget**: how much money this is for. Only money they can afford to lose.
- **cash_buffer_pct**: how much always stays in cash (default 10).
- **max_loss_per_trade_inr**: the most one trade may lose if the stop fills at the stop (default 500).
- **max_position_pct**, **max_order_inr**, **min_order_inr**: the biggest position (75% of the
  budget), the biggest order (Rs 1,00,000) and the smallest order (Rs 500).
- The day limits trader-in-risk enforces: **max_daily_loss_inr** (1,500), **max_trades_per_day** (3),
  **min_reward_risk** (1.0), **require_stop** (true), **no_entries_before** / **no_entries_after**
  ("09:35" / "15:00") and **flat_by** ("15:10"; Zerodha squares MIS off at 15:25), all IST.
- **blocked**: tickers they never want to trade.
- Keep **paper** true until they have watched it work on a paper account.

## Step 2: size the trade

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
```

Whole shares only: NSE cash trades whole shares. The size is
the smallest of four limits:

| limit | shares |
| --- | --- |
| max loss | `max_loss_per_trade_inr` / risk a share (entry minus stop) |
| position cap | budget x `max_position_pct` / entry |
| max order | `max_order_inr` / entry |
| cash | (budget minus the cash buffer) / entry, never more than the cash in `trader/portfolio.json` |

The entry it sizes at: the limit price with `--limit`. For a market order, the
plan's entry, or the price in `trader/prices.json` if it is fresh (under 15
minutes old) and higher. A price that ran up since the plan means a bigger
loss at the same stop, so fewer shares. A lower price never shrinks the risk.

It refuses, and writes no order, when: the size is zero shares, the order is
under the minimum, reward:risk is under `min_reward_risk`, the stop is not
below the entry, the target is not above it (the move already happened), the
plan is for another day, the ticker is blocked, or the plan is a short. Say
the reason to the user in one line.

## Step 3: show the user

Show the four limits, which one decided the size, the shares, the rupees
and the max loss at the stop. Say plainly that a stop is an order, not a
promise: in a fast market it can fill below the stop. Then hand over to
`/trader-in-risk`.

## Example

RELIANCE, Wed 2026-10-28. Entry 1,167.40, stop 1,165.20 (the opening-range midpoint), target 1,171.80 (2R). Risk 2.20 a share. The example config: Rs 1,00,000 budget, 10% cash buffer, Rs 500 max loss (illustrative prices).

| limit | the math | shares |
| --- | --- | --- |
| max loss | Rs 500 / 2.20 | 227 |
| position cap | 75% of Rs 1,00,000 = Rs 75,000 / 1,167.40 | **64 (decides it)** |
| max order | Rs 1,00,000 / 1,167.40 | 85 |
| cash | Rs 1,00,000 minus Rs 10,000 = Rs 90,000 / 1,167.40 | 77 |

64 shares = Rs 74,713.60. Max loss at the stop: 64 x 2.20 = Rs 140.80. It writes a bracket-shaped proposal (`qty` "64", `take_profit_limit_price` "1171.80", `stop_loss_stop_price` "1165.20"). `why` and `plan` are notes for trader-in-risk and trader-in-broker and are never sent to the broker. Kite has no bracket orders, so trader-in-broker places the entry, then the stop as a separate SL / SL-M order or a GTT.

A wider stop shrinks the size: one share risking more than the max loss gives no order at all. A Rs 0.09% round-trip cost (brokerage, STT, fees, GST) is not subtracted from the size; trader-in-exit refuses a target that cannot clear it.

## Weights mode (kept from v1)

`--weights RELIANCE=22.04,ITC=10.86` or `--targets FILE` (`targets.example.json`
here) splits a budget across a list by weight: the cash buffer comes off the
top, weights are renormalised to 100, any stock over `max_position_pct` is
pinned at the cap and its excess shared out, slices under the minimum order
are dropped, and amounts round to whole rupees so nothing is left idle by
accident. It buys whole shares and needs prices (`--prices trader/prices.json`). These are plain buys with no stop: trader-in-risk blocks them while
`require_stop` is true and counts each one against `max_trades_per_day`. Use
a separate config (`--config`) for a long-term split.

## Rules

- Proposals only. This skill never calls a broker tool.
- Never size money the user has not said is for this. Ask for the budget and the max loss.
- Every number comes from the config, the plan or the prices. Nothing is guessed.
- No projections: never say what a trade will make. A target is a plan, not a forecast.
- Free Yahoo prices are unofficial and can lag. The broker's price is the one that fills.

## What it never does

It never places, approves or schedules an order, never raises a limit on its
own, never shrinks a stop to fit more shares, and never sizes F&O,
margin or short positions.

## Safety

- Education and tooling, not financial advice and not SEBI-registered investment advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-in-broker, and only when all three hold: trader-in-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No F&O, margin beyond MIS, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
