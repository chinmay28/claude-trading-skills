# Daily Report Template

Template for `reports/morning_advisor/<YYYY-MM-DD>/report.md`. Render from `run_manifest.json`.

```markdown
# Morning Advisor — {date}

**Regime:** {regime_label}  ·  **Breadth:** {breadth_score}/100  ·  **Top signal:** {top_signal_active}
**Account equity:** ${equity:,.0f}  ·  **Cash:** ${cash:,.0f}  ·  **Open risk:** {open_risk_pct:.2f}%

---

## Open Positions ({open_count})

| Ticker | Instrument | Entry | Current | P&L | Decision | Reason |
|--------|-----------|-------|---------|-----|----------|--------|
| {ticker} | {stock|call|put} {strike} {expiry} | ${entry_price} | ${current_price} | {pnl_pct:+.1f}% | **{HOLD|EXIT|ROLL}** | {reason} |
| ... |

## New Ideas ({new_count})

{# if new_count == 0:}
**No new entries today.** Reason: {no_entry_reason}
{# else:}

### {N}. {TICKER} — {LONG CALL | LONG PUT | STOCK | ETF}

- **Setup:** {setup_type} ({source_skill})
- **Thesis:** {thesis_one_liner}
- **Catalyst:** {catalyst}
- **Entry:** ${entry_price}  ·  **Stop:** ${stop_price}  ·  **Target:** ${target_price}  ·  **Time stop:** {time_stop_date}
- {# if option:}**Strike:** ${strike}  ·  **Expiry:** {expiry} ({dte} DTE)  ·  **Delta:** {delta}  ·  **IV pct:** {iv_pct}{# endif}
- **Sizing:** {qty} {shares|contracts}  ·  **Risk:** ${risk_dollars} ({risk_pct:.2f}% of equity)
- **Source:** {source_skill}  (rolling 30d hit rate: {hit_rate}%, alpha: {alpha:+.1f}%)
{# endfor:}

## Execution Log

| Time | Ticker | Side | Qty | Type | Limit/Mkt | Order ID | Status |
|------|--------|------|-----|------|-----------|----------|--------|
| {ts} | {ticker} | {buy|sell|buy_to_open|sell_to_close} | {qty} | {market|limit} | {price} | {order_id} | {filled|partial|canceled|rejected} |
| ... |

## Benchmark Snapshot (rolling 30 days)

- Trades closed: {n_closed}
- Win rate: {win_rate}%
- Average return per trade: {avg_return:+.2f}%
- **Cumulative alpha vs SPY: {cum_alpha:+.2f}%**
- Best skill source by alpha: {best_skill} ({best_skill_alpha:+.1f}%)

## Run Telemetry

- FMP calls used: {fmp_calls}/250 (budget 200)
- Started: {started_at} ET
- Completed: {completed_at} ET
- Errors: {error_count}
```

## Rendering Notes

- Use 24-hour ET timestamps throughout.
- Format prices to 2 decimals; percentages to 1 decimal except open-risk (2 decimals).
- If a section has no data (e.g., zero open positions), render the heading and "(none)".
- Do not include disclaimers in the daily report — they belong in the SKILL.md and the Pi setup doc.
- The report.json mirrors this structure as nested objects with the same keys; use snake_case throughout.

## Example

```markdown
# Morning Advisor — 2026-04-27

**Regime:** RISK_ON  ·  **Breadth:** 64/100  ·  **Top signal:** false
**Account equity:** $100,000  ·  **Cash:** $87,400  ·  **Open risk:** 2.30%

---

## Open Positions (2)

| Ticker | Instrument | Entry | Current | P&L | Decision | Reason |
|--------|-----------|-------|---------|-----|----------|--------|
| AAPL | call 180 2026-06-19 | $4.20 | $4.85 | +15.5% | **HOLD** | thesis intact, 41 DTE remaining |
| XLE | stock | $82.10 | $79.90 | -2.7% | **HOLD** | stop $78.50 unbroken, time stop 2026-05-19 |

## New Ideas (1)

### 1. NVDA — LONG CALL

- **Setup:** vcp_breakout (vcp-screener)
- **Thesis:** 6-week volatility contraction; pivot $112.40 cleared on 1.8× volume
- **Catalyst:** earnings 2026-05-22 (outside window — no event risk)
- **Entry:** $112.50  ·  **Stop:** $108.00  ·  **Target:** $122.00  ·  **Time stop:** 2026-05-30
- **Strike:** $115  ·  **Expiry:** 2026-05-30 (33 DTE)  ·  **Delta:** 0.42  ·  **IV pct:** 38
- **Sizing:** 2 contracts  ·  **Risk:** $970 (0.97% of equity)
- **Source:** vcp-screener (rolling 30d hit rate: 58%, alpha: +4.2%)

## Execution Log

| Time | Ticker | Side | Qty | Type | Limit/Mkt | Order ID | Status |
|------|--------|------|-----|------|-----------|----------|--------|
| 09:30:14 | NVDA 250530C115 | buy_to_open | 2 | limit | 4.85 | f3a91... | filled |

## Benchmark Snapshot (rolling 30 days)

- Trades closed: 8
- Win rate: 62%
- Average return per trade: +3.4%
- **Cumulative alpha vs SPY: +5.8%**
- Best skill source by alpha: vcp-screener (+4.2%)

## Run Telemetry

- FMP calls used: 142/250 (budget 200)
- Started: 08:00:03 ET
- Completed: 08:02:41 ET
- Errors: 0
```
