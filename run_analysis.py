import os
import socket
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import create_llm_client
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.technical_indicators_tools import get_indicators
from tradingagents.agents.utils.news_data_tools import get_news, get_global_news
from tradingagents.agents.utils.fundamental_data_tools import get_fundamentals
from tradingagents.agents.utils.market_compaction import (
    build_compact_research_context,
    compact_generated_report,
)


THEME_TICKERS: Dict[str, set[str]] = {
    "energy": {"XOM", "CVX", "OXY", "COP", "SLB", "HAL", "EOG", "PXD"},
    "semiconductor": {"NVDA", "AMD", "AVGO", "TSM", "MU", "QCOM", "INTC", "AMAT", "LRCX", "KLAC"},
    "software": {"MSFT", "CRM", "NOW", "ADBE", "ORCL", "SNOW", "PLTR", "MDB", "CRWD", "DDOG", "ZS", "PANW"},
    "banks": {"JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "USB", "PNC"},
}


INDUSTRY_TEMPLATE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "energy": {
        "label": "Energy",
        "positive_rules": [
            ("oil_up", "Oil and gas prices are firm -> upstream realizations improve -> free cash flow, buybacks, and dividends gain support."),
            ("automation_efficiency", "Operational automation improves offshore productivity -> lowers lifting cost / execution friction -> strengthens earnings resilience through the cycle."),
            ("asset_refocus", "Portfolio refocus toward advantaged assets -> capital allocation quality improves -> market may reward cleaner return profile."),
            ("uptrend", "Trend confirmation above medium-term averages -> sector narrative is being accepted by incremental capital, not just defended by longs."),
        ],
        "risk_rules": [
            ("overbought", "Commodity-linked strength is already reflected in price; overbought conditions raise the odds of mean reversion before the next leg."),
            ("middle_east_risk", "Geopolitical premium can reverse quickly if supply fears cool, so narrative support may decay faster than fundamentals."),
            ("rate_hike", "Higher real rates can tighten global growth expectations and cap the multiple investors are willing to pay for cyclical cash flows."),
        ],
        "default_positive": "Integrated cash generation and shareholder return capacity make the group investable when the commodity tape stays constructive.",
        "default_risk": "Energy theses degrade quickly when commodity direction flips, so price confirmation matters as much as the narrative.",
        "strategy_tilt": {
            "bullish": "Prefer macro pass-through or pullback-long structures tied to oil strength, not blind momentum chasing.",
            "neutral": "Prefer watchlist / pullback entries over fresh breakout chasing.",
            "bearish": "Reduce aggression and wait for commodity confirmation before promoting the idea."
        },
    },
    "semiconductor": {
        "label": "Semiconductors",
        "positive_rules": [
            ("ai_capex", "AI capex stays strong -> accelerator / networking demand improves -> earnings revisions and valuation support can follow."),
            ("uptrend", "Price trend and momentum align -> institutions are more likely to keep pressing winners while estimate revisions hold."),
            ("rising_ma", "Trading above key moving averages keeps the long-duration growth thesis investable for trend allocators."),
        ],
        "risk_rules": [
            ("downtrend", "Price trend is no longer confirming the AI narrative, so even strong fundamentals can fail to convert into immediate returns."),
            ("rate_hike", "Higher discount rates pressure long-duration semiconductor multiples even when end-demand remains healthy."),
            ("middle_east_risk", "Macro shock can rotate flows out of high-beta AI leaders faster than fundamentals change."),
        ],
        "default_positive": "Estimate revision power is the main engine; when capex confidence persists, the group can re-rate quickly.",
        "default_risk": "Crowded AI positioning can compress quickly on any capex disappointment or export-policy headline.",
        "strategy_tilt": {
            "bullish": "Prefer trend-follow or breakout-confirmation structures with tight event risk controls.",
            "neutral": "Prefer staged entries and faster feedback loops because sentiment can turn faster than fundamentals.",
            "bearish": "Prefer observation or reversal-only setups until price repairs above trend filters."
        },
    },
    "software": {
        "label": "Software",
        "positive_rules": [
            ("ai_capex", "Enterprise AI adoption expands software monetization opportunities -> premium vendors can convert narrative into higher seat value or attach rates."),
            ("rate_cut", "Lower rate expectations improve valuation support for long-duration recurring-revenue assets."),
            ("uptrend", "Stable uptrend suggests investors are rewarding durability of recurring revenue, not just tactical optimism."),
        ],
        "risk_rules": [
            ("rate_hike", "Higher-for-longer rates compress software multiples before operating results visibly weaken."),
            ("downtrend", "Weak price confirmation implies investors doubt near-term reacceleration in bookings or margins."),
            ("overbought", "Even quality software names can mean-revert sharply when positioning gets too one-sided."),
        ],
        "default_positive": "Recurring revenue and expanding product bundles create room for quality software to compound through moderate macro noise.",
        "default_risk": "Software narratives break when valuation gets too far ahead of evidence from renewals, upsell, or AI monetization.",
        "strategy_tilt": {
            "bullish": "Prefer quality-growth trend or post-earnings continuation structures over deep-value framing.",
            "neutral": "Prefer selective observation and wait for cleaner proof of monetization or multiple support.",
            "bearish": "Avoid forcing longs while duration pressure and weak price action are both active."
        },
    },
    "banks": {
        "label": "Banks",
        "positive_rules": [
            ("rate_hike", "Higher-for-longer rates can support asset yields and trading income for well-positioned banks if credit quality remains contained."),
            ("uptrend", "Positive trend suggests investors are becoming more comfortable with balance-sheet and credit risk."),
        ],
        "risk_rules": [
            ("rate_cut", "Rate-cut expectations can support risk assets, but bank net-interest margins may compress if funding costs do not fall as fast."),
            ("downtrend", "Weak price action implies the market is discounting funding stress, softer loan growth, or rising credit costs."),
            ("middle_east_risk", "Macro stress can tighten financial conditions and widen credit concerns before earnings show the damage."),
        ],
        "default_positive": "Financials work best when credit costs stay contained and the rate path remains favorable to spreads and capital return.",
        "default_risk": "Funding sensitivity and credit surprises can overwhelm a superficially cheap bank thesis.",
        "strategy_tilt": {
            "bullish": "Prefer spread-sensitive trend or value-repricing structures with explicit credit-risk checks.",
            "neutral": "Prefer observation until the market gives cleaner evidence on margins and credit costs.",
            "bearish": "Stay defensive until price and macro conditions stop implying stress."
        },
    },
    "generic": {
        "label": "Generic",
        "positive_rules": [
            ("uptrend", "Technical trend remains constructive -> observation bias should stay positive unless news flow breaks the trend."),
            ("rising_ma", "Holding above medium-term averages keeps the setup investable for systematic trend allocators."),
        ],
        "risk_rules": [
            ("downtrend", "Negative price trend still dominates; any thesis needs a catalyst strong enough to reverse positioning."),
            ("overbought", "A stretched technical position reduces the quality of fresh entry even if the broad thesis still works."),
        ],
        "default_positive": "No dominant sector template detected; rely on price confirmation and capital discipline.",
        "default_risk": "Without a clear sector pass-through, narrative confidence should stay below pure price confirmation.",
        "strategy_tilt": {
            "bullish": "Prefer smaller sizing and thesis validation before promoting to a higher-conviction trade.",
            "neutral": "Keep the name in watchlist mode until catalyst quality improves.",
            "bearish": "Prefer defensive observation or reversal-only setups until trend damage repairs."
        },
    },
}


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
    config["llm_timeout_seconds"] = float(
        os.getenv("TRADINGAGENTS_LLM_TIMEOUT_SECONDS", "180")
    )
    config["llm_max_retries"] = _get_int("TRADINGAGENTS_LLM_MAX_RETRIES", 1)
    config["http_timeout_seconds"] = float(
        os.getenv("TRADINGAGENTS_HTTP_TIMEOUT_SECONDS", "45")
    )
    return config


