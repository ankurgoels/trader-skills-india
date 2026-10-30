#!/usr/bin/env python3
"""News Monitor for trader-in-news: what is new on the NSE stocks you watch. Standard library only.

    python3 news.py                              # watchlist + plan + portfolio
    python3 news.py --tickers RELIANCE TCS --hours 12
    python3 news.py --no-nse --json

Reads, for every ticker:
  - Google News RSS for the symbol (English, India edition):
    https://news.google.com/rss/search?q=<SYMBOL>+NSE+when:2d&hl=en-IN&gl=IN&ceid=IN:en
  - NSE corporate announcements (SEBI LODR disclosures: results, board-meeting
    outcomes, resignations, acquisitions, insider and SAST filings, credit ratings):
    https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=<SYMBOL>
  - NSE's event calendar for the next 7 days (results dates, board meetings, dividends):
    https://www.nseindia.com/api/event-calendar?symbol=<SYMBOL>
  - Yahoo's chart endpoint for the last price against yesterday's close (SYMBOL.NS):
    https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS?range=1d&interval=5m

Times print in IST. State: trader/state/news.json remembers what was shown (30 days).
--offline DIR reads gnews-<SYMBOL>.xml, nse-<SYMBOL>.json, events-<SYMBOL>.json and chart-<SYMBOL>.json.
Headlines are leads, not facts. Exit code 0 when something new was shown, 1 when not.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

GNEWS = "https://news.google.com/rss/search?q=%s+NSE+when:2d&hl=en-IN&gl=IN&ceid=IN:en"
CHART = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
NSE_ANN = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=%s"
NSE_EVENTS = "https://www.nseindia.com/api/event-calendar?symbol=%s"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KEEP_DAYS = 30
MOVE_PCT = 3.0  # a stock this far from yesterday's close is flagged as moving
EVENT_DAYS = 7  # upcoming results / board meetings this far ahead
IST = _dt.timedelta(hours=5, minutes=30)

# NSE announcement categories (the "desc" field) that can gap a stock
IMPORTANT_DESC = re.compile(
    r"result|outcome of board|resignation|appointment|acquisition|amalgamation|scheme|demerger|"
    r"bankruptcy|insolvency|default|credit rating|fraud|trading window|investor presentation|"
    r"insider|sast|takeover|buyback|bonus|split|dividend|fund raising|preferential|qip", re.I)
KEYWORDS = [
    ("earnings", r"\bearnings\b|\bresults\b|\bEPS\b|\bguidance\b|\bforecast\b"),
    ("analyst", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|price target|\boutperform\b|\bunderperform\b"),
    ("legal", r"\blawsuit\b|\bsued\b|\bprobe\b|\binvestigation\b|\bSEBI\b|\bNCLT\b|\bED raid|\bantitrust\b|\bjudge\b|\bcourt\b"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bbuyout\b|\btakeover\b|\bdeal\b"),
    ("capital", r"\bdividend\b|\bbuyback\b|\bbonus\b|\bstock split\b|\brights issue\b|\bQIP\b|\bIPO\b|\boffering\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bresign|\bsteps down\b|\bappoint"),
    ("risk", r"\brecall\b|\bbankrupt|\bdefault\b|\bdelist|\bhack|\bbreach\b|\boutage\b"),
    ("halt", r"\bhalt(?:s|ed)?\b|\btrading (?:pause|suspen)"),
    ("regulatory", r"\bFDA\b|\bapproval\b|\bapproves\b|\bclinical\b|\bSEBI\b|\bRBI\b|\bCCI\b|\bNCLT\b"),
    ("macro", r"\bRBI\b|\brepo rate\b|\bMPC\b|\bCPI\b|\binflation\b|\bNifty\b|\bSensex\b|\bFII\b|\bFPI\b|\btariffs?\b|\bGIFT Nifty\b"),
]


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

def to_ist(utc):
    """Aware or naive UTC -> naive IST wall-clock time (UTC+5:30, no daylight saving)."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc)
    return utc.replace(tzinfo=None) + IST


