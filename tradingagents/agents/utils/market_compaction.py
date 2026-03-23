from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Iterable, List, Optional, Tuple

import pandas as pd


def infer_market(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if normalized.endswith(".HK"):
        return "HK"
    if normalized.endswith((".SH", ".SZ", ".BJ", ".SS")):
        return "CN"
    return "US"


def cap_history_start(symbol: str, start_date: str, end_date: str) -> str:
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    market = infer_market(symbol)
    max_days = {
        "HK": 60,
        "CN": 90,
        "US": 120,
    }.get(market, 90)
    capped_start = max(start_dt, end_dt - timedelta(days=max_days))
    return capped_start.strftime("%Y-%m-%d")


def cap_indicator_lookback(symbol: str, look_back_days: int) -> int:
    market = infer_market(symbol)
    max_days = {
        "HK": 30,
        "CN": 45,
        "US": 60,
    }.get(market, 45)
    return max(5, min(int(look_back_days), max_days))


def compact_stock_data(
    symbol: str,
    requested_start_date: str,
    effective_start_date: str,
    end_date: str,
    raw: str,
    max_rows: int = 12,
) -> str:
    if not raw or raw.startswith(("Error", "No data found")):
        return raw

    csv_start = raw.find("Date,")
    if csv_start == -1:
        return _truncate(raw, 2200)

    try:
        df = pd.read_csv(StringIO(raw[csv_start:]))
    except Exception:
        return _truncate(raw, 2200)

    if df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return _truncate(raw, 2200)

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Close"]).copy()
    if df.empty:
        return _truncate(raw, 2200)

    numeric_cols = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col in df.columns]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("Date")
    recent = df.tail(max_rows).copy()

    first_close = float(df.iloc[0]["Close"])
    last_close = float(df.iloc[-1]["Close"])
    high = float(df["High"].max()) if "High" in df.columns else last_close
    low = float(df["Low"].min()) if "Low" in df.columns else last_close
    avg_volume = float(df["Volume"].mean()) if "Volume" in df.columns else 0.0
    return_pct = ((last_close / first_close) - 1.0) * 100 if first_close else 0.0

    recent["Date"] = recent["Date"].dt.strftime("%Y-%m-%d")
    if "Volume" in recent.columns:
        recent["Volume"] = recent["Volume"].fillna(0).astype(int)
    for col in ["Open", "High", "Low", "Close"]:
        if col in recent.columns:
            recent[col] = recent[col].round(2)

    table_cols = [col for col in ["Date", "Open", "High", "Low", "Close", "Volume"] if col in recent.columns]
    recent_table = recent[table_cols].to_csv(index=False)

    lines = [
        f"# Compact stock snapshot for {symbol.upper()}",
        f"Requested window: {requested_start_date} to {end_date}",
        f"Effective window: {effective_start_date} to {end_date}",
        f"Trading rows used: {len(df)}",
        "",
        "Summary:",
        f"- Last close: {last_close:.2f}",
        f"- Window return: {return_pct:.2f}%",
        f"- Window high / low: {high:.2f} / {low:.2f}",
        f"- Average volume: {avg_volume:,.0f}",
        "",
        f"Recent trading days (last {len(recent)} rows):",
        recent_table.strip(),
    ]
    return "\n".join(lines)


def compact_indicator_output(
    symbol: str,
    indicator: str,
    requested_look_back_days: int,
    effective_look_back_days: int,
    raw: str,
    max_points: int = 8,
) -> str:
    if not raw or raw.startswith(("Error", "No ", "N/A")):
        return raw

    observations = _parse_indicator_observations(raw)
    if not observations:
        return _truncate(raw, 1200)

    valid_points = [(date_str, value) for date_str, value in observations if isinstance(value, float)]
    recent_points = observations[:max_points]

    latest_valid = valid_points[0] if valid_points else None
    valid_values = [value for _, value in valid_points]
    trend = _trend_from_points(valid_points[:5])

    lines = [
        f"## Compact {indicator} snapshot for {symbol.upper()}",
        f"Requested lookback: {requested_look_back_days} days",
        f"Effective lookback: {effective_look_back_days} days",
        f"Observation rows returned: {len(observations)}",
    ]

    if latest_valid is not None:
        lines.extend(
            [
                f"Latest valid reading: {latest_valid[0]} -> {latest_valid[1]:.4f}",
                f"Window min / max: {min(valid_values):.4f} / {max(valid_values):.4f}",
                f"Recent trend: {trend}",
            ]
        )

    lines.append("")
    lines.append("Recent observations:")
    for date_str, value in recent_points:
        rendered = f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"- {date_str}: {rendered}")

    return "\n".join(lines)