def run_analysis() -> Dict[str, Any]:
    config = build_runtime_config()
    analysts = _get_analysts()
    ticker = os.getenv("TRADINGAGENTS_TICKER", "NVDA")
    analysis_date = os.getenv("TRADINGAGENTS_ANALYSIS_DATE", "2024-05-10")
    debug = _get_bool("TRADINGAGENTS_DEBUG", False)

    # Guard all external blocking I/O, including Yahoo data/news requests.
    http_timeout = config.get("http_timeout_seconds")
    if isinstance(http_timeout, (int, float)) and http_timeout > 0:
        socket.setdefaulttimeout(float(http_timeout))

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
        "mode": "graph",
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


def _safe_tool_invoke(tool, payload: Dict[str, Any], label: str) -> str:
    try:
        result = tool.invoke(payload)
        return compact_generated_report(str(result), max_chars=2200)
    except Exception as exc:
        return f"{label} unavailable: {exc}"


def _extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _heuristic_rating(market_report: str, fundamentals_report: str) -> str:
    market_text = market_report.lower()
    fundamentals_text = fundamentals_report.lower()
    if "window return: -" in market_text or "downtrend" in market_text:
        return "SELL"
    if "window return:" in market_text and "window return: -" not in market_text:
        if "profitable" in fundamentals_text or "cash" in fundamentals_text:
            return "BUY"
        return "HOLD"
    return "HOLD"


