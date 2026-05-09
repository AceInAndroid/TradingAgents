import argparse
import json
import os
import re
import time
from typing import Dict

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BAILIAN_BASE_URL = "https://coding.dashscope.aliyuncs.com/v1"

MODEL_PRESETS: Dict[str, Dict[str, str]] = {
    "balanced": {
        "quick": "qwen3.5-plus",
        "deep": "qwen3-max-2026-01-23",
        "description": "Default trading preset with fast quick-think and stronger deep-think.",
    },
    "fast": {
        "quick": "qwen3.5-plus",
        "deep": "qwen3.5-plus",
        "description": "Lower latency preset for quick iterations and smoke tests.",
    },
    "coder": {
        "quick": "qwen3-coder-plus",
        "deep": "qwen3-coder-next",
        "description": "Useful when you want coding-oriented reasoning from Bailian models.",
    },
    "glm": {
        "quick": "glm-4.7",
        "deep": "glm-5",
        "description": "Alternative GLM preset with smaller context and balanced latency.",
    },
    "kimi": {
        "quick": "kimi-k2.5",
        "deep": "kimi-k2.5",
        "description": "Moonshot preset when you want one model for both passes.",
    },
}

TOOL_NAME = "run_tradingagents"
JD_OPENAI_BASE_URL_FRAGMENT = "modelservice.jdcloud.com/coding/openai/v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TradingAgents with Bailian OpenAI-compatible models."
    )
    parser.add_argument(
        "--preset",
        choices=sorted(MODEL_PRESETS),
        default=os.getenv("TRADINGAGENTS_MODEL_PRESET", "balanced"),
        help="Model preset to use.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "graph", "shallow"],
        default=os.getenv("TRADINGAGENTS_RUN_MODE", "auto"),
        help="Execution mode. auto prefers shallow research on constrained providers.",
    )
    parser.add_argument("--ticker", default=os.getenv("TRADINGAGENTS_TICKER", "NVDA"))
    parser.add_argument(
        "--date",
        dest="analysis_date",
        default=os.getenv("TRADINGAGENTS_ANALYSIS_DATE", "2024-05-10"),
        help="Analysis date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--analysts",
        default=os.getenv(
            "TRADINGAGENTS_ANALYSTS", "market,social,news,fundamentals"
        ),
        help="Comma-separated analysts list.",
    )
    parser.add_argument(
        "--quick-model",
        default=None,
        help="Override quick-think model.",
    )
    parser.add_argument(
        "--deep-model",
        default=None,
        help="Override deep-think model.",
    )
    parser.add_argument(
        "--debate-rounds",
        type=int,
        default=int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")),
    )
    parser.add_argument(
        "--risk-rounds",
        type=int,
        default=int(os.getenv("TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS", "1")),
    )
    parser.add_argument(
        "--recur-limit",
        type=int,
        default=int(os.getenv("TRADINGAGENTS_MAX_RECUR_LIMIT", "30")),
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=float(os.getenv("TRADINGAGENTS_LLM_TIMEOUT_SECONDS", "180")),
        help="LLM request timeout in seconds.",
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=int(os.getenv("TRADINGAGENTS_LLM_MAX_RETRIES", "1")),
        help="Maximum LLM retry attempts.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=float(os.getenv("TRADINGAGENTS_HTTP_TIMEOUT_SECONDS", "45")),
        help="Socket-level timeout for external HTTP requests in seconds.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("TRADINGAGENTS_DEBUG", "false").lower()
        in {"1", "true", "yes", "on"},
        help="Enable debug streaming output.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print resolved configuration and exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON result for tool integration.",
    )
    return parser.parse_args()


def _resolve_api_env() -> None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BAILIAN_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing API key. Set OPENAI_API_KEY or BAILIAN_API_KEY in .env."
        )

    os.environ["OPENAI_API_KEY"] = api_key
    os.environ.setdefault(
        "OPENAI_BASE_URL",
        os.getenv("BAILIAN_BASE_URL", DEFAULT_BAILIAN_BASE_URL),
    )
    os.environ.setdefault("TRADINGAGENTS_LLM_PROVIDER", "openai")


