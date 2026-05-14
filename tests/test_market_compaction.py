from tradingagents.agents.utils.market_compaction import (
    cap_history_start,
    cap_indicator_lookback,
    compact_indicator_output,
    compact_stock_data,
)


def test_cap_history_start_shortens_hk_window() -> None:
    assert cap_history_start("9868.HK", "2025-09-23", "2026-03-23") == "2026-01-22"


def test_cap_indicator_lookback_shortens_hk_window() -> None:
    assert cap_indicator_lookback("9868.HK", 60) == 30


def test_compact_stock_data_returns_summary_and_recent_rows() -> None:
    raw = """# Stock data for 9868.HK from 2026-01-22 to 2026-03-23
# Total records: 3
# Data retrieved on: 2026-03-23 14:00:00

Date,Open,High,Low,Close,Volume
2026-03-19,73.5,76.75,73.5,75.45,15124989
2026-03-20,75.7,77.3,71.0,71.6,26124893
2026-03-23,71.8,72.4,70.9,72.1,12000000
"""
    compact = compact_stock_data(
        "9868.HK",
        "2025-09-23",
        "2026-01-22",
        "2026-03-23",
        raw,
    )
    assert "Compact stock snapshot for 9868.HK" in compact
    assert "Requested window: 2025-09-23 to 2026-03-23" in compact
    assert "Recent trading days" in compact
    assert "2026-03-23" in compact


def test_compact_indicator_output_returns_recent_summary() -> None:
    raw = """## rsi values from 2026-02-22 to 2026-03-23:

2026-03-23: N/A: Not a trading day (weekend or holiday)
2026-03-20: 41.23
2026-03-19: 45.11
2026-03-18: 47.88
2026-03-17: 49.56

RSI: Measures momentum.
"""
    compact = compact_indicator_output("9868.HK", "rsi", 60, 30, raw)
    assert "Compact rsi snapshot for 9868.HK" in compact
    assert "Requested lookback: 60 days" in compact
    assert "Latest valid reading: 2026-03-20 -> 41.2300" in compact
