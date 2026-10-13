from __future__ import annotations

from pathlib import PurePosixPath


MAX_ANALYSIS_FILES = 6
MAX_ANALYSIS_DIFF_CHARS = 12000

SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".swift", ".scala", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte", ".c", ".cpp", ".h", ".hpp", ".sh", ".ps1", ".yaml", ".yml",
}

DEPENDENCY_MANIFESTS = {
    "package.json",
    "requirements.txt",
    "poetry.lock",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "Cargo.lock",
}

LOW_SIGNAL_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
}

LOW_SIGNAL_SUFFIXES = (
    ".map",
    ".min.js",
    ".min.css",
)


def prioritize_changed_file_entries(file_entries: list[dict], limit: int = MAX_ANALYSIS_FILES) -> list[dict]:
    ranked = sorted(file_entries, key=_score_file_entry, reverse=True)
    return ranked[:limit]


def build_analysis_diff(file_entries: list[dict], limit_chars: int = MAX_ANALYSIS_DIFF_CHARS) -> str:
    chunks: list[str] = []
    remaining = limit_chars

    for entry in file_entries:
        patch = entry.get("patch")
        path = entry.get("filename")
        if not patch or not path or remaining <= 0:
            continue

        chunk = f"=== {path} ===\n{patch}\n"
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        chunks.append(chunk)
        remaining -= len(chunk)

    return "\n".join(chunks)


def _score_file_entry(entry: dict) -> tuple[int, int, int, str]:
    path = entry.get("filename", "")
    file_name = PurePosixPath(path).name
    extension = PurePosixPath(path).suffix.lower()
    status = entry.get("status")
    changes = int(entry.get("changes") or 0)
    patch = entry.get("patch")

    score = 0

    if file_name in DEPENDENCY_MANIFESTS:
        score += 70
    if extension in SOURCE_EXTENSIONS:
        score += 100
    if patch:
        score += 20
    if status == "added":
        score += 10
    if status == "removed":
        score -= 15

    if file_name in LOW_SIGNAL_FILES:
        score -= 120
    if any(path.endswith(suffix) for suffix in LOW_SIGNAL_SUFFIXES):
        score -= 80
    if "/dist/" in path or "/build/" in path or "/coverage/" in path:
        score -= 60
    if "/node_modules/" in path:
        score -= 200

    return (score, min(changes, 500), 1 if patch else 0, path)
