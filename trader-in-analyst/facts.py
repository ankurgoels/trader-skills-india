#!/usr/bin/env python3
"""Earnings Analyst for trader-in-analyst: NSE quarterly results from the exchange's own filings. Standard library only.

    python3 facts.py RELIANCE                 # consolidated, last 5 quarters, each against the year before
    python3 facts.py RELIANCE TCS --standalone
    python3 facts.py RELIANCE --json

Reads, per symbol:
  https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=X&period=Quarterly
      the list of filed results (toDate, consolidated or not, audited, an "xbrl" link)
  the XBRL file behind each filing (nsearchives.nseindia.com/corporate/xbrl/INDAS_*.xml):
      RevenueFromOperations, Income, FinanceCosts, ProfitBeforeTax, TaxExpense, ProfitLossForPeriod,
      diluted EPS: context OneD is the quarter (FourD the year to date). The year-on-year compares with
      the filing four quarters earlier, so it fetches four more filings than it prints.
Amounts print in Rs crore (the XBRL is in rupees). Indian companies file a standalone fourth quarter, so
nothing is derived. Say when the newest filing is old: NSE's feed can lag a result that is already out.

--offline DIR reads DIR/results-<SYMBOL>.json and DIR/<xbrl file name>.
Exit code 0 when numbers were printed, 1 when not.
"""

import argparse
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
RESULTS = "https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=%s&period=Quarterly"
CRORE = 1e7
PAUSE = 0.3
STALE_DAYS = 150  # a quarter ends, results follow within 45 days: older than this is lagging
TAGS = {"revenue": ["RevenueFromOperations"], "income": ["Income"], "finance_costs": ["FinanceCosts"],
        "pbt": ["ProfitBeforeTax"], "tax": ["TaxExpense"],
        "net_profit": ["ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations"],
        "eps": ["DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"]}


class FactsError(Exception):
    pass


def get(url, offline=None, name=None):
    if offline:
        try:
            with open("%s/%s" % (offline, name or url.rsplit("/", 1)[-1]), "rb") as fh:
                return fh.read()
        except OSError as e:
            raise FactsError("offline: %s" % e)
    time.sleep(PAUSE)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise FactsError("HTTP %d for %s" % (e.code, url.split("?")[0]))
    except (urllib.error.URLError, OSError) as e:
        raise FactsError("could not reach %s: %s" % (url.split("?")[0], getattr(e, "reason", e)))


