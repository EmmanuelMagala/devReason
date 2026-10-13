
import uuid
import asyncio
import base64
import time
import structlog
from cryptography.fernet import Fernet
from src.core.github_app import mint_installation_token
from src.db.base import AsyncSessionLocal
from src.db.repositories.review_repo import (
    create_review as db_create_review,
    update_review_status,
)
from src.agents.state import ReviewState, RepoConfig
from src.schemas.stream import StreamEvent
from src.services.stream_service import push_event, set_status
from src.core.settings import settings

log = structlog.get_logger()

REPORT_STREAM_MIN_CHARS = 180
REPORT_STREAM_FLUSH_INTERVAL_MS = 200


def _elapsed_ms(started_at: float, finished_at: float | None = None) -> int:
    end_time = finished_at if finished_at is not None else time.perf_counter()
    return max(0, int((end_time - started_at) * 1000))


def _should_flush_report_buffer(buffer: str, last_flush_at: float, now: float) -> bool:
    if not buffer:
        return False

    if len(buffer) >= REPORT_STREAM_MIN_CHARS:
        return True

    return _elapsed_ms(last_flush_at, now) >= REPORT_STREAM_FLUSH_INTERVAL_MS


async def _flush_report_buffer(
    redis,
    review_id: str,
    report_buffer: list[str],
) -> None:
    if not report_buffer:
        return

    chunk = "".join(report_buffer)
    report_buffer.clear()
    await push_event(
        redis,
        review_id,
        StreamEvent(event="report_token", agent="report_writer", data={"token": chunk}),
    )


def _get_stream_source_node(event: dict) -> str | None:
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        node_name = metadata.get("langgraph_node")
        if isinstance(node_name, str) and node_name:
            return node_name

    name = event.get("name")
    if isinstance(name, str) and name:
        return name

    return None


def _extract_report_text(output: object) -> str | None:
    if not isinstance(output, dict):
        return None

    report_text = output.get("final_report")
    if isinstance(report_text, str) and report_text:
        return report_text

    return None


def _extract_stream_token_text(content: object) -> str | None:
    if isinstance(content, str):
        return content or None

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item:
                parts.append(item)
                continue

            if not isinstance(item, dict):
                continue

            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
                continue

            if item.get("type") == "text":
                nested_text = item.get("text")
                if isinstance(nested_text, str) and nested_text:
                    parts.append(nested_text)

        return "".join(parts) or None

    return None


async def create_review(
    clerk_user_id: str,
    repo_id: str,
    pr_url: str,
    pr_number: int,
    post_to_github: bool,
    github_token: str,
    owner: str,
    name: str,
) -> tuple[uuid.UUID, str]:
    """
    Creates the review record in Postgres and returns (review_uuid, thread_id).
    The thread_id is the composite crash-recovery key for LangGraph.
    """
    review_uuid = uuid.uuid4()
    thread_id = f"{clerk_user_id}::{repo_id}::{review_uuid}"

    async with AsyncSessionLocal() as db:
        await db_create_review(
            db=db,
            review_id=review_uuid,
            clerk_user_id=clerk_user_id,
            repo_id=uuid.UUID(repo_id),
            pr_url=pr_url,
            pr_number=pr_number,
            thread_id=thread_id,
        )

    return review_uuid, thread_id


def _decrypt_token(encrypted: str) -> str:
    key = base64.urlsafe_b64encode(bytes.fromhex(settings.encryption_key))
    fernet = Fernet(key)
    return fernet.decrypt(encrypted.encode()).decode()


