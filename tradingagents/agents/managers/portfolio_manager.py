from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.market_compaction import (
    build_compact_research_context,
    compact_argument,
    compact_debate_history,
    compact_generated_report,
    compact_memory_recommendations,
)

def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = build_compact_research_context(
            market_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            market_max_chars=520,
            sentiment_max_chars=220,
            news_max_chars=380,
            fundamentals_max_chars=260,
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = compact_memory_recommendations(
            (rec["recommendation"] for rec in past_memories),
            per_item_chars=260,
        )
        history = compact_debate_history(history, max_chars=900)
        trader_plan = compact_argument(trader_plan, max_chars=650)

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

Use exactly one rating: Buy, Overweight, Hold, Underweight, or Sell.

Trader's proposed plan:
{trader_plan}

Compact research brief:
{curr_situation}

Lessons from similar situations:
{past_memory_str}

Risk analysts debate history:
{history}

Requirements:
- Be decisive. Hold only if strongly justified.
- Ground the call in the strongest evidence from the debate and research brief.
- Cover entry or exposure, sizing, key invalidation/risk level, and time horizon.
- Max 220 words.
- Plain text only.

Output sections:
Rating:
Executive Summary:
Investment Thesis:"""

        response = llm.invoke(prompt)
        response_text = compact_generated_report(response.content, max_chars=1100)

        new_risk_debate_state = {
            "judge_decision": response_text,
            "history": history,
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response_text,
        }

    return portfolio_manager_node
