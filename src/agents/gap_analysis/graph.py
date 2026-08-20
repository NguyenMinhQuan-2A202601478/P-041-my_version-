"""LangGraph graph definition for the CV Gap Analysis Agent.

WHY a linear chain instead of parallel branches for extract_cv_skills /
extract_jd_requirements? LangGraph supports fan-out/fan-in, but it adds
real complexity (the `Send` API, merge semantics for concurrent state
updates) for a two-node speedup that isn't worth it here — one of the two
nodes doesn't even call an LLM (see nodes.py). A simple, readable sequence
is easier for future maintainers (including a solo student developer) to
reason about and debug.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.gap_analysis.nodes import (
    compute_match,
    extract_cv_skills,
    extract_jd_requirements,
    generate_suggestions,
    guardrail_check,
    identify_gaps,
    validate_input,
)
from src.agents.state import GapAnalysisState


def _after_validation(state: GapAnalysisState) -> str:
    return END if state.get("error") else "extract_cv_skills"


def create_gap_analysis_graph() -> CompiledStateGraph:
    """Build and compile the Gap Analysis agent graph.

    Usage:
        graph = create_gap_analysis_graph()
        result_state = await graph.ainvoke({
            "cv_raw_text": ...,
            "cv_parsed_json": ...,
            "jd_title": ...,
            "jd_requirements": ...,
        })
    """
    graph = StateGraph(GapAnalysisState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("extract_cv_skills", extract_cv_skills)
    graph.add_node("extract_jd_requirements", extract_jd_requirements)
    graph.add_node("compute_match", compute_match)
    graph.add_node("identify_gaps", identify_gaps)
    graph.add_node("generate_suggestions", generate_suggestions)
    graph.add_node("guardrail_check", guardrail_check)

    graph.set_entry_point("validate_input")
    graph.add_conditional_edges("validate_input", _after_validation)
    graph.add_edge("extract_cv_skills", "extract_jd_requirements")
    graph.add_edge("extract_jd_requirements", "compute_match")
    graph.add_edge("compute_match", "identify_gaps")
    graph.add_edge("identify_gaps", "generate_suggestions")
    graph.add_edge("generate_suggestions", "guardrail_check")
    graph.add_edge("guardrail_check", END)

    return graph.compile()
