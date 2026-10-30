---
name: trader-in-insiders
description: >-
  The India replacement for the US congress-trades tracker. Shows who is buying
  and selling an NSE stock from public SEBI-mandated disclosures: bulk and block
  deals, promoter and director trades (SEBI PIT Reg 7), large-holder
  acquisitions and sales (SAST Reg 29) and the day's FII/FPI and DII flows.
  India has no politician-trade disclosure like the US STOCK Act, so this does
  not track politicians. Use when the user says "who is buying RELIANCE", "any
  insider buying", "promoter selling", "bulk deals today", "block deals", "FII
  DII flows", "SAST filings", "what are the big investors doing", "smart money".
argument-hint: "[deals|fii|insiders SYMBOL|sast]"
---

# trader-in-insiders

Some people see a company before the market does: its promoters, directors and
the funds that move whole blocks of shares. India makes several of them file
what they did. This skill reads those filings and lists them. It is fast, not
early: every one of these arrives after the trade, some by days. There is no
inside information here, only public filings read quickly. Say that every time.

There is **no India equivalent of the US STOCK Act**: no source found shows MPs
or ministers filing trade reports (they file asset declarations, not trades). So
the old "what is Pelosi buying" question has no Indian answer, and the skill
does not pretend otherwise.

```bash
python3 "${CLAUDE_SKILL_DIR}/flows.py" deals [--symbol X]    # today's bulk + block deals, biggest first
python3 "${CLAUDE_SKILL_DIR}/flows.py" fii                   # FII/FPI and DII, latest day (provisional)
python3 "${CLAUDE_SKILL_DIR}/flows.py" insiders RELIANCE     # promoters, directors, designated persons (PIT Reg 7)
python3 "${CLAUDE_SKILL_DIR}/flows.py" sast --symbol X       # holders crossing thresholds (Reg 29); --from/--to DD-MM-YYYY
```

`--json` on any of them. No keys. NSE needs a browser User-Agent and a Referer;
the script sends both.

## What each one is, and how late

| command | source | what it shows | lag |
| --- | --- | --- | --- |
| `deals` | NSE `bulk.csv`, `block.csv` | trades of 0.5% of a company's shares or more (bulk), and large negotiated blocks in the block window (block): client name, buy or sell, quantity, price | same evening |
| `fii` | NSE `fiidiiTradeReact` | cash-market FII/FPI and DII buy, sell and net, Rs crore | provisional, same evening |
| `insiders` | NSE `corporates-pit` | trades by promoters, directors and designated persons above Rs 10 lakh a quarter, with holding before and after | filed within 2 trading days of the trade; real lag was often longer |
| `sast` | NSE `corporate-sast-reg29` | a holder crossing 5% or moving 2% in a company, promoter or not, with the mode (open market, preferential allotment, pledge) | within 2 working days |

## The rules

- **Say the lag.** Quote the filing date and the trade date. A filing is news about the past.
- **No filings is not no buying.** `insiders` queries by symbol and shows the newest rows. Date-ranged PIT queries returned nothing for Jul-Oct 2026 in testing, and RELIANCE's newest returned row was Feb 2026: say "no recent filings returned", never "no insider buying".
- **Read the mode.** `Off Market` and `Others` among relatives are often gifts and transfers, not conviction. `Pledge` is lending the shares as security, not selling them. A preferential allotment is a company issuing shares to a holder, not the holder buying in the market.
- **Same client on both sides.** In `deals`, a trading firm that buys and sells the same stock the same day (HFT and arbitrage desks) is not a view on the stock. Say so when you see it.
- **FII vs NSDL.** NSE's provisional FII figure and NSDL's FPI report use different methods and differ for the same day. Never mix the two series.
- **Not a signal.** A promoter buying is information, not an instruction. Never say "follow the insiders".
- Keep to what the filing says: names, numbers, dates, links. Do not guess motives.

## Steps

1. Run the command the user asked for. For a watchlist, loop `insiders` and `sast --symbol` over the symbols in `trader/watchlist.json` and `deals` once.
2. Summarise: the biggest items first, with filing date, who, buy or sell, size in shares and rupees, and the mode.
3. Add the context that changes the reading (a gift, a pledge, an HFT round trip, a stale feed).
4. Hand over to `/trader-in-news` to see whether an announcement explains it, then `/trader-in-entry` if the user wants to time a setup.

## What it never does

- Never says follow, copy, buy or sell because of a filing.
- Never infers inside information or intent.
- Never calls the data real time.

## Safety

Education and tooling, not financial advice and not SEBI-registered investment advice. This skill only reads public filings. Nothing places an order except `/trader-in-broker`, after `/trader-in-risk` passes and the user types an explicit yes for that order.
