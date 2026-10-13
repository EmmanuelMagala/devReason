
from functools import partial
import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from src.agents.state import ReviewState
from src.agents.nodes import (
    fetch_pr, load_pr_history, load_project_insights,
    supervisor, code_analyst, security_agent, semantic_security_agent,
    architecture_agent, merge_findings, report_writer, persist_review,
    save_pr_memory, update_project_insights, post_to_github,
    complete_review,
)

log = structlog.get_logger()


async def _load_pr_history_node(state: ReviewState, store):
    return await load_pr_history.run(state, store=store)


async def _load_project_insights_node(state: ReviewState, store):
    return await load_project_insights.run(state, store=store)


async def _save_pr_memory_node(state: ReviewState, store):
    return await save_pr_memory.run(state, store=store)


async def _update_project_insights_node(state: ReviewState, store):
    return await update_project_insights.run(state, store=store)


def compile_review_graph(checkpointer, store):
    """
    Builds and compiles the 12-node review graph.
    Called once at startup. Returns a compiled graph stored on app.state.
    The graph object is stateless — all per-request state comes from the checkpointer.
    """
    graph = StateGraph(ReviewState)

    # Register all 12 nodes
    graph.add_node("fetch_pr",                  fetch_pr.run)
    graph.add_node("load_pr_history",           partial(_load_pr_history_node, store=store))
    graph.add_node("load_project_insights",     partial(_load_project_insights_node, store=store))
    graph.add_node("supervisor",                supervisor.run)
    graph.add_node("code_analyst",              code_analyst.run)
    graph.add_node("security_agent",            security_agent.run)
    graph.add_node("semantic_security_agent",   semantic_security_agent.run)
    graph.add_node("architecture_agent",        architecture_agent.run)
    graph.add_node("merge_findings",            merge_findings.run)
    graph.add_node("report_writer",             report_writer.run)
    graph.add_node("persist_review",            persist_review.run)
    graph.add_node("save_pr_memory",            partial(_save_pr_memory_node, store=store))
    graph.add_node("update_project_insights",   partial(_update_project_insights_node, store=store))
    graph.add_node("post_to_github",            post_to_github.run)
    graph.add_node("complete_review",           complete_review.run)

    # Linear entry: fetch → memory loading → supervisor
    graph.add_edge(START,                       "fetch_pr")
    graph.add_edge("fetch_pr",                  "load_pr_history")
    graph.add_edge("load_pr_history",           "load_project_insights")
    graph.add_edge("load_project_insights",     "supervisor")

    # Fan-out: supervisor dispatches all 3 agents in parallel
    graph.add_conditional_edges(
        "supervisor",
        supervisor.supervisor_router,
        ["code_analyst", "security_agent", "semantic_security_agent", "architecture_agent", "merge_findings"],
    )

    # All 3 agents converge at merge_findings
    graph.add_edge("code_analyst",              "merge_findings")
    graph.add_edge("security_agent",            "merge_findings")
    graph.add_edge("semantic_security_agent",   "merge_findings")
    graph.add_edge("architecture_agent",        "merge_findings")
    graph.add_edge("merge_findings",            "report_writer")
    graph.add_edge("report_writer",             "persist_review")
    graph.add_edge("persist_review",            "save_pr_memory")
    graph.add_edge("save_pr_memory",            "update_project_insights")

    # Finalization: persist review first, then complete side effects, then optionally post.
    graph.add_conditional_edges(
        "update_project_insights",
        lambda state: _post_report_router(state),
        ["post_to_github", "complete_review"],
    )
    graph.add_edge("post_to_github",            "complete_review")
    graph.add_edge("complete_review",           END)

    compiled = graph.compile(checkpointer=checkpointer, store=store)
    log.info("Review graph compiled", nodes=list(compiled.nodes))
    return compiled


def _post_report_router(state: ReviewState) -> list[Send]:
    if state.repo_config.post_to_github:
        return [Send("post_to_github", state)]
    return [Send("complete_review", state)]
