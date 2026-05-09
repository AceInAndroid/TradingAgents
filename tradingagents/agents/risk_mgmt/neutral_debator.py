
from tradingagents.agents.utils.market_compaction import (
    build_compact_research_context,
    compact_argument,
    compact_debate_history,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = compact_argument(
            state["trader_investment_plan"], max_chars=900
        )
        research_brief = build_compact_research_context(
            market_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            market_max_chars=480,
            sentiment_max_chars=220,
            news_max_chars=360,
            fundamentals_max_chars=240,
        )
        history = compact_debate_history(history, max_chars=650)
        current_aggressive_response = compact_argument(
            current_aggressive_response, max_chars=320
        )
        current_conservative_response = compact_argument(
            current_conservative_response, max_chars=320
        )

        prompt = f"""You are the Neutral Risk Analyst. Balance upside and downside, reconcile the strongest points from both sides, and push toward a practical risk-adjusted stance.

Trader proposal:
{trader_decision}

Compact research brief:
{research_brief}

Debate history:
{history}

Latest aggressive argument:
{current_aggressive_response}

Latest conservative argument:
{current_conservative_response}

Requirements:
- Identify the 1-2 strongest upside factors and 1-2 strongest risks.
- Point out where aggressive or conservative takes overreach.
- End with a balanced risk posture or conditional plan.
- Max 150 words, with up to 2 short bullets if useful.
- Plain conversational text only."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {compact_argument(response.content, max_chars=700)}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
