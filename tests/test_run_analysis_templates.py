from run_analysis import _build_causal_chain_report
from run_analysis import _default_strategy_tilt
from run_analysis import _infer_company_theme


def _fundamentals(sector: str, industry: str) -> str:
    return f"Sector: {sector}\nIndustry: {industry}\n"


def test_infer_company_theme_supports_core_template_groups() -> None:
    assert _infer_company_theme("XOM", _fundamentals("Energy", "Oil & Gas Integrated"))[0] == "energy"
    assert _infer_company_theme("NVDA", _fundamentals("Technology", "Semiconductors"))[0] == "semiconductor"
    assert _infer_company_theme("MSFT", _fundamentals("Technology", "Software - Infrastructure"))[0] == "software"
    assert _infer_company_theme("JPM", _fundamentals("Financial Services", "Banks - Diversified"))[0] == "banks"


def test_energy_template_mentions_commodity_and_operational_chain() -> None:
    report = _build_causal_chain_report(
        ticker="XOM",
        market_report="window return: 12%\nclose_50_sma\nrecent trend: rising\nrsi latest valid reading 70.4",
        news_report="oil prices rising after middle east conflict and fully automated offshore project",
        fundamentals_report=_fundamentals("Energy", "Oil & Gas Integrated"),
    )
    assert "upstream realizations improve" in report
    assert "Operational automation improves" in report
    assert "Geopolitical premium can reverse quickly" in report


def test_semiconductor_template_prefers_trend_controls() -> None:
    tilt = _default_strategy_tilt(
        "NVDA",
        "window return: 8%\nclose_50_sma\nrecent trend: rising\nmacd snapshot\nrecent trend: rising",
        _fundamentals("Technology", "Semiconductors"),
        "AI capex stays strong",
    )
    assert "trend-follow" in tilt


def test_bank_template_surfaces_margin_and_credit_risk() -> None:
    report = _build_causal_chain_report(
        ticker="JPM",
        market_report="window return: -4%",
        news_report="fed keeps cutting while macro stress rises",
        fundamentals_report=_fundamentals("Financial Services", "Banks - Diversified"),
    )
    assert "net-interest margins may compress" in report
    assert "funding stress" in report or "credit" in report
