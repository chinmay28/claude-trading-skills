#!/usr/bin/env bash
# Cron entrypoint for the morning-advisor pipeline (Raspberry Pi / Linux).
#
# Invoke from cron (08:00 ET, Mon-Fri); replace install path below for your box:  # noqa: absolute-path
#   0 8 * * 1-5 /home/pi/claude-trading-skills/scripts/morning_advisor_run.sh \  # noqa: absolute-path
#       >> /home/pi/claude-trading-skills/logs/morning_advisor.log 2>&1          # noqa: absolute-path
#
# Manual run:
#   bash scripts/morning_advisor_run.sh [--dry-run]
#
# Required environment (load via wrapper, see docs/setup-raspberry-pi.md):
#   FMP_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true
#   ANTHROPIC_API_KEY (optional; only if using Claude Agent SDK headless)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Ensure cron has access to user-installed binaries (uv, claude, python3.11).
export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

# Load secrets from the user's env file (chmod 600 recommended).
ENV_FILE="${MORNING_ADVISOR_ENV:-${HOME}/.config/claude-trading-skills/env}"
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
fi

mkdir -p "${PROJECT_ROOT}/logs"
TODAY="$(date -u +%Y-%m-%d)"
LOG_LINE_PREFIX="[$(date -Iseconds)]"

echo "${LOG_LINE_PREFIX} morning-advisor: starting (cwd=${PROJECT_ROOT}, date=${TODAY})"

# Required env vars
for var in FMP_API_KEY ALPACA_API_KEY ALPACA_SECRET_KEY; do
    if [[ -z "${!var:-}" ]]; then
        echo "${LOG_LINE_PREFIX} ERROR: ${var} not set" >&2
        exit 1
    fi
done

# Hard safety: this script is for paper trading only.
if [[ "${ALPACA_PAPER:-true}" != "true" ]]; then
    echo "${LOG_LINE_PREFIX} ERROR: ALPACA_PAPER must be 'true' for morning-advisor" >&2
    exit 1
fi

# Pre-flight: market-open check (Alpaca calendar; no FMP cost)
if ! python3 skills/morning-advisor/scripts/check_market_open.py; then
    echo "${LOG_LINE_PREFIX} morning-advisor: market closed; exiting cleanly"
    exit 0
fi

# Resolve Claude CLI (graceful error if missing)
if ! command -v claude >/dev/null 2>&1; then
    echo "${LOG_LINE_PREFIX} ERROR: 'claude' CLI not on PATH; install per docs/setup-raspberry-pi.md" >&2
    exit 1
fi

REPORT_DIR="${PROJECT_ROOT}/reports/morning_advisor/${TODAY}"
mkdir -p "${REPORT_DIR}"

# Headless invocation of the morning-advisor skill.
# `claude -p` runs a single non-interactive turn and exits.
PROMPT="/morning-advisor"
if [[ "${1:-}" == "--dry-run" ]]; then
    PROMPT="/morning-advisor --dry-run (no orders submitted)"
fi

echo "${LOG_LINE_PREFIX} morning-advisor: invoking claude -p"
claude -p "${PROMPT}" \
    --output-format text \
    >> "${REPORT_DIR}/claude_session.log" 2>&1

EXIT_CODE=$?
echo "${LOG_LINE_PREFIX} morning-advisor: completed (exit=${EXIT_CODE})"
exit "${EXIT_CODE}"