# ---------------------------------------------------------------- inputs

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{ticker: name or None}: the scanner's hits, the planned trade and your holdings."""
    out = {}
    wl = load_json(watchlist) or {}
    for h in wl.get("hits", []):
        sym = h.get("symbol") or h.get("ticker")
        if sym:
            out[sym.upper()] = h.get("name")
    pl = load_json(plan) or {}
    if pl.get("symbol"):
        out.setdefault(pl["symbol"].upper(), pl.get("name"))
    pf = load_json(portfolio) or {}
    for p in pf.get("positions", []):
        sym = p.get("ticker") or p.get("symbol")
        if sym:
            out[sym.upper()] = p.get("name") or out.get(sym.upper())
    return out


# ---------------------------------------------------------------- fetching

class Fetcher(object):
    def __init__(self, offline=None, pause=0.15):
        self.offline = offline
        self.pause = pause
        self._last = 0.0

    def get(self, url, name, nse=False):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        headers = {"User-Agent": BROWSER_UA, "Accept-Encoding": "gzip"}
        if nse:
            headers["Referer"] = "https://www.nseindia.com/"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("HTTP %s for %s" % (exc.code, url.split("?")[0]))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach %s: %s" % (url.split("?")[0], exc.reason))


def yahoo_symbol(ticker):
    return urllib.parse.quote(ticker.upper() + ".NS")


