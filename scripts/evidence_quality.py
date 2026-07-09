from __future__ import annotations

import pathlib
import re


MIN_SUBSTANTIVE_EVIDENCE_CHARS = 80
REQUIRED_METADATA_FIELDS = (
    "Scope",
    "Owner id",
    "Recorded at",
    "Operator",
    "Command or source",
)

INCOMPLETE_PATTERNS = (
    (
        "unsigned draft",
        re.compile(
            r"\bDRAFT\b|\bdrafted via\b|pending\s+(?:operator\s+)?(?:confirmation|sign[- ]off)",
            re.IGNORECASE,
        ),
    ),
    (
        "incomplete marker",
        re.compile(
            r"\b(?:TODO|TBD|TBC|PLACEHOLDER)\b|_{4,}|"
            r"paste\s+the\s+(?:transcript|screenshot|evidence)|"
            r"passed\s*\|\s*blocked\s*\|\s*partial",
            re.IGNORECASE,
        ),
    ),
)


def markdown_metadata(content: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^\s*-\s*([^:]+):\s*(.*?)\s*$", line)
        if not match:
            continue
        metadata[match.group(1).strip()] = match.group(2).strip().strip("`")
    return metadata


def substantive_evidence_text(content: str) -> str:
    section = re.search(r"(?m)^##\s+.+\s*$", content)
    if not section:
        return ""
    body = content[section.end() :]
    return re.sub(r"[\s#*`|_\-]+", " ", body).strip()


def evidence_file_errors(
    path: pathlib.Path,
    *,
    expected_scope: str,
    expected_owner_id: str,
) -> list[str]:
    if not path.exists():
        return ["file is missing"]
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"file cannot be read as UTF-8 markdown: {exc}"]

    errors: list[str] = []
    if not content.strip():
        return ["file is empty"]

    for label, pattern in INCOMPLETE_PATTERNS:
        match = pattern.search(content)
        if match:
            errors.append(f"{label} remains: {match.group(0)!r}")

    metadata = markdown_metadata(content)
    for field in REQUIRED_METADATA_FIELDS:
        if not metadata.get(field, "").strip():
            errors.append(f"required metadata is missing or empty: {field}")

    if metadata.get("Scope") and metadata["Scope"] != expected_scope:
        errors.append(
            f"Scope metadata must be {expected_scope!r}, got {metadata['Scope']!r}"
        )
    if metadata.get("Owner id") and metadata["Owner id"] != expected_owner_id:
        errors.append(
            f"Owner id metadata must be {expected_owner_id!r}, got {metadata['Owner id']!r}"
        )

    substantive = substantive_evidence_text(content)
    if not substantive:
        errors.append("file must contain at least one level-two evidence section")
    elif len(substantive) < MIN_SUBSTANTIVE_EVIDENCE_CHARS:
        errors.append(
            "file must contain substantive evidence after a level-two heading "
            f"(at least {MIN_SUBSTANTIVE_EVIDENCE_CHARS} characters)"
        )
    return errors