def compact_company_news(
    ticker: str,
    start_date: str,
    end_date: str,
    raw: str,
    max_articles: int = 6,
) -> str:
    if not raw or raw.startswith(("Error", "No news")):
        return raw

    articles = _parse_news_articles(raw)
    if not articles:
        return _truncate(raw, 2200)

    selected = articles[:max_articles]
    lines = [
        f"## Compact {ticker.upper()} news summary",
        f"Date range: {start_date} to {end_date}",
        f"Articles kept: {len(selected)} of {len(articles)}",
        "",
    ]
    for index, article in enumerate(selected, start=1):
        lines.append(f"{index}. {article['title']} [{article['source']}]")
        if article["summary"]:
            lines.append(f"   - {article['summary']}")
    return "\n".join(lines)


def compact_global_news(
    curr_date: str,
    look_back_days: int,
    raw: str,
    max_articles: int = 5,
) -> str:
    if not raw or raw.startswith(("Error", "No global news")):
        return raw

    articles = _parse_news_articles(raw)
    if not articles:
        return _truncate(raw, 2200)

    selected = articles[:max_articles]
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    lines = [
        "## Compact global market news summary",
        f"Date range: {start_date} to {curr_date}",
        f"Articles kept: {len(selected)} of {len(articles)}",
        "",
    ]
    for index, article in enumerate(selected, start=1):
        lines.append(f"{index}. {article['title']} [{article['source']}]")
        if article["summary"]:
            lines.append(f"   - {article['summary']}")
    return "\n".join(lines)


def compact_generated_report(report: str, max_chars: int = 2200) -> str:
    text = (report or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def build_compact_research_context(
    *,
    market_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    market_max_chars: int = 900,
    sentiment_max_chars: int = 450,
    news_max_chars: int = 850,
    fundamentals_max_chars: int = 500,
) -> str:
    parts = [
        _compact_section("Market research report", market_report, market_max_chars),
        _compact_section(
            "Social media sentiment report",
            sentiment_report,
            sentiment_max_chars,
        ),
        _compact_section("Latest world affairs news", news_report, news_max_chars),
        _compact_section(
            "Company fundamentals report",
            fundamentals_report,
            fundamentals_max_chars,
        ),
    ]
    return "\n\n".join(part for part in parts if part)


def compact_debate_history(history: str, max_chars: int = 1400) -> str:
    text = (history or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def compact_argument(argument: str, max_chars: int = 700) -> str:
    return compact_generated_report(argument, max_chars=max_chars)


def compact_memory_recommendations(recommendations: Iterable[str], per_item_chars: int = 420) -> str:
    items = []
    for index, recommendation in enumerate(recommendations, start=1):
        text = compact_generated_report(recommendation, max_chars=per_item_chars)
        if text:
            items.append(f"{index}. {text}")
    return "\n\n".join(items)


def _parse_indicator_observations(raw: str) -> List[Tuple[str, float | str]]:
    observations: List[Tuple[str, float | str]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if len(stripped) < 12 or stripped[4] != "-" or ":" not in stripped:
            continue
        date_str, value_str = stripped.split(":", 1)
        date_str = date_str.strip()
        value_str = value_str.strip()
        try:
            value = float(value_str)
        except ValueError:
            value = value_str
        observations.append((date_str, value))
    return observations


def _trend_from_points(points: Iterable[Tuple[str, float]]) -> str:
    values = [value for _, value in points]
    if len(values) < 2:
        return "insufficient data"
    if values[0] > values[-1]:
        return "rising"
    if values[0] < values[-1]:
        return "falling"
    return "flat"


def _truncate(text: str, limit: int) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _parse_news_articles(raw: str) -> List[dict]:
    articles: List[dict] = []
    current: Optional[dict] = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if current:
                articles.append(current)
            title_line = stripped[4:]
            source = "Unknown"
            title = title_line
            if " (source: " in title_line and title_line.endswith(")"):
                title, source_part = title_line.rsplit(" (source: ", 1)
                source = source_part[:-1]
            current = {"title": title, "source": source, "summary": "", "link": ""}
            continue
        if not current or not stripped:
            continue
        if stripped.startswith("Link: "):
            current["link"] = stripped[6:]
        elif not current["summary"]:
            current["summary"] = _truncate(stripped, 140)
    if current:
        articles.append(current)
    return articles


def _compact_section(label: str, text: str, max_chars: int) -> str:
    compact = compact_generated_report(text, max_chars=max_chars)
    if not compact:
        return ""
    return f"{label}: {compact}"