def _parse_fundamental_snapshot(fundamentals_report: str) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for line in (fundamentals_report or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        snapshot[key] = value.strip()
    return snapshot


def _market_signal_flags(market_report: str) -> Dict[str, bool]:
    text = (market_report or "").lower()
    return {
        "uptrend": "window return: -" not in text and "window return:" in text,
        "downtrend": "window return: -" in text,
        "overbought": "latest valid reading" in text and "rsi" in text and any(token in text for token in ["70.", "71.", "72.", "73.", "74."]),
        "rising_ma": "recent trend: rising" in text and "close_50_sma" in text,
        "rising_macd": "macd snapshot" in text and "recent trend: rising" in text,
    }


def _news_theme_flags(news_report: str) -> Dict[str, bool]:
    text = (news_report or "").lower()
    return {
        "oil_up": any(token in text for token in ["oil prices", "oil stock", "原油", "美油", "布油", "天然气"]),
        "middle_east_risk": any(token in text for token in ["middle east", "中东", "战争", "冲突"]),
        "automation_efficiency": any(token in text for token in ["automated", "automation", "fully automated", "efficiency"]),
        "asset_refocus": any(token in text for token in ["refocus", "exit", "advantaged assets", "portfolio optimization"]),
        "ai_capex": any(token in text for token in ["ai", "artificial intelligence", "gpu", "chip", "semiconductor"]),
        "rate_cut": any(token in text for token in ["fed keeps cutting", "cut rates", "降息"]),
        "rate_hike": any(token in text for token in ["加息", "rate hike", "higher for longer"]),
    }


def _infer_company_theme(ticker: str, fundamentals_report: str) -> Tuple[str, str]:
    snapshot = _parse_fundamental_snapshot(fundamentals_report)
    sector = snapshot.get("sector", "").lower()
    industry = snapshot.get("industry", "").lower()
    normalized = ticker.upper()

    if normalized in THEME_TICKERS["energy"] or "oil" in industry or "energy" in sector:
        return "energy", snapshot.get("sector", "Energy")
    if normalized in THEME_TICKERS["semiconductor"] or "semiconductor" in industry:
        return "semiconductor", snapshot.get("sector", "Technology")
    if normalized in THEME_TICKERS["software"] or "software" in industry or "saas" in industry:
        return "software", snapshot.get("sector", "Technology")
    if normalized in THEME_TICKERS["banks"] or "bank" in industry or "financial" in sector:
        return "banks", snapshot.get("sector", "Financials")
    return "generic", snapshot.get("sector", "Unknown")


def _template_bias(market_flags: Dict[str, bool]) -> str:
    if market_flags.get("downtrend"):
        return "bearish"
    if market_flags.get("uptrend"):
        return "bullish"
    return "neutral"


def _template_lines(
    *,
    template: Dict[str, Any],
    active_flags: Dict[str, bool],
    rule_key: str,
    default_key: str,
) -> List[str]:
    lines: List[str] = []
    for flag_name, text in template.get(rule_key, []):
        if active_flags.get(flag_name):
            lines.append(text)
    if not lines:
        lines.append(template.get(default_key, ""))
    return [line for line in lines if line]


def _build_causal_chain_report(
    *,
    ticker: str,
    market_report: str,
    news_report: str,
    fundamentals_report: str,
) -> str:
    company_theme, sector_label = _infer_company_theme(ticker, fundamentals_report)
    market_flags = _market_signal_flags(market_report)
    news_flags = _news_theme_flags(news_report)
    active_flags = {**market_flags, **news_flags}
    template = INDUSTRY_TEMPLATE_LIBRARY.get(company_theme, INDUSTRY_TEMPLATE_LIBRARY["generic"])
    lines = [
        f"## Causal chain for {ticker}",
        f"Sector lens: {sector_label or template['label']}",
    ]

    chains = _template_lines(
        template=template,
        active_flags=active_flags,
        rule_key="positive_rules",
        default_key="default_positive",
    )
    risks = _template_lines(
        template=template,
        active_flags=active_flags,
        rule_key="risk_rules",
        default_key="default_risk",
    )

    lines.append("")
    lines.append("Positive pass-through:")
    for item in chains:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Main fragilities:")
    for item in risks:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _default_strategy_tilt(
    ticker: str,
    market_report: str,
    fundamentals_report: str,
    causal_chain_report: str,
) -> str:
    theme, _ = _infer_company_theme(ticker, fundamentals_report)
    market_flags = _market_signal_flags(market_report)
    template = INDUSTRY_TEMPLATE_LIBRARY.get(theme, INDUSTRY_TEMPLATE_LIBRARY["generic"])
    return template.get("strategy_tilt", {}).get(
        _template_bias(market_flags),
        INDUSTRY_TEMPLATE_LIBRARY["generic"]["strategy_tilt"]["neutral"],
    )


def _default_thesis(
    ticker: str,
    market_report: str,
    fundamentals_report: str,
    causal_chain_report: str,
) -> str:
    theme, _ = _infer_company_theme(ticker, fundamentals_report)
    market_flags = _market_signal_flags(market_report)
    template = INDUSTRY_TEMPLATE_LIBRARY.get(theme, INDUSTRY_TEMPLATE_LIBRARY["generic"])
    if market_flags["uptrend"] and not market_flags["overbought"]:
        return f"{ticker} has a constructive {template['label'].lower()} setup where narrative support and price confirmation still align."
    if market_flags["uptrend"] and market_flags["overbought"]:
        return f"{ticker} still has a valid {template['label'].lower()} thesis, but the entry is degraded because price has already pulled too much future good news forward."
    if market_flags["downtrend"]:
        return f"{ticker} may still have a long-term {template['label'].lower()} story, but the market is not validating it yet; timing risk dominates until trend damage repairs."
    if "positive pass-through" in causal_chain_report.lower():
        return f"{ticker} has a usable sector pass-through thesis, but it still needs cleaner price confirmation before acting aggressively."
    return "Compact research suggests a watchlist-grade thesis rather than a fully debated high-conviction trade."


def _build_shallow_decision(
    *,
    llm,
    ticker: str,
    analysis_date: str,
    reports: Dict[str, str],
) -> Dict[str, str]:
    context = build_compact_research_context(
        market_report=reports.get("market", ""),
        sentiment_report=reports.get("social", ""),
        news_report=reports.get("news", ""),
        fundamentals_report=reports.get("fundamentals", ""),
    )
    prompt = f"""
You are producing a compact trading research note for {ticker} on {analysis_date}.
Use the supplied research context and return strict JSON with keys:
- rating: BUY, HOLD, or SELL
- summary: <= 120 words
- investment_plan: <= 120 words
- trader_plan: <= 120 words
- thesis: <= 80 words
- causal_chain: array of 2-4 short strings
- risks: array of 2-4 short strings
- strategy_tilt: <= 40 words

Research context:
{context}
""".strip()

    try:
        response = llm.invoke(prompt)
        payload = _extract_json_object(getattr(response, "content", str(response)))
    except Exception:
        payload = {}

    rating = str(payload.get("rating") or "").upper()
    if rating not in {"BUY", "HOLD", "SELL"}:
        rating = _heuristic_rating(reports.get("market", ""), reports.get("fundamentals", ""))

    summary = str(payload.get("summary") or "").strip()
    if not summary:
        summary = "Shallow research fallback based on compact market, news, and fundamentals context."

    investment_plan = str(payload.get("investment_plan") or "").strip()
    if not investment_plan:
        investment_plan = f"{rating}: use the research note as a watchlist-level decision, not a fully debated graph output."

    trader_plan = str(payload.get("trader_plan") or "").strip()
    if not trader_plan:
        trader_plan = "Size conservatively and require external confirmation before treating this as a primary conviction trade."

    thesis = str(payload.get("thesis") or "").strip()
    if not thesis:
        thesis = _default_thesis(
            ticker,
            reports.get("market", ""),
            reports.get("fundamentals", ""),
            reports.get("causal_chain", ""),
        )

    causal_chain_items = [str(item).strip() for item in (payload.get("causal_chain") or []) if str(item).strip()]
    if not causal_chain_items:
        causal_chain_items = []

    risk_items = [str(item).strip() for item in (payload.get("risks") or []) if str(item).strip()]
    if not risk_items:
        risk_items = []

    strategy_tilt = str(payload.get("strategy_tilt") or "").strip()
    if not strategy_tilt:
        strategy_tilt = _default_strategy_tilt(
            ticker,
            reports.get("market", ""),
            reports.get("fundamentals", ""),
            reports.get("causal_chain", ""),
        )

    causal_block = "\n".join(f"- {item}" for item in causal_chain_items) if causal_chain_items else reports.get("causal_chain", "")
    risk_block = "\n".join(f"- {item}" for item in risk_items) if risk_items else ""

    final_trade_decision = (
        f"## Thesis\n{thesis}\n\n"
        f"## Executive Summary\n{summary}\n\n"
        f"## Causal Chain\n{causal_block}\n\n"
        f"## Rating\n{rating}\n\n"
        f"## Investment Plan\n{investment_plan}\n\n"
        f"## Trader Plan\n{trader_plan}\n\n"
        f"## Strategy Tilt\n{strategy_tilt}\n\n"
        f"## Risks\n{risk_block or 'Use normal sizing discipline and wait for cleaner confirmation.'}"
    )
    return {
        "rating": rating,
        "summary": summary,
        "investment_plan": investment_plan,
        "trader_plan": trader_plan,
        "thesis": thesis,
        "strategy_tilt": strategy_tilt,
        "final_trade_decision": final_trade_decision,
    }


def run_shallow_analysis() -> Dict[str, Any]:
    config = build_runtime_config()
    analysts = _get_analysts()
    ticker = os.getenv("TRADINGAGENTS_TICKER", "NVDA")
    analysis_date = os.getenv("TRADINGAGENTS_ANALYSIS_DATE", "2024-05-10")

    analysis_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    market_start = (analysis_dt - timedelta(days=90)).strftime("%Y-%m-%d")
    news_start = (analysis_dt - timedelta(days=14)).strftime("%Y-%m-%d")

    http_timeout = config.get("http_timeout_seconds")
    if isinstance(http_timeout, (int, float)) and http_timeout > 0:
        socket.setdefaulttimeout(float(http_timeout))

    reports: Dict[str, str] = {}
    if "market" in analysts:
        market_parts = [
            _safe_tool_invoke(
                get_stock_data,
                {"symbol": ticker, "start_date": market_start, "end_date": analysis_date},
                "market stock data",
            ),
            _safe_tool_invoke(
                get_indicators,
                {"symbol": ticker, "indicator": "close_50_sma", "curr_date": analysis_date, "look_back_days": 45},
                "market 50 SMA",
            ),
            _safe_tool_invoke(
                get_indicators,
                {"symbol": ticker, "indicator": "rsi", "curr_date": analysis_date, "look_back_days": 30},
                "market RSI",
            ),
            _safe_tool_invoke(
                get_indicators,
                {"symbol": ticker, "indicator": "macd", "curr_date": analysis_date, "look_back_days": 30},
                "market MACD",
            ),
        ]
        reports["market"] = "\n\n".join(part for part in market_parts if part)
    else:
        reports["market"] = ""

    if "news" in analysts or "social" in analysts:
        company_news = _safe_tool_invoke(
            get_news,
            {"ticker": ticker, "start_date": news_start, "end_date": analysis_date},
            "company news",
        )
        global_news = _safe_tool_invoke(
            get_global_news,
            {"curr_date": analysis_date, "look_back_days": 7, "limit": 3},
            "global news",
        )
        reports["news"] = "\n\n".join(part for part in [company_news, global_news] if part)
        reports["social"] = company_news if "social" in analysts else ""
    else:
        reports["news"] = ""
        reports["social"] = ""

    if "fundamentals" in analysts:
        reports["fundamentals"] = _safe_tool_invoke(
            get_fundamentals,
            {"ticker": ticker, "curr_date": analysis_date},
            "fundamentals",
        )
    else:
        reports["fundamentals"] = ""

    reports["causal_chain"] = _build_causal_chain_report(
        ticker=ticker,
        market_report=reports.get("market", ""),
        news_report=reports.get("news", ""),
        fundamentals_report=reports.get("fundamentals", ""),
    )

    llm_kwargs: Dict[str, Any] = {}
    timeout = config.get("llm_timeout_seconds")
    if isinstance(timeout, (int, float)) and timeout > 0:
        llm_kwargs["timeout"] = float(timeout)
    max_retries = config.get("llm_max_retries")
    if isinstance(max_retries, int) and max_retries >= 0:
        llm_kwargs["max_retries"] = max_retries

    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["quick_think_llm"],
        base_url=config.get("backend_url"),
        **llm_kwargs,
    ).get_llm()

    decision = _build_shallow_decision(
        llm=llm,
        ticker=ticker,
        analysis_date=analysis_date,
        reports=reports,
    )

    shallow_log = {
        "mode": "shallow",
        "ticker": ticker,
        "analysis_date": analysis_date,
        "analysts": analysts,
        "reports": reports,
        "decision": decision,
    }
    directory = Path(f"eval_results/{ticker}/TradingAgentsStrategy_logs/").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"shallow_state_log_{analysis_date}.json"
    log_path.write_text(json.dumps(shallow_log, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "mode": "shallow",
        "ticker": ticker,
        "analysis_date": analysis_date,
        "analysts": analysts,
        "provider": config["llm_provider"],
        "backend_url": config["backend_url"],
        "quick_think_llm": config["quick_think_llm"],
        "deep_think_llm": config["deep_think_llm"],
        "rating": decision["rating"],
        "final_trade_decision": decision["final_trade_decision"],
        "investment_plan": decision["investment_plan"],
        "trader_investment_decision": decision["trader_plan"],
        "reports": reports,
        "log_path": str(log_path),
    }


def main() -> None:
    result = run_analysis()
    print(result["rating"])


if __name__ == "__main__":
    main()
