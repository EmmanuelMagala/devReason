import json

from src.services.architecture_rule_service import parse_rule_suggestions, select_representative_paths


def test_select_representative_paths_prefers_source_boundaries_over_lockfiles():
    paths = [
        "backend/package-lock.json",
        "backend/src/socket/index.ts",
        "backend/src/features/tasks/taskController.ts",
        "backend/tests/taskController.test.ts",
        "backend/package.json",
    ]

    selected = select_representative_paths(paths, limit=3)

    assert selected == [
        "backend/src/features/tasks/taskController.ts",
        "backend/src/socket/index.ts",
        "backend/package.json",
    ]


def test_parse_rule_suggestions_returns_trimmed_strings():
    raw = json.dumps([
        " Route handlers must delegate persistence to a service layer. ",
        "Realtime socket events must derive room membership from authorized server-side state.",
        "",
        123,
    ])

    assert parse_rule_suggestions(raw) == [
        "Route handlers must delegate persistence to a service layer.",
        "Realtime socket events must derive room membership from authorized server-side state.",
    ]