---
name: tradingagents-bailian
description: Run TradingAgents from this workspace through run_bailian.py and return structured stock analysis for a ticker and date. Use when the user asks for a trading signal, stock analysis, buy/hold/sell view, or wants TradingAgents results from the local repository.
homepage: https://github.com/AceInAndroid/TradingAgents
metadata: {"openclaw":{"homepage":"https://github.com/AceInAndroid/TradingAgents"}}
---

# TradingAgents Bailian

Use this skill when the user wants analysis from the local `TradingAgents` repository in this workspace.

## Preconditions

- Repository root is two levels above this skill: `$(cd "{baseDir}/../.." && pwd)`.
- Prefer the existing virtualenv at `<repo>/.venv`.
- API keys must come from environment or local config. Never print secrets.
- Use `--json` for machine-readable output. Do not combine `--json` with `--debug`.

## Command

Run from the repository root:

```bash
source .venv/bin/activate && python run_bailian.py --json --preset fast --ticker NVDA --date 2024-05-10 --analysts market,news
```

Adjust:

- `--preset`: `balanced`, `fast`, `coder`, `glm`, `kimi`
- `--ticker`: exact ticker symbol
- `--date`: `YYYY-MM-DD`
- `--analysts`: comma-separated subset of `market,social,news,fundamentals`

## Output Handling

The command returns JSON with this shape:

- `ok`
- `tool`
- `input`
- `result.rating`
- `result.summary`
- `result.decision`
- `result.models`
- `result.reports`
- `result.artifacts.log_path`
- `error`
- `meta.elapsed_seconds`

If `ok` is `false`, surface `error.code` and `error.message` clearly.

If `ok` is `true`, summarize:

1. `result.rating`
2. `result.summary`
3. Any important points from `result.decision`
4. `result.artifacts.log_path` when the user may want the full log

## Guardrails

- Do not invent ratings or reports; rely on the JSON output.
- Do not expose `.env` contents or API keys.
- If `.venv` or `run_bailian.py` is missing, say the workspace is not prepared.
- If the user asks for a quick check, prefer `--preset fast` and fewer analysts.
- If the user asks for a fuller run, prefer `--preset balanced` with all analysts.