def parse_xbrl(data):
    """XBRL bytes -> {key: value} for the reporting quarter, in rupees (EPS in rupees a share)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise FactsError("XBRL is not valid XML: %s" % e)
    ctx, facts = {}, {}
    for el in root.iter():
        name = el.tag.rsplit("}", 1)[-1]
        if name == "context":
            s = e = None
            for c in el.iter():
                n = c.tag.rsplit("}", 1)[-1]
                if n == "startDate":
                    s = (c.text or "").strip()
                elif n == "endDate":
                    e = (c.text or "").strip()
            ctx[el.get("id")] = (s, e)
        elif el.get("contextRef") and (el.text or "").strip():
            facts.setdefault(name, []).append((el.get("contextRef"), el.text.strip()))
    # NSE Ind-AS files label contexts OneD (this quarter), ThreeD (same quarter last year), FourD (year to date)
    out = {"from": next((v for _, v in facts.get("DateOfStartOfReportingPeriod", [])), None),
           "to": next((v for _, v in facts.get("DateOfEndOfReportingPeriod", [])), None)}
    for key, names in TAGS.items():
        for n in names:
            for ref, suffix in (("OneD", ""), ("ThreeD", "_py")):
                vals = [v for c, v in facts.get(n, []) if c == ref]
                if vals:
                    try:
                        out[key + suffix] = float(vals[0])
                    except ValueError:
                        pass
            if key in out:
                break
    return out


def quarters(symbol, standalone=False, n=8, offline=None):
    """The newest n quarterly filings, newest first: [{to, audited, numbers}]."""
    try:
        rows = json.loads(get(RESULTS % urllib.parse.quote(symbol), offline, "results-%s.json" % symbol))
    except ValueError:
        raise FactsError("NSE's results list for %s is not JSON" % symbol)
    want = "Non-Consolidated" if standalone else "Consolidated"
    seen, picked = set(), []
    for r in sorted((r for r in rows if r.get("consolidated") == want and r.get("xbrl")),
                    key=lambda r: datetime.datetime.strptime(r["toDate"], "%d-%b-%Y"), reverse=True):
        if r["toDate"] not in seen:
            seen.add(r["toDate"])
            picked.append(r)
    if not picked:
        raise FactsError("no %s quarterly results filed for %s on NSE" % (want.lower(), symbol))
    out = []
    for r in picked[:n]:
        try:
            nums = parse_xbrl(get(r["xbrl"], offline))
        except FactsError as e:
            nums = {"error": str(e)}
        out.append({"to": datetime.datetime.strptime(r["toDate"], "%d-%b-%Y").date().isoformat(),
                    "audited": r.get("audited"), "filed": r.get("filingDate"), **nums})
    return out


def pct(a, b):
    return None if a is None or not b else (a / b - 1) * 100


def analyse(qs, today=None):
    """Adds yoy and margins to each quarter; returns (quarters, notes)."""
    today = today or datetime.date.today()
    by_end = {q["to"]: q for q in qs}
    for q in qs:
        d = datetime.date.fromisoformat(q["to"])
        prev = next((p for e, p in by_end.items() if abs((datetime.date.fromisoformat(e) - d).days + 365) <= 10), {})
        q["yoy"] = {k: pct(q.get(k), prev.get(k, q.get(k + "_py"))) for k in ("revenue", "pbt", "net_profit", "eps")}
        q["pbt_margin"] = None if not q.get("revenue") or q.get("pbt") is None else q["pbt"] / q["revenue"] * 100
        q["net_margin"] = None if not q.get("revenue") or q.get("net_profit") is None else q["net_profit"] / q["revenue"] * 100
    notes = []
    newest = datetime.date.fromisoformat(qs[0]["to"])
    if (today - newest).days > STALE_DAYS:
        notes.append("The newest filing NSE returned is for the quarter ended %s, %d days ago: results since then "
                     "are missing from this feed. Check the company's announcements." % (newest, (today - newest).days))
    for q in qs[:2]:
        y = q["yoy"]
        if y.get("eps") is not None and y.get("net_profit") is not None and abs(y["eps"] - y["net_profit"]) > 25:
            notes.append("%s: EPS moved %+.0f%% but net profit %+.0f%%. A bonus issue or split changes the share count: "
                         "compare net profit, not EPS, unless the filing restates it." % (q["to"], y["eps"], y["net_profit"]))
    return qs, notes


def cr(v):
    return "n/a" if v is None else "{:,.0f}".format(v / CRORE)


def p(v):
    return "n/a" if v is None else "%+.1f%%" % v


def render(symbol, qs, notes, standalone):
    out = ["%s, %s quarterly results from NSE filings (Rs crore):" % (symbol, "standalone" if standalone else "consolidated")]
    out.append("%-12s %10s %8s %10s %8s %7s %9s %8s" % ("quarter end", "revenue", "yoy", "net profit", "yoy", "net %", "dil. EPS", "yoy"))
    for q in qs:
        if "error" in q:
            out.append("%-12s %s" % (q["to"], q["error"]))
            continue
        y = q["yoy"]
        out.append("%-12s %10s %8s %10s %8s %7s %9s %8s" % (
            q["to"], cr(q.get("revenue")), p(y.get("revenue")), cr(q.get("net_profit")), p(y.get("net_profit")),
            "n/a" if q["net_margin"] is None else "%.1f" % q["net_margin"],
            "n/a" if q.get("eps") is None else "%.2f" % q["eps"], p(y.get("eps"))))
    out += ["note: " + n for n in notes]
    out.append("Reported numbers, not a forecast. Net profit can include one-offs (exceptional items, "
               "tax): read the filing before calling it growth. Not financial advice.")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--standalone", action="store_true")
    ap.add_argument("--quarters", type=int, default=5)
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--today", help="YYYY-MM-DD, for reproducible runs")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    today = datetime.date.fromisoformat(a.today) if a.today else None
    docs, code = [], 1
    for sym in [s.upper() for s in a.symbols]:
        try:
            qs, notes = analyse(quarters(sym, a.standalone, a.quarters + 4, a.offline), today)
            qs = qs[:a.quarters]
        except FactsError as e:
            print("facts.py: %s: %s" % (sym, e), file=sys.stderr)
            continue
        code = 0
        docs.append({"symbol": sym, "quarters": qs, "notes": notes})
        if not a.json:
            sys.stdout.write(render(sym, qs, notes, a.standalone))
    if a.json:
        print(json.dumps(docs, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
