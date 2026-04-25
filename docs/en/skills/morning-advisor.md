---
layout: default
title: "Morning Advisor"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/morning-advisor/
permalink: /en/skills/morning-advisor/
---

# Morning Advisor
{: .no_toc }

Run the daily pre-market trading routine — assess regime, manage open positions, generate 0–3 new long-call/long-put or stock/ETF ideas with sized entries, and auto-execute on Alpaca paper. Designed for cron execution at 8:00 ET on a Raspberry Pi. Holding horizon 1 week to 1 month, benchmark S&P 500. Trigger when user says "run morning advisor", "daily trade plan", "morning routine", or when invoked headlessly via `claude -p "/morning-advisor"`.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span> <span class="badge badge-api">Alpaca Required</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/morning-advisor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Daily orchestrator that produces one trading decision per market day: position management for open theses + 0–3 new long-only ideas (stock, ETF, long call, or long put) sized to risk and auto-executed on Alpaca paper. Runs unattended via cron; the report is the audit trail, Alpaca is the execution venue.

This skill composes existing skills rather than reimplementing them. It is the regime gate, the routing layer, and the execution layer — the analytical work happens in the downstream skills it calls.

---

## 2. When to Use

- Scheduled cron run at 08:00 ET, Mon–Fri (skips holidays via `check_market_open.py`)
- Manual invocation: "run morning advisor", "give me today's trade plan"
- Headless: `claude -p "/morning-advisor"`

---

## 3. Prerequisites

- **FMP API key** (free tier 250 calls/day) — `$FMP_API_KEY`
- **Alpaca paper keys** — `$ALPACA_API_KEY`, `$ALPACA_SECRET_KEY`, `$ALPACA_PAPER=true`
- **Alpaca MCP server** configured (see `portfolio-manager/references/alpaca-mcp-setup.md`)
- Existing state directories: `state/theses/` (trader-memory-core), `state/benchmark_log.jsonl` (auto-created)

---

## 4. Quick Start

```bash
# Smoke-test the market-open gate
python3 skills/morning-advisor/scripts/check_market_open.py

# Manual dry-run of the orchestrator (no orders)
bash scripts/morning_advisor_run.sh --dry-run

# Inspect rolling performance vs SPY
python3 scripts/benchmark_tracker.py summary --window 30d

# Manually log a recommendation (normally done by the skill)
python3 scripts/benchmark_tracker.py record-rec \
  --thesis-id th_x --ticker NVDA --instrument call \
  --entry-price 4.85 --entry-date 2026-04-27 \
  --source-skill vcp-screener
```

---

## 5. Workflow

### Step 0 — Pre-flight

1. Run `python3 skills/morning-advisor/scripts/check_market_open.py`. If exit code ≠ 0, write a one-line "MARKET CLOSED — skipping" report and stop.
2. Verify env: `FMP_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` all set. Abort with a clear error if any missing.
3. Initialize the run manifest at `reports/morning_advisor/<YYYY-MM-DD>/run_manifest.json` with `started_at`, empty `recommendations`, `executions`, `_fmp_calls_used: 0`.

### Step 1 — Regime gate

Determine market regime to route screener selection and gate new entries.

Read `references/regime_playbook.md` for the full decision matrix. Summary:

1. Run `macro-regime-detector` (no API cost) → regime label: `RISK_ON | NEUTRAL | RISK_OFF`
2. Run `market-breadth-analyzer` or `uptrend-analyzer` (no API cost, public CSV) → breadth score 0–100
3. Run `ftd-detector` and `market-top-detector` (no API cost) → confirmation flags
4. Combine into a single regime decision:
   - **RISK_ON** (breadth ≥ 60, no top signal) → enable breakout / momentum screeners + long calls
   - **NEUTRAL** (40 ≤ breadth < 60) → enable pullback / mean-reversion screeners + selective long calls or stock
   - **RISK_OFF** (breadth < 40 or top signal active) → manage existing only; new entries only as long puts on weak names, max 1
5. Write regime block to manifest.

### Step 2 — Position management (open theses)

Process every open position before considering new entries.

1. List open positions via Alpaca MCP `mcp__alpaca__get_positions`. Cross-reference with `trader-memory-core` ACTIVE theses.
2. For each open position, evaluate against the **original thesis** stored in `state/theses/<thesis_id>.yaml`:
   - **Stop-loss hit?** (price below `entry.stop`) → EXIT at market open
   - **Time stop hit?** (today ≥ `entry.time_stop_date`) → EXIT at market open
   - **Target hit?** (price ≥ `entry.target`) → EXIT or trail (default: full exit unless thesis explicitly supports trailing)
   - **Thesis invalidated?** (regime flip, fundamental break, or `references/regime_playbook.md` exit triggers) → EXIT
   - **Roll candidate?** Long option with ≤ 7 DTE and thesis intact and ≥ 30% remaining intrinsic value → ROLL to next expiry, same delta
   - **Otherwise** → HOLD
3. For each EXIT or ROLL, record the action in the manifest and update the thesis via `trader-memory-core`:
   ```bash
   python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
     terminate <thesis_id> CLOSED <reason> <exit_price> <today_date>
   ```
