---
name: openclaw-tradingagents
description: Use the run_tradingagents plugin tool to run the local TradingAgents repository for a ticker and date, returning structured JSON analysis with rating, summary, and full decision text.
---

# OpenClaw TradingAgents

Use this skill when the user asks for:

- a stock analysis from the local TradingAgents repo
- a buy/hold/sell style signal
- a structured trading decision for a ticker on a specific date

## Tool

Call the optional plugin tool:

- `run_tradingagents`

## Parameters

- `ticker`: required
- `analysis_date`: optional, `YYYY-MM-DD`
- `preset`: optional, one of `balanced`, `fast`, `coder`, `glm`, `kimi`
- `analysts`: optional subset of `market`, `social`, `news`, `fundamentals`

## Defaults

- For quick checks, prefer `preset: "fast"` with `["market", "news"]`.
- For fuller analysis, prefer `preset: "balanced"` with all analysts.

## Output

The tool returns JSON text with:

- `ok`
- `result.rating`
- `result.summary`
- `result.decision`
- `result.reports`
- `result.artifacts.log_path`

If `ok` is `false`, surface `error.code` and `error.message` clearly.

Do not invent a rating or rewrite the JSON as if it came from somewhere else. Base the response on the tool output.
