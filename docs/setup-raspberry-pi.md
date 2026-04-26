# Setup: Morning Advisor on a Raspberry Pi

End-to-end setup for running the `morning-advisor` skill on an always-on Raspberry Pi (or any always-on Linux box). The pipeline runs at 08:00 ET each weekday, generates a daily report, and auto-executes the resulting trades on Alpaca paper.

> **Status:** Phase 1 — paper trading only. `ALPACA_PAPER` must be `true`. The cron wrapper aborts otherwise.

## Hardware

- Raspberry Pi 4 (4GB+) or Pi 5 — anything ARMv8 with 4GB RAM is sufficient
- microSD or SSD with ~16GB free
- Reliable power + Ethernet/Wi-Fi
- Time-synced via `systemd-timesyncd` (default on Raspberry Pi OS)

## 1. Base OS prep

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-pip cron

# Set timezone to America/New_York so cron times match market hours
sudo timedatectl set-timezone America/New_York
timedatectl   # verify
```

## 2. Install uv (Python project manager) and Claude Code CLI

```bash
# uv (fast pip + venv replacement; we use `uv run` to invoke project scripts)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Claude Code CLI
curl -fsSL https://claude.ai/install.sh | bash

# One-time browser auth (opens an auth URL — copy to a browser on another device)
claude login
```

Verify:
```bash
uv --version
claude --version
```

## 3. Clone and install the repository

```bash
mkdir -p ~/claude-trading-skills && cd ~/claude-trading-skills
git clone https://github.com/<your-fork>/claude-trading-skills.git .
uv sync     # installs dependencies from pyproject.toml
```

## 4. Get API keys

### Financial Modeling Prep (FMP) — free tier

1. Sign up: https://site.financialmodelingprep.com/developer/docs
2. Copy the API key from the dashboard
3. Free tier = 250 calls/day. The morning-advisor budgets ≤ 200/day.

### Alpaca paper trading — free

1. Sign up: https://alpaca.markets
2. Go to **Paper Trading → API Keys** → "Generate New Key"
3. Copy both `Key ID` and `Secret Key`. Keep `Paper` mode selected.

> Live trading is **not** supported by this script (it asserts `ALPACA_PAPER=true`).

### Anthropic API (optional)

Only needed if you want to run via the Claude Agent SDK headlessly instead of the `claude` CLI. The default cron path uses `claude -p` with browser auth, so you can skip this.

## 5. Store secrets

Create the env file (mode 600):

```bash
mkdir -p ~/.config/claude-trading-skills
cat > ~/.config/claude-trading-skills/env <<'EOF'
export FMP_API_KEY="paste-fmp-key-here"
export ALPACA_API_KEY="paste-alpaca-key-id-here"
export ALPACA_SECRET_KEY="paste-alpaca-secret-here"
export ALPACA_PAPER="true"
EOF
chmod 600 ~/.config/claude-trading-skills/env
```

The cron wrapper sources this file automatically. Override its path by exporting `MORNING_ADVISOR_ENV`.

## 6. Connect Alpaca MCP server

The `morning-advisor` skill uses Alpaca via the MCP server (same as `portfolio-manager`). Follow `skills/portfolio-manager/references/alpaca-mcp-setup.md`. Key step: add the MCP server to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "paste-here-or-leave-empty-to-inherit",
        "ALPACA_SECRET_KEY": "paste-here-or-leave-empty-to-inherit",
        "ALPACA_PAPER": "true"
      }
    }
  }
}
```

Verify the MCP connection inside Claude Code (interactive):
```bash
claude
> /mcp                   # should list 'alpaca' as connected
> use Alpaca to fetch my account info
```

## 7. Smoke-test the pipeline

```bash
cd ~/claude-trading-skills
source ~/.config/claude-trading-skills/env

# Test Alpaca connection (no trades)
python3 skills/portfolio-manager/scripts/check_alpaca_connection.py

# Test market-open check (exit 0 = open, 1 = closed, 2 = unreachable)
python3 skills/morning-advisor/scripts/check_market_open.py
echo "exit: $?"

# Test benchmark tracker (CRUD round-trip)
python3 scripts/benchmark_tracker.py --log-path /tmp/test_log.jsonl record-rec \
    --thesis-id smoke_test --ticker NVDA --instrument call \
    --entry-price 4.85 --entry-date "$(date +%F)" --source-skill smoke

python3 scripts/benchmark_tracker.py --log-path /tmp/test_log.jsonl summary
rm /tmp/test_log.jsonl

# Dry-run the orchestrator (no orders)
bash scripts/morning_advisor_run.sh --dry-run
```

Inspect `reports/morning_advisor/<today>/` for the dry-run output.

## 8. Schedule via cron

```bash
crontab -e
```

Add (substitute the install dir below for your box):  <!-- noqa: absolute-path -->
```
0 8 * * 1-5 /home/pi/claude-trading-skills/scripts/morning_advisor_run.sh >> /home/pi/claude-trading-skills/logs/morning_advisor.log 2>&1  # noqa: absolute-path
```

Adjust the path if you cloned elsewhere. The wrapper handles env loading, market-open gating, and Claude CLI invocation.

Verify cron is active:
```bash
sudo systemctl status cron
cat /etc/crontab     # should NOT contain your user entry; it's in `crontab -e`
```

## 9. Verify the first live (paper) run

The morning after scheduling:

```bash
tail -f ~/claude-trading-skills/logs/morning_advisor.log
ls ~/claude-trading-skills/reports/morning_advisor/
cat ~/claude-trading-skills/state/benchmark_log.jsonl | tail
```

Confirm in the Alpaca paper dashboard that any orders shown in `reports/morning_advisor/<date>/report.md` actually appear under **Activity → Orders**.

## 10. Log rotation (optional but recommended)

Add to `/etc/logrotate.d/morning-advisor` (replace path with your install dir):

```
/home/pi/claude-trading-skills/logs/morning_advisor.log {  # noqa: absolute-path
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `'claude' CLI not on PATH` (cron) | cron's PATH excludes `~/.local/bin` | The wrapper already adds `${HOME}/.local/bin`; ensure `claude` actually installed there. `which claude` |
| Cron didn't fire at 08:00 | Pi was off, or timezone wrong | `timedatectl` shows zone; `journalctl -u cron --since "08:00"` |
| `Authentication failed` on Alpaca | wrong paper/live mode | Confirm `ALPACA_PAPER=true` and keys are paper keys |
| `claude login` URL won't open on Pi | no GUI | run `claude login` once, copy the URL, paste in a browser on your laptop, complete auth, return to Pi |
| FMP rate-limited mid-run | another script burned the budget | `morning-advisor` will degrade gracefully; check `run_manifest.json` |
| MCP shows `alpaca: disconnected` | uvx not installed or wrong path | `which uvx` and reinstall via `pip install --user uv` |
| Orders rejected: `pattern day trader` | account triggered PDT | paper accounts get reset monthly; otherwise reduce frequency |

## Going to production (after the trial month)

After ~1 month of paper trading, when reviewing `state/benchmark_log.jsonl`:

1. Look at the `summary` JSON: cumulative alpha, by-skill breakdown, win rate
2. If results are positive and you've sanity-checked the trade decisions, decide whether to graduate
3. **Do not flip `ALPACA_PAPER` to `false` to enable live trading.** The wrapper hard-aborts in that mode for safety. To go live, fork the wrapper into a separate `morning_advisor_live.sh` with explicit guardrails (max-loss circuit breaker, manual approval queue, etc.) — that's a deliberate decision, not a config tweak.
