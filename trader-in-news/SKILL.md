---
name: trader-in-news
description: >-
  News Monitor for the Indian market (NSE). Tracks news on every stock you
  watch: Google News headlines per symbol (India edition), NSE corporate
  announcements (results, board-meeting outcomes, resignations, acquisitions,
  insider and SAST filings, credit ratings), the next 7 days of results and
  board-meeting dates from NSE's event calendar, and how far each stock is from
  yesterday's close. Shows only what is new since the last check, newest first,
  in IST, tags each item and never repeats one. Use when the user says "any news
  on RELIANCE", "why is this moving", "what's the news on my NSE watchlist",
  "morning briefing India", "pre-open news", "monitor the news", "did anything
  break", "check the announcements", "when are results", or after
  /trader-in-scanner finds setups.
argument-hint: "[symbols]"
---

# trader-in-news

A chart can look perfect and still be about to gap on a results date, a
board-meeting outcome or an ASM listing. Before a setup becomes a trade, this
skill reads the feeds that carry those first, for every stock on the watchlist,
and tells you only what is new. It also prints how far each stock has moved
today, so a headline and a move sit side by side.

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                         # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS M\&M --hours 12
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-nse --json
```

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-in-scanner), raw NSE symbols |
| `trader/plan.json` | the trade you are planning (trader-in-exit) |
| `trader/portfolio.json` | what you hold |
| Google News RSS | `news.google.com/rss/search?q=SYMBOL+NSE+when:2d&hl=en-IN&gl=IN&ceid=IN:en` |
| NSE `/api/corporate-announcements` | SEBI LODR disclosures per symbol; `seq_id` is the key it remembers |
| NSE `/api/event-calendar` | results dates, board meetings, dividends in the next 7 days (`UPCOMING` lines) |
| Yahoo chart endpoint | last price against yesterday's close, `SYMBOL.NS` (unofficial; 429s are common, then the price line is skipped with a note) |
| `trader/state/news.json` | what has been shown (kept 30 days) |

NSE's JSON needs a browser User-Agent and a Referer; the script sends both. NSE's terms on scripted access were not found, so it makes one request per symbol per feed with a pause.

## The rules

- **Headlines are leads, not facts.** Open the story or the filing before telling the user something happened. Quote the source and link it. Never summarise a paywalled story you could not read.
- **Announcements beat headlines.** If an NSE announcement and a headline disagree, the announcement is what the company told the exchange.
- **Say what it touches.** Every item lists its tickers and tags: earnings, analyst, legal, deal, capital, people, risk, halt, regulatory, macro. Announcements marked `!` are results, board-meeting outcomes, resignations or appointments, acquisitions, schemes, insolvency or default, credit ratings, buybacks, bonus or split, insider or SAST filings, fund raising.
- **UPCOMING** lines are results or board meetings in the next 7 days. A results date inside the trade means an overnight gap can jump past any stop; say so before `/trader-in-entry`.
- **MOVING** marks a stock 3 % or more from yesterday's close (`--move-pct`). A move with no headline is worth saying out loud too.
- **No predictions.** Report what was published and how far the price is from yesterday's close.
- Keep headline, source, time and link only; do not republish article text.

## Steps

1. Run `python3 "${CLAUDE_SKILL_DIR}/news.py"`. Exit code 1 means nothing new. `--all` shows seen items, `--json` is machine readable, `--dry-run` leaves the state alone.
2. Read the items that matter: every `!` announcement, anything tagged earnings, halt, legal, regulatory or risk, every UPCOMING line and every MOVING ticker first.
3. Write a short brief per ticker: what happened, source and link, the move, and one line on why it matters to the setup.
4. If a story changes the picture, say so before `/trader-in-entry` and `/trader-in-exit`: results inside the trade, a board meeting, a fund raise. Never act on a headline alone.

Before the open, also worth a line from the other feeds this skill does not read yet: Nifty and India VIX (`nseindia.com/api/allIndices`), FII/DII provisional flows (`/api/fiidiiTradeReact`), the F&O ban list (`nsearchives.nseindia.com/content/fo/fo_secban.csv`), GIFT Nifty.

During the session: `/loop 15m /trader-in-news`, or a scheduled task each morning before 9:00 AM IST.

## Not done yet

- BSE announcements (BSE's API answered 403 from the test host).
- A time filter by trading session: `--hours 48` is clock hours, not sessions.

## What it never does

- Never invents or embellishes a story, a quote or a number.
- Never trades on news, and never tells the user to buy or sell because of a headline.

## Safety

Education and tooling, not financial advice and not SEBI-registered investment advice. This skill only reads and reports. Nothing places an order except `/trader-in-broker`, after `/trader-in-risk` passes and the user types an explicit yes for that order.
