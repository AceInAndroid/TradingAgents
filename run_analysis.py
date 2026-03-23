import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _get_analysts() -> List[str]:
    return [
        analyst.strip()
        for analyst in os.getenv(
            "TRADINGAGENTS_ANALYSTS",
            "market,social,news,fundamentals",
        ).split(",")
        if analyst.strip()
    ]


def build_runtime_config() -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    config["backend_url"] = os.getenv(
        "TRADINGAGENTS_BACKEND_URL",
        os.getenv("OPENAI_BASE_URL", config["backend_url"]),
    )
    config["deep_think_llm"] = os.getenv(
        "TRADINGAGENTS_DEEP_THINK_LLM",
        config["deep_think_llm"],
    )
    config["quick_think_llm"] = os.getenv(
        "TRADINGAGENTS_QUICK_THINK_LLM",
        config["quick_think_llm"],
    )
    config["max_debate_rounds"] = _get_int("TRADINGAGENTS_MAX_DEBATE_ROUNDS", 1)
    config["max_risk_discuss_rounds"] = _get_int(
        "TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS", 1
    )
    config["max_recur_limit"] = _get_int("TRADINGAGENTS_MAX_RECUR_LIMIT", 30)
    return config


def run_analysis() -> Dict[str, Any]:
    config = build_runtime_config()
    analysts = _get_analysts()
    ticker = os.getenv("TRADINGAGENTS_TICKER", "NVDA")
    analysis_date = os.getenv("TRADINGAGENTS_ANALYSIS_DATE", "2024-05-10")
    debug = _get_bool("TRADINGAGENTS_DEBUG", False)

    ta = TradingAgentsGraph(
        selected_analysts=analysts,
        debug=debug,
        config=config,
    )
    final_state, decision = ta.propagate(ticker, analysis_date)
    log_path = Path(
        f"eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{analysis_date}.json"
    ).resolve()

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "analysts": analysts,
        "provider": config["llm_provider"],
        "backend_url": config["backend_url"],
        "quick_think_llm": config["quick_think_llm"],
        "deep_think_llm": config["deep_think_llm"],
        "rating": decision.strip().upper(),
        "final_trade_decision": final_state["final_trade_decision"],
        "investment_plan": final_state["investment_plan"],
        "trader_investment_decision": final_state["trader_investment_plan"],
        "reports": {
            "market": final_state["market_report"],
            "social": final_state["sentiment_report"],
            "news": final_state["news_report"],
            "fundamentals": final_state["fundamentals_report"],
        },
        "log_path": str(log_path),
    }


def main() -> None:
    result = run_analysis()
    print(result["rating"])


if __name__ == "__main__":
    main()