4. Submit closing orders via Alpaca MCP `mcp__alpaca__close_position` (stocks) or `mcp__alpaca__submit_order` (options). Wait for fill confirmation before proceeding to Step 3.
5. Append outcome to benchmark log:
   ```bash
   python3 scripts/benchmark_tracker.py record-outcome --thesis-id <id> --exit-price <p> --exit-date <YYYY-MM-DD>
   ```

### Step 3 — New idea generation (regime-conditional)

Only proceed if total open risk after Step 2 < 5% of equity. Otherwise note "open risk cap reached, no new entries" and skip to Step 6.

Pick **one** screener based on regime (Step 1). Read `references/regime_playbook.md` for full mapping.

| Regime | Primary screener | Secondary (if primary returns 0) |
|--------|------------------|----------------------------------|
| RISK_ON | `vcp-screener` or `breakout-trade-planner` | `earnings-trade-analyzer` |
| NEUTRAL | `dividend-growth-pullback-screener` | `pead-screener` |
| RISK_OFF | (no long calls/stock) — scan SPY/QQQ for put setups via `technical-analyst` workflow | none |

Cap the screener to ~30 tickers to stay within FMP budget. Note: the screener will execute its own FMP calls; track via the manifest's `_fmp_calls_used` counter.

If the screener returns no candidates, write "no candidates today" to manifest and skip to Step 6.

### Step 4 — Hypothesis + option selection (per candidate)

For up to top-3 candidates from Step 3:

1. Run `trade-hypothesis-ideator` to produce a structured hypothesis: setup type, catalyst, entry, stop, target, time horizon.
2. Pre-trade calendar check: query `economic-calendar-fetcher` and `earnings-calendar` for events within the holding window. If a high-impact event sits inside the window AND the thesis is not event-driven, **drop the candidate**.
3. Decide instrument via `references/option_selection.md`:
   - **Earnings catalyst inside window AND high IV percentile** → SKIP (long premium loses to vol crush)
   - **Strong directional thesis, IV percentile < 50, holding 1–4 weeks** → long option (delta 0.30–0.50, 30–45 DTE)
   - **Moderate thesis OR low liquidity options OR small account** → common shares
   - **Bearish thesis (RISK_OFF only, on weak SPY/QQQ/sector ETF)** → long put, same delta/DTE rules
4. Run `position-sizer` with `--risk-pct 1.0 --max-position-pct 10`. For options, size by max-loss = (premium × contracts × 100) ≤ 1% of equity.
5. Register the thesis with `trader-memory-core`:
   ```bash
   python3 skills/trader-memory-core/scripts/thesis_ingest.py \
     --source morning-advisor --input <candidate_json> --state-dir state/theses/
   ```
   Then transition IDEA → ENTRY_READY with `thesis_store.transition()`, attach the position-sizer output, set `entry.time_stop_date = today + 25 trading days`.

### Step 5 — Auto-execute on Alpaca paper

For each ENTRY_READY thesis from Step 4:

1. **Stocks/ETFs:** submit a market order at open via `mcp__alpaca__submit_order` (qty from sizer, side=buy, type=market, time_in_force=day). For long puts on weak indices, use the equivalent option order.
2. **Options:** submit a limit order at the mid of bid-ask via `mcp__alpaca__submit_order` (asset_class=option, side=buy_to_open, type=limit, time_in_force=day, limit_price=mid). If unfilled by 9:45 ET, cancel — do not chase.
3. On fill confirmation, transition the thesis ENTRY_READY → ACTIVE with actual fill price/date via `thesis_store.open_position()`.
4. Record the entry in the benchmark log:
   ```bash
   python3 scripts/benchmark_tracker.py record-rec --thesis-id <id> --entry-price <p> --entry-date <YYYY-MM-DD> --instrument <stock|etf|call|put>
   ```
5. If a fill fails or is rejected, mark the thesis INVALIDATED with reason, do not retry.

### Step 6 — Generate the daily report

Render `reports/morning_advisor/<YYYY-MM-DD>/report.md` from the manifest using `references/daily_report_template.md`. Required sections:

1. Header (date, regime, account equity, open risk %)
2. Open positions table with HOLD/EXIT/ROLL decisions and reasons
3. New ideas table (or "no new entries today" with reason)
4. Execution log (Alpaca order IDs, fills, rejections)
5. Benchmark snapshot (call `benchmark_tracker.py summary --window 30d`)
6. FMP budget used / remaining

Also write `report.json` with the same structured data for downstream tools.

### Step 7 — Cleanup

1. Compact the manifest, write final `completed_at` and `_fmp_calls_used`.
2. If FMP calls exceeded 200, log a WARN line.
3. Exit 0 on success, 1 on any unrecoverable error (missing keys, Alpaca down, schema validation failure).

---

## 6. Resources

**References:**

- `skills/morning-advisor/references/daily_report_template.md`
- `skills/morning-advisor/references/execution_protocol.md`
- `skills/morning-advisor/references/option_selection.md`
- `skills/morning-advisor/references/regime_playbook.md`

**Scripts:**

- `skills/morning-advisor/scripts/check_market_open.py`