# ---------------------------------------------------------------- parsing

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_time(value):
    """RFC 822 (RSS) or ISO 8601 (Atom) -> aware UTC datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def parse_rss(data, ticker):
    """Google News RSS -> items."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("RSS for %s is not valid XML: %s" % (ticker, exc))
    out = []
    for it in root.iter("item"):
        title = _text(it, "title")
        link = _text(it, "link")
        guid = _text(it, "guid") or link
        out.append({"id": "rss:" + guid, "source": "Google News", "kind": "headline",
                    "ticker": ticker, "title": title, "summary": _text(it, "description"),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def parse_ist(text):
    """'29-Oct-2026 08:55:40' (IST) -> aware UTC datetime, or None."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return (_dt.datetime.strptime(text.strip(), fmt) - IST).replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            pass
    return None


def parse_nse_announcements(data, ticker):
    """NSE corporate-announcements JSON -> items. The seq_id is the key we remember."""
    try:
        rows = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except ValueError:
        raise NewsError("NSE announcements for %s are not valid JSON" % ticker)
    if not isinstance(rows, list):
        raise NewsError("NSE announcements for %s are not the shape this tool knows" % ticker)
    out = []
    for r in rows:
        desc = (r.get("desc") or "").strip()
        text = " ".join((r.get("attchmntText") or "").split())
        out.append({"id": "nse:" + str(r.get("seq_id") or r.get("dt")), "source": "NSE", "kind": "filing",
                    "form": desc, "ticker": ticker, "title": "%s: %s" % (desc or "Announcement", text[:200]),
                    "summary": text, "items": [], "important": bool(IMPORTANT_DESC.search(desc + " " + text[:120])),
                    "link": r.get("attchmntFile") or "", "time": parse_ist(r.get("an_dt") or "")})
    return out


def parse_events(data, ticker, today, days=EVENT_DAYS):
    """NSE event-calendar JSON -> [{"ticker","purpose","date","desc"}] from today to today+days (IST dates)."""
    try:
        rows = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except ValueError:
        raise NewsError("NSE event calendar for %s is not valid JSON" % ticker)
    out = []
    for r in rows if isinstance(rows, list) else []:
        try:
            d = _dt.datetime.strptime((r.get("date") or "").strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        if today <= d <= today + _dt.timedelta(days=days):
            out.append({"ticker": ticker, "purpose": (r.get("purpose") or "").strip(), "date": d.isoformat(),
                        "desc": " ".join((r.get("bm_desc") or "").split())[:160]})
    return sorted(out, key=lambda e: e["date"])


def parse_chart(data, ticker):
    """Yahoo chart JSON -> {"ticker", "price", "prev_close", "pct", "time"} or raise."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        meta = doc["chart"]["result"][0]["meta"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise NewsError("chart for %s is not usable" % ticker)
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        raise NewsError("chart for %s has no price" % ticker)
    when = meta.get("regularMarketTime")
    return {"ticker": ticker, "price": round(float(price), 2), "prev_close": round(float(prev), 2),
            "pct": round((float(price) / float(prev) - 1) * 100, 2),
            "time": _dt.datetime.fromtimestamp(when, _dt.timezone.utc) if when else None}


def collect_moves(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        name = "chart-%s.json" % t
        try:
            try:
                data = fetcher.get(CHART % ("query2", yahoo_symbol(t)), name)
            except NewsError as exc:
                if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
                    raise
                data = fetcher.get(CHART % ("query1", yahoo_symbol(t)), name)
            out.append(parse_chart(data, t))
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("price for %s: %s" % (t, exc))
    return out


def mention_patterns(watch):
    pats = {}
    for t, name in watch.items():
        alts = [r"\(%s\)" % re.escape(t), r"\$%s\b" % re.escape(t),
                r"\b(?:NSE|BSE)\s*:\s*%s\b" % re.escape(t)]
        if name and len(name) >= 4:
            alts.append(r"\b%s\b" % re.escape(name).replace(r"\ ", r"[\s-]"))
        pats[t] = re.compile("|".join(alts))
    return pats


def tag(items, watch):
    """Which of your tickers each item touches, and why it matters."""
    pats = mention_patterns(watch)
    for it in items:
        hay = "%s %s" % (it["title"], it.get("summary") or "")
        touches = {it["ticker"]} if it["ticker"] in watch else set()
        for t, rx in pats.items():
            if rx.search(hay):
                touches.add(t)
        it["touches"] = sorted(touches)
        it["tags"] = [label for label, rx in KEYWORDS if re.search(rx, hay, re.I)]
        if it["kind"] == "filing" and re.search(r"result", it.get("form", ""), re.I) and "earnings" not in it["tags"]:
            it["tags"].insert(0, "earnings")
    return items


def dedupe(items):
    """One item per story: same id, or same link, or same title the same day."""
    seen, out = {}, []
    for it in items:
        keys = [it["id"], it["link"],
                "%s|%s" % (re.sub(r"\W+", " ", it["title"].lower()).strip(),
                           it["time"].date() if it["time"] else "")]
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit is not None:
            for t in it.get("touches", []):
                if t not in hit["touches"]:
                    hit["touches"].append(t)
            hit["touches"].sort()
            continue
        for k in keys:
            if k:
                seen[k] = it
        out.append(it)
    return out


def fingerprint(it):
    return hashlib.sha1(it["id"].encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- the check

def collect(fetcher, watch, state, nse=True, errors=None):
    errors = [] if errors is None else errors
    items = []
    for t in sorted(watch):
        try:
            items += parse_rss(fetcher.get(GNEWS % urllib.parse.quote_plus(t), "gnews-%s.xml" % t), t)
        except NewsError as exc:
            errors.append("headlines for %s: %s" % (t, exc))
        if nse:
            try:
                items += parse_nse_announcements(
                    fetcher.get(NSE_ANN % urllib.parse.quote(t), "nse-%s.json" % t, nse=True), t)
            except NewsError as exc:
                errors.append("NSE announcements for %s: %s" % (t, exc))
    return items


def collect_events(fetcher, watch, today, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        try:
            out += parse_events(fetcher.get(NSE_EVENTS % urllib.parse.quote(t), "events-%s.json" % t, nse=True),
                                t, today)
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("NSE events for %s: %s" % (t, exc))
    return out


def select(items, state, now, hours=48, show_all=False):
    """Items within the window; only unseen ones unless show_all."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)  # a pinned --now: nothing from after it
    out = []
    for it in items:
        if it["time"] is not None and (it["time"] < cutoff or it["time"] > ahead):
            continue
        fp = fingerprint(it)
        it["new"] = fp not in seen
        if it["new"] or show_all:
            out.append(it)
    out.sort(key=lambda i: (i["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for it in items:
        seen.setdefault(fingerprint(it), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    state["last_check"] = stamp


def render_moves(moves, move_pct=MOVE_PCT):
    out = []
    for m in moves:
        flag = "MOVING" if abs(m["pct"]) >= move_pct else ""
        when = (" at %s IST" % to_ist(m["time"]).strftime("%H:%M")) if m.get("time") else ""
        out.append("%-6s %s %+.2f%% vs yesterday's close %s%s  %s" % (
            m["ticker"], "{:,.2f}".format(m["price"]), m["pct"], "{:,.2f}".format(m["prev_close"]),
            when, flag))
    return out


def render(items, errors, now, moves=None, move_pct=MOVE_PCT, events=None):
    out = render_moves(moves or [], move_pct)
    for e in events or []:
        out.append("UPCOMING %s  %-11s %s%s" % (e["date"], e["ticker"], e["purpose"] or "event",
                                              (" - " + e["desc"]) if e["desc"] else ""))
    if out:
        out.append("")
    if not items:
        out.append("Nothing new.")
    for it in items:
        when = to_ist(it["time"]).strftime("%Y-%m-%d %H:%M IST") if it["time"] else "time unknown"
        mark = "!" if it.get("important") else " "
        who = ",".join(it["touches"]) or it["ticker"]
        out.append("%s %s  %-11s %-13s %s" % (mark, when, who, it["source"], it["title"]))
        extra = []
        if it["tags"]:
            extra.append("tags: " + ", ".join(it["tags"]))
        extra.append(it["link"])
        out.append("      " + "  ".join(extra))
    for e in errors:
        out.append("note: %s" % e)
    out.append("Checked %s. Headlines are leads, not facts; open the story before acting. "
               "Not financial advice or SEBI-registered investment advice." % to_ist(now).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(out) + "\n"


def _json_ready(items):
    out = []
    for it in items:
        d = dict(it)
        d["time"] = it["time"].isoformat() if it["time"] else None
        out.append(d)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*", help="default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore items older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--no-nse", action="store_true", help="skip NSE announcements and the event calendar")
    ap.add_argument("--no-moves", action="store_true", help="skip the price line per ticker")
    ap.add_argument("--move-pct", type=float, default=MOVE_PCT, help="flag a move this big (percent)")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--now", help="ISO time, for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.tickers:
        watch = {t.upper(): None for t in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({t: known[t] for t in watch if known.get(t)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
    if not watch:
        print("news: no tickers. Pass --tickers, or run /trader-in-scanner first (it writes "
              "trader/watchlist.json).", file=sys.stderr)
        return 2
    now = parse_time(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    state = load_json(args.state) or {}
    errors = []
    fetcher = Fetcher(offline=args.offline)
    items = collect(fetcher, watch, state, nse=not args.no_nse, errors=errors)
    items = dedupe(tag(items, watch))
    shown = select(items, state, now, hours=args.hours, show_all=args.all)
    events = [] if args.no_nse else collect_events(fetcher, watch, to_ist(now).date(), errors)
    moves = [] if args.no_moves else collect_moves(fetcher, watch, errors)
    if args.json:
        mv = [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                   moving=abs(m["pct"]) >= args.move_pct) for m in moves]
        print(json.dumps({"checked": now.isoformat(), "moves": mv, "events": events, "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now, moves, args.move_pct, events))
    if not args.dry_run:
        remember(items, state, now)
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(i["new"] for i in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
