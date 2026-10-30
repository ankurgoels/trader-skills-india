#!/usr/bin/env python3
"""Who is buying, for trader-in-insiders: NSE's public disclosures of insider, large-holder and institutional flows.
Standard library only. India has no politician-trade disclosure like the US STOCK Act; these are the filings it does have.

    python3 flows.py deals [--symbol X]          # today's bulk and block deals (NSE csv)
    python3 flows.py fii                         # FII/FPI and DII provisional flows for the latest day
    python3 flows.py insiders RELIANCE           # SEBI PIT Reg 7 insider trades (promoters, directors, designated persons)
    python3 flows.py sast [--from 01-10-2026 --to 29-10-2026] [--symbol X]   # SAST Reg 29 holder disclosures
    python3 flows.py ... --json

Sources (all need a browser User-Agent; the api/ ones also a Referer):
  nsearchives.nseindia.com/content/equities/bulk.csv and block.csv
  www.nseindia.com/api/fiidiiTradeReact
  www.nseindia.com/api/corporates-pit?index=equities&symbol=X
  www.nseindia.com/api/corporate-sast-reg29?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY

Lags are real: a bulk or block deal prints the same evening, FII/DII numbers are provisional, a PIT filing comes up to
2 trading days after the trade (and the last test showed several days), a SAST filing within 2 working days.
Date-ranged PIT queries returned nothing for Jul-Oct 2026 in testing, so insiders is by symbol, newest first.
"No filings returned" never means "no insider buying". Exit code 0 when rows were printed, 1 when none.
"""

import argparse
import csv
import datetime
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
API = "https://www.nseindia.com/api/"
ARCH = "https://nsearchives.nseindia.com/content/equities/"
NOTE = "Disclosures of what others did, days late: not a signal to copy. Not financial advice."


class FlowError(Exception):
    pass


def get(url, referer=True, pause=0.3):
    time.sleep(pause)
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = "https://www.nseindia.com/"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FlowError("HTTP %d for %s" % (e.code, url.split("?")[0]))
    except (urllib.error.URLError, OSError) as e:
        raise FlowError("could not reach %s: %s" % (url.split("?")[0], getattr(e, "reason", e)))


def jget(url):
    try:
        return json.loads(get(url))
    except ValueError:
        raise FlowError("not JSON: " + url.split("?")[0])


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def parse_deals(text, kind):
    rows = []
    for r in csv.DictReader(io.StringIO(text.replace("\r", ""))):
        if (r.get("Date") or "").upper().startswith("NO RECORDS") or not r.get("Symbol"):
            continue
        q, px = num(r.get("Quantity Traded")), num(r.get("Trade Price / Wght. Avg. Price"))
        rows.append({"kind": kind, "date": r["Date"], "symbol": r["Symbol"], "client": r["Client Name"],
                     "side": r["Buy/Sell"].upper(), "qty": q, "price": px,
                     "value_cr": round(q * px / 1e7, 2) if q and px else None})
    return rows


def deals(symbol=None):
    rows = parse_deals(get(ARCH + "bulk.csv", referer=False), "bulk") + parse_deals(get(ARCH + "block.csv", referer=False), "block")
    if symbol:
        rows = [r for r in rows if r["symbol"].upper() == symbol.upper()]
    return sorted(rows, key=lambda r: -(r["value_cr"] or 0))


def fii():
    return [{"category": r["category"], "date": r["date"], "buy_cr": num(r["buyValue"]), "sell_cr": num(r["sellValue"]),
             "net_cr": num(r["netValue"])} for r in jget(API + "fiidiiTradeReact")]


def insiders(symbol, n=15):
    doc = jget(API + "corporates-pit?index=equities&symbol=" + urllib.parse.quote(symbol.upper()))
    rows = []
    for r in doc.get("data") or []:
        rows.append({"symbol": r.get("symbol"), "filed": r.get("date"), "trade_from": r.get("acqfromDt"),
                     "who": r.get("acqName"), "category": r.get("personCategory"), "type": r.get("tdpTransactionType"),
                     "mode": r.get("acqMode"), "shares": num(r.get("secAcq")), "value_rs": num(r.get("secVal")),
                     "held_before": num(r.get("befAcqSharesNo")), "held_after": num(r.get("afterAcqSharesNo")),
                     "security": r.get("secType")})
    key = lambda r: datetime.datetime.strptime(r["filed"][:11], "%d-%b-%Y") if r["filed"] else datetime.datetime.min
    return sorted(rows, key=key, reverse=True)[:n]


def sast(frm=None, to=None, symbol=None):
    to = to or datetime.date.today().strftime("%d-%m-%Y")
    frm = frm or (datetime.date.today() - datetime.timedelta(days=7)).strftime("%d-%m-%Y")
    url = API + "corporate-sast-reg29?index=equities&from_date=%s&to_date=%s" % (frm, to)
    if symbol:
        url += "&symbol=" + urllib.parse.quote(symbol.upper())
    return [{"symbol": r.get("symbol"), "company": r.get("company"), "filed": r.get("timestamp"), "who": r.get("acquirerName"),
             "type": r.get("acqSaleType"), "mode": r.get("acquisitionMode"), "shares": num(r.get("noOfShareAcq") or r.get("noOfShareSale")),
             "pct_before": num(r.get("totAcqShare")), "pct_after": num(r.get("totAftShare")), "promoter": r.get("promoterType") == "Y",
             "reg": r.get("regType")} for r in jget(url).get("data") or []]


def lines(cmd, rows):
    if not rows:
        return ["No filings returned (that is not the same as nothing happening)."]
    out = []
    for r in rows:
        if cmd == "deals":
            out.append("%-5s %-12s %-9s %-52.52s %12s sh @ %s = Rs %s cr" % (r["kind"], r["symbol"], r["side"], r["client"],
                       "{:,.0f}".format(r["qty"] or 0), r["price"], r["value_cr"]))
        elif cmd == "fii":
            out.append("%-8s %s  buy Rs %s cr, sell Rs %s cr, net %+.2f cr" % (r["category"], r["date"],
                       "{:,.0f}".format(r["buy_cr"]), "{:,.0f}".format(r["sell_cr"]), r["net_cr"]))
        elif cmd == "insiders":
            out.append("filed %s  %-9s %-28.28s (%s) %s %s sh, Rs %s, holds %s -> %s" % (r["filed"][:11], r["type"], r["who"], r["category"],
                       r["mode"], "{:,.0f}".format(r["shares"] or 0), "{:,.0f}".format(r["value_rs"] or 0),
                       "{:,.0f}".format(r["held_before"] or 0), "{:,.0f}".format(r["held_after"] or 0)))
        else:
            out.append("%s %-10s %-9s %-40.40s %s sh, %s%% -> %s%%%s" % (r["filed"], r["symbol"], r["type"], r["who"],
                       "{:,.0f}".format(r["shares"] or 0), r["pct_before"], r["pct_after"], "  [promoter]" if r["promoter"] else ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    for name in ("deals", "fii", "insiders", "sast"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        if name == "insiders":
            p.add_argument("symbol")
            p.add_argument("--n", type=int, default=15)
        if name in ("deals", "sast"):
            p.add_argument("--symbol")
        if name == "sast":
            p.add_argument("--from", dest="frm")
            p.add_argument("--to")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        rows = {"deals": lambda: deals(a.symbol), "fii": fii, "insiders": lambda: insiders(a.symbol, a.n),
                "sast": lambda: sast(a.frm, a.to, a.symbol)}[a.cmd]()
    except FlowError as e:
        print("flows.py: %s" % e, file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print("\n".join(lines(a.cmd, rows)))
        print(NOTE)
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
