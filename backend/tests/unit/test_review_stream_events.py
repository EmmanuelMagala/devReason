from src.schemas.stream import StreamEvent
from src.services.review_service import (
    _elapsed_ms,
    _extract_report_text,
    _extract_stream_token_text,
    _get_stream_source_node,
    _should_flush_report_buffer,
)


def test_get_stream_source_node_prefers_langgraph_metadata():
    event = {
        "name": "ChatOpenAI",
        "metadata": {"langgraph_node": "report_writer"},
    }

    assert _get_stream_source_node(event) == "report_writer"


def test_get_stream_source_node_falls_back_to_event_name():
    event = {"name": "report_writer"}

    assert _get_stream_source_node(event) == "report_writer"


def test_extract_report_text_returns_final_report_string():
    output = {"final_report": "# Code Review Report"}

    assert _extract_report_text(output) == "# Code Review Report"


def test_extract_report_text_ignores_missing_report_payload():
    output = {"code_findings": []}

    assert _extract_report_text(output) is None


def test_extract_stream_token_text_returns_string_content():
    assert _extract_stream_token_text("hello") == "hello"


def test_extract_stream_token_text_joins_text_blocks():
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "text", "text": " world"},
    ]

    assert _extract_stream_token_text(content) == "Hello world"


def test_extract_stream_token_text_ignores_non_text_blocks():
    content = [{"type": "tool_call", "id": "1"}]

    assert _extract_stream_token_text(content) is None


def test_elapsed_ms_returns_integer_duration():
    assert _elapsed_ms(10.0, 10.2509) == 250


def test_elapsed_ms_never_returns_negative_values():
    assert _elapsed_ms(10.0, 9.5) == 0


def test_should_flush_report_buffer_on_size_threshold():
    assert _should_flush_report_buffer("x" * 180, 10.0, 10.05) is True


def test_should_flush_report_buffer_on_time_threshold():
    assert _should_flush_report_buffer("short", 10.0, 10.25) is True


def test_should_flush_report_buffer_ignores_empty_buffer():
    assert _should_flush_report_buffer("", 10.0, 11.0) is False


def test_stream_event_schema_accepts_report_specific_events():
    ready_event = StreamEvent(event="report_ready", agent="report_writer", data={"report": "done"})
    token_event = StreamEvent(event="report_token", agent="report_writer", data={"token": "#"})

    assert ready_event.event == "report_ready"
    assert token_event.event == "report_token"