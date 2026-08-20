"""LangGraph graph definition for the Mock Interview Agent.

One compiled graph serves three "operations" (see state.py), routed by
`state["operation"]` right after validate_input:

    validate_input --(start)---------> generate_questions -> END
                   --(respond)-------> evaluate_response -> score_star -+
                   --(report)--------> generate_report -> END           |
                                                                          |
        (needs_follow_up=True)  <-------------------------------------- +--> generate_followup -> END
        (needs_follow_up=False) <-------------------------------------- +--> END
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.interview.nodes import (
    evaluate_response,
    generate_followup,
    generate_questions,
    generate_report,
    score_star,
    validate_input,
)
from src.agents.state import InterviewAgentState


def _route_operation(state: InterviewAgentState) -> str:
    if state.get("error"):
        return END
    return {
        "start": "generate_questions",
        "respond": "evaluate_response",
        "report": "generate_report",
    }[state["operation"]]


def _route_after_scoring(state: InterviewAgentState) -> str:
    needs_follow_up = bool(state.get("evaluation", {}).get("needs_follow_up"))
    return "generate_followup" if needs_follow_up else END


def create_interview_graph() -> CompiledStateGraph:
    """Build and compile the Mock Interview agent graph.

    Usage:
        graph = create_interview_graph()

        # Start a session:
        state = await graph.ainvoke({
            "operation": "start", "cv_text": ..., "jd_title": ..., "jd_requirements": ...,
            "num_questions": 5,
        })
        questions = state["interview_questions"]

        # Evaluate one answer:
        state = await graph.ainvoke({
            "operation": "respond", "question_text": ..., "user_answer": ...,
        })
        star_score = state["star_score"]
        follow_up = state.get("follow_up_question")  # only set if needed

        # Build the final report once all questions are answered:
        state = await graph.ainvoke({"operation": "report", "qa_history": [...], "jd_title": ...})
        report = state["final_report"]
    """
    graph = StateGraph(InterviewAgentState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("evaluate_response", evaluate_response)
    graph.add_node("score_star", score_star)
    graph.add_node("generate_followup", generate_followup)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("validate_input")
    graph.add_conditional_edges("validate_input", _route_operation)
    graph.add_edge("generate_questions", END)
    graph.add_edge("evaluate_response", "score_star")
    graph.add_conditional_edges("score_star", _route_after_scoring)
    graph.add_edge("generate_followup", END)
    graph.add_edge("generate_report", END)

    return graph.compile()
