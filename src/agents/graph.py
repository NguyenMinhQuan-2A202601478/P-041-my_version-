"""Top-level entry point for the project's two LangGraph agents.

The API layer (owned by agent_web) should import from here rather than
reaching into `src.agents.gap_analysis.*` / `src.agents.interview.*`
directly — this keeps one stable import surface even if the internal
package layout changes.
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from src.agents.gap_analysis.graph import create_gap_analysis_graph
from src.agents.interview.graph import create_interview_graph

__all__ = ["create_gap_analysis_graph", "create_interview_graph"]


def create_graph(kind: str) -> CompiledStateGraph:
    """Convenience dispatcher: `create_graph("gap_analysis" | "interview")`.

    Prefer calling `create_gap_analysis_graph()` / `create_interview_graph()`
    directly when the kind is known at the call site (clearer, and the
    return type is obvious); this exists for code that picks the agent
    dynamically (e.g. a generic "run agent by name" admin/debug tool).
    """
    if kind == "gap_analysis":
        return create_gap_analysis_graph()
    if kind == "interview":
        return create_interview_graph()
    raise ValueError(f"Unknown agent kind: {kind!r}. Expected 'gap_analysis' or 'interview'.")