async def run_review_graph(
    review_id: uuid.UUID,
    thread_id: str,
    pr_url: str,
    pr_number: int,
    repo_id: str,
    clerk_user_id: str,
    owner: str,
    name: str,
    github_installation_id: int | None,
    github_token_enc: str | None,
    post_to_github: bool,
    graph,
    redis,
) -> None:
    """
    Runs as an asyncio background task.
    Executes the full LangGraph pipeline and forwards events to Redis.
    """
    review_id_str = str(review_id)
    log.info("Starting review graph", review_id=review_id_str, pr_url=pr_url)

    await set_status(redis, review_id_str, "running")

    async with AsyncSessionLocal() as db:
        await update_review_status(db, review_id, "running")

    try:
        if github_installation_id:
            github_token = await mint_installation_token(github_installation_id)
        elif github_token_enc:
            github_token = _decrypt_token(github_token_enc)
        else:
            raise ValueError('Reconnect this repository before reviewing it.')
    except Exception:
        async with AsyncSessionLocal() as db:
            await update_review_status(db, review_id, 'failed', error_message='GitHub access could not be renewed. Reconnect the repository.')
        await set_status(redis, review_id_str, 'failed')
        await push_event(redis, review_id_str, StreamEvent(event='error', data={'message':'GitHub access could not be renewed. Reconnect the repository.'}))
        return

    initial_state = ReviewState(
        pr_url=pr_url,
        repo_config=RepoConfig(
            repo_id=repo_id,
            review_id=review_id_str,
            owner=owner,
            name=name,
            github_token=github_token,
            post_to_github=post_to_github,
        ),
    )

    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"review:{owner}/{name}#{pr_number}",
        "run_id": review_id,
        "tags": [
            "review",
            f"repo:{owner}/{name}",
            "post_to_github" if post_to_github else "dry_run",
        ],
        "metadata": {
            "review_id": review_id_str,
            "thread_id": thread_id,
            "repo_id": repo_id,
            "repo": f"{owner}/{name}",
            "pr_number": pr_number,
            "clerk_user_id": clerk_user_id,
        },
    }

    try:
        review_started_at = time.perf_counter()
        node_started_at: dict[str, float] = {}
        node_durations_ms: dict[str, int] = {}
        phase_timings: dict[str, int] = {}
        report_buffer: list[str] = []
        last_report_flush_at = review_started_at

        tracked_nodes = {
            "fetch_pr",
            "load_pr_history",
            "load_project_insights",
            "supervisor",
            "code_analyst",
            "security_agent",
            "semantic_security_agent",
            "architecture_agent",
            "merge_findings",
            "report_writer",
            "persist_review",
            "save_pr_memory",
            "update_project_insights",
            "post_to_github",
            "complete_review",
        }
        counted_agents = {
            "code_analyst": "code_findings",
            "security_agent": "security_findings",
            "semantic_security_agent": "semantic_security_findings",
            "architecture_agent": "arch_findings",
        }

        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            event_type = event.get("event", "")
            node_name = event.get("name", "")

            if event_type == "on_chain_start" and node_name in tracked_nodes:
                started_at = time.perf_counter()
                node_started_at[node_name] = started_at

                if node_name == "report_writer":
                    phase_timings["report_writer_started_ms"] = _elapsed_ms(review_started_at, started_at)
                elif node_name == "post_to_github":
                    phase_timings["post_to_github_started_ms"] = _elapsed_ms(review_started_at, started_at)
                elif node_name == "complete_review":
                    phase_timings["complete_review_started_ms"] = _elapsed_ms(review_started_at, started_at)

                await push_event(redis, review_id_str, StreamEvent(
                    event="agent_start", agent=node_name
                ))

            elif event_type == "on_chain_end" and node_name == "merge_findings":
                finished_at = time.perf_counter()
                started_at = node_started_at.get(node_name)
                if started_at is not None:
                    node_durations_ms[node_name] = _elapsed_ms(started_at, finished_at)
                phase_timings["merge_findings_completed_ms"] = _elapsed_ms(review_started_at, finished_at)

                output = event.get("data", {}).get("output", {})
                findings_raw = output.get("merged_findings", [])
                await push_event(redis, review_id_str, StreamEvent(
                    event="findings_ready",
                    data={"findings": [f.model_dump() if hasattr(f, "model_dump") else f for f in findings_raw]},
                ))

            elif event_type == "on_chain_end" and node_name == "report_writer":
                finished_at = time.perf_counter()
                started_at = node_started_at.get(node_name)
                data = {}
                if started_at is not None:
                    duration_ms = _elapsed_ms(started_at, finished_at)
                    node_durations_ms[node_name] = duration_ms
                    data["elapsed_ms"] = duration_ms

                output = event.get("data", {}).get("output", {})
                report_text = _extract_report_text(output)
                if report_text:
                    await _flush_report_buffer(redis, review_id_str, report_buffer)
                    phase_timings["report_ready_ms"] = _elapsed_ms(review_started_at, finished_at)
                    await push_event(
                        redis,
                        review_id_str,
                        StreamEvent(
                            event="report_ready",
                            agent="report_writer",
                            data={
                                "report": report_text,
                                "timings": dict(phase_timings),
                            },
                        ),
                    )

                await push_event(
                    redis,
                    review_id_str,
                    StreamEvent(event="agent_complete", agent="report_writer", data=data),
                )

            elif event_type == "on_chain_end" and node_name in tracked_nodes:
                finished_at = time.perf_counter()
                output = event.get("data", {}).get("output", {})
                findings_key = counted_agents.get(node_name)
                data = {}
                started_at = node_started_at.get(node_name)
                if started_at is not None:
                    duration_ms = _elapsed_ms(started_at, finished_at)
                    node_durations_ms[node_name] = duration_ms
                    data["elapsed_ms"] = duration_ms
                if findings_key:
                    data["count"] = len(output.get(findings_key, []))
                if node_name == "post_to_github":
                    phase_timings["post_to_github_completed_ms"] = _elapsed_ms(review_started_at, finished_at)
                elif node_name == "complete_review":
                    phase_timings["complete_review_completed_ms"] = _elapsed_ms(review_started_at, finished_at)
                await push_event(
                    redis,
                    review_id_str,
                    StreamEvent(event="agent_complete", agent=node_name, data=data),
                )

            elif event_type == "on_chat_model_stream":
                source_node = _get_stream_source_node(event)
                if source_node != "report_writer":
                    continue

                chunk = event.get("data", {}).get("chunk")
                token_text = _extract_stream_token_text(getattr(chunk, "content", None)) if chunk else None
                if token_text:
                    phase_timings.setdefault("first_report_token_ms", _elapsed_ms(review_started_at))
                    report_buffer.append(token_text)
                    now = time.perf_counter()
                    if _should_flush_report_buffer("".join(report_buffer), last_report_flush_at, now):
                        await _flush_report_buffer(redis, review_id_str, report_buffer)
                        last_report_flush_at = now

        final_state = await graph.aget_state(config)
        values = final_state.values if final_state else {}

        report_md = values.get("final_report") if isinstance(values, dict) else getattr(values, "final_report", None)
        github_url = values.get("github_comment_url") if isinstance(values, dict) else getattr(values, "github_comment_url", None)
        error_message = values.get("error") if isinstance(values, dict) else getattr(values, "error", None)
        agent_status = values.get("agent_status", {}) if isinstance(values, dict) else getattr(values, "agent_status", {})
        fetch_status = agent_status.get("fetch_pr", {}).get("status") if isinstance(agent_status, dict) else None

        if error_message or fetch_status == "failed":
            failure_message = error_message or agent_status.get("fetch_pr", {}).get("error") or "Review failed before PR context could be fetched"
            async with AsyncSessionLocal() as db:
                await update_review_status(db, review_id, "failed", error_message=failure_message)
            await set_status(redis, review_id_str, "failed")
            await push_event(redis, review_id_str, StreamEvent(
                event="error", data={"message": failure_message}
            ))
            log.error("Review completed with failed fetch context", review_id=review_id_str, error=failure_message)
            return

        from src.services.outcomes import review_outcome
        outcome = review_outcome(agent_status)
        await set_status(redis, review_id_str, outcome)
        phase_timings.setdefault("review_completed_ms", _elapsed_ms(review_started_at))
        await push_event(redis, review_id_str, StreamEvent(
            event="complete",
            data={
                "github_url": github_url,
                "report": report_md,
                "status": outcome,
                "timings": dict(phase_timings),
                "node_durations_ms": dict(node_durations_ms),
            },
        ))
        log.info(
            "Review completed",
            review_id=review_id_str,
            timings=phase_timings,
            node_durations_ms=node_durations_ms,
        )

    except Exception as e:
        log.error("Review graph failed", review_id=review_id_str, error=str(e))
        async with AsyncSessionLocal() as db:
            await update_review_status(db, review_id, "failed", error_message=str(e))
        await set_status(redis, review_id_str, "failed")
        await push_event(redis, review_id_str, StreamEvent(
            event="error", data={"message": str(e)}
        ))
