# trader-skills-india

NSE (Indian market) versions of the `trader-*` day-trading skills for Claude Code: scanner, news, entry, exit, budget, risk, broker (Zerodha Kite), alerts, analyst (NSE XBRL results), insiders (bulk/block deals, SEBI PIT and SAST filings, FII/DII) and timemachine.

Each folder is a skill (`SKILL.md` plus a standard-library Python tool). Copy the folders into `~/.agents/skills/` (or `~/.claude/skills/`).

- Education and tooling, not financial advice and not SEBI-registered investment advice.
- Zerodha has no paper account: `"paper": true` is a dry run and nothing is sent to the broker.
- Calendar is 2026 only (add NSE's 2027 list when published). Tick size above Rs 1,000 (Rs 0.10) is assumed.
- Research and open items: `docs/research-report.md`.

## License

MIT, see `LICENSE`.