def _is_jd_openai_base_url(base_url: str) -> bool:
    return JD_OPENAI_BASE_URL_FRAGMENT in str(base_url or "").lower()


def _resolve_model_profile(args: argparse.Namespace) -> Dict[str, str]:
    base_url = os.environ["OPENAI_BASE_URL"]
    preset = MODEL_PRESETS[args.preset]
    quick_model = args.quick_model or preset["quick"]
    deep_model = args.deep_model or preset["deep"]

    # JD coding/openai endpoint currently only accepts the exact `GLM-5`
    # model id in this account context. Avoid unsupported qwen/glm aliases.
    if _is_jd_openai_base_url(base_url):
        quick_model = args.quick_model or "GLM-5"
        deep_model = args.deep_model or "GLM-5"

    return {
        "base_url": base_url,
        "quick_model": quick_model,
        "deep_model": deep_model,
    }


def _apply_runtime_env(args: argparse.Namespace) -> Dict[str, str]:
    profile = _resolve_model_profile(args)
    quick_model = profile["quick_model"]
    deep_model = profile["deep_model"]

    llm_timeout = args.llm_timeout
    llm_max_retries = args.llm_max_retries
    http_timeout = args.http_timeout
    debate_rounds = args.debate_rounds
    risk_rounds = args.risk_rounds
    recur_limit = args.recur_limit

    # Use a more conservative profile on JD GLM to avoid repeated provider
    # failures and token-per-minute spikes from the full TradingAgents graph.
    if _is_jd_openai_base_url(profile["base_url"]):
        llm_timeout = min(llm_timeout, 60.0)
        llm_max_retries = min(llm_max_retries, 0)
        http_timeout = min(http_timeout, 15.0)
        debate_rounds = min(debate_rounds, 1)
        risk_rounds = min(risk_rounds, 1)
        recur_limit = min(recur_limit, 12)

    effective = {
        "provider": "openai",
        "base_url": profile["base_url"],
        "preset": args.preset,
        "mode": args.mode,
        "quick_model": quick_model,
        "deep_model": deep_model,
        "ticker": args.ticker,
        "analysis_date": args.analysis_date,
        "analysts": args.analysts,
        "max_debate_rounds": str(debate_rounds),
        "max_risk_discuss_rounds": str(risk_rounds),
        "max_recur_limit": str(recur_limit),
        "llm_timeout_seconds": str(llm_timeout),
        "llm_max_retries": str(llm_max_retries),
        "http_timeout_seconds": str(http_timeout),
        "debug": str(args.debug).lower(),
    }

    os.environ["TRADINGAGENTS_MODEL_PRESET"] = args.preset
    os.environ["TRADINGAGENTS_QUICK_THINK_LLM"] = quick_model
    os.environ["TRADINGAGENTS_DEEP_THINK_LLM"] = deep_model
    os.environ["TRADINGAGENTS_TICKER"] = args.ticker
    os.environ["TRADINGAGENTS_ANALYSIS_DATE"] = args.analysis_date
    os.environ["TRADINGAGENTS_ANALYSTS"] = args.analysts
    os.environ["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] = str(debate_rounds)
    os.environ["TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS"] = str(risk_rounds)
    os.environ["TRADINGAGENTS_MAX_RECUR_LIMIT"] = str(recur_limit)
    os.environ["TRADINGAGENTS_LLM_TIMEOUT_SECONDS"] = str(llm_timeout)
    os.environ["TRADINGAGENTS_LLM_MAX_RETRIES"] = str(llm_max_retries)
    os.environ["TRADINGAGENTS_HTTP_TIMEOUT_SECONDS"] = str(http_timeout)
    os.environ["TRADINGAGENTS_DEBUG"] = str(args.debug).lower()

    return effective


def _extract_summary(final_trade_decision: str) -> str:
    patterns = [
        r"\*\*Executive Summary\*\*\s*(.+?)(?:\n\s*\d+\.\s+\*\*|\Z)",
        r"Executive Summary\s*(.+?)(?:\n\s*\d+\.\s*\*\*|\Z)",
    ]

    for pattern in patterns:
        match = re.search(pattern, final_trade_decision, flags=re.DOTALL | re.IGNORECASE)
        if match:
            summary = re.sub(r"\s+", " ", match.group(1)).strip()
            if summary:
                return summary

    paragraphs = [part.strip() for part in final_trade_decision.split("\n\n") if part.strip()]
    if paragraphs:
        return re.sub(r"\s+", " ", paragraphs[0]).strip()

    return ""


def _compact_reports(reports: Dict[str, str]) -> Dict[str, str]:
    return {name: content for name, content in reports.items() if content}


def _build_tool_success_payload(
    effective: Dict[str, str],
    result: Dict[str, object],
    elapsed_seconds: float,
) -> Dict[str, object]:
    return {
        "ok": True,
        "tool": TOOL_NAME,
        "input": {
            "ticker": effective["ticker"],
            "analysis_date": effective["analysis_date"],
            "preset": effective["preset"],
            "mode": effective["mode"],
            "analysts": [item.strip() for item in effective["analysts"].split(",") if item.strip()],
        },
        "result": {
            "rating": result["rating"],
            "summary": _extract_summary(str(result["final_trade_decision"])),
            "decision": result["final_trade_decision"],
            "models": {
                "provider": result["provider"],
                "quick": result["quick_think_llm"],
                "deep": result["deep_think_llm"],
                "base_url": result["backend_url"],
            },
            "reports": _compact_reports(result["reports"]),
            "artifacts": {
                "log_path": result["log_path"],
                "mode": result.get("mode", effective["mode"]),
            },
        },
        "meta": {
            "elapsed_seconds": round(elapsed_seconds, 2),
        },
    }


def _classify_error(exc: BaseException) -> tuple[int, str]:
    message = str(exc).lower()

    if isinstance(exc, SystemExit):
        return 2, "config_error"

    if "api key" in message or "base url" in message:
        return 2, "config_error"

    if "alpha_vantage" in message or "yfinance" in message or "ticker" in message:
        return 4, "data_error"

    if "rate_limit" in message or "tpm limit" in message or "model not found" in message or "valid services" in message:
        return 5, "provider_error"

    return 3, "runtime_error"


def _build_tool_error_payload(
    effective: Dict[str, str] | None,
    exc: BaseException,
    elapsed_seconds: float,
) -> Dict[str, object]:
    _, error_code = _classify_error(exc)
    input_payload = None
    if effective is not None:
        input_payload = {
            "ticker": effective["ticker"],
            "analysis_date": effective["analysis_date"],
            "preset": effective["preset"],
            "mode": effective["mode"],
            "analysts": [item.strip() for item in effective["analysts"].split(",") if item.strip()],
        }

    return {
        "ok": False,
        "tool": TOOL_NAME,
        "input": input_payload,
        "error": {
            "code": error_code,
            "message": str(exc),
        },
        "meta": {
            "elapsed_seconds": round(elapsed_seconds, 2),
        },
    }


def main() -> None:
    args = _parse_args()
    if args.json and args.debug:
        raise SystemExit("--json cannot be combined with --debug.")

    started_at = time.time()
    effective = None

    try:
        _resolve_api_env()
        effective = _apply_runtime_env(args)

        if args.show_config:
            print(json.dumps(effective, indent=2, ensure_ascii=False))
            return

        from run_analysis import run_analysis, run_shallow_analysis

        run_mode = args.mode
        if run_mode == "auto" and _is_jd_openai_base_url(effective["base_url"]):
            run_mode = "shallow"

        if run_mode == "shallow":
            result = run_shallow_analysis()
        else:
            result = run_analysis()
        if args.json:
            payload = _build_tool_success_payload(
                effective,
                result,
                time.time() - started_at,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        print(result["rating"])
    except (Exception, SystemExit) as exc:
        if not args.json:
            raise

        exit_code, _ = _classify_error(exc)
        payload = _build_tool_error_payload(
            effective,
            exc,
            time.time() - started_at,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
