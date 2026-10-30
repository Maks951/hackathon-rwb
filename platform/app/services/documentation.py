"""Structural document checks. Semantic correctness still needs acceptance/runner checks."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ports import CheckResult


class DocumentRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    sections: tuple[str, ...]


class SourceDocument(BaseModel):
    name: str
    sha256: str


class DocumentationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policyVersion: str
    sources: tuple[SourceDocument, ...]
    documents: tuple[DocumentRequirement, ...]
    instructions: tuple[str, ...]


@lru_cache
def load_policy() -> DocumentationPolicy:
    path = Path(__file__).resolve().parents[1] / "resources/documentation-policy.json"
    return DocumentationPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def plain_markdown(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
        elif fence is None:
            lines.append(line)
    return "\n".join(lines)


def normalized(text: str) -> str:
    text = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", text.strip())
    return text.casefold().replace("ё", "е").strip(" :#*")


def missing_sections(text: str, required: tuple[str, ...]) -> list[str]:
    headings = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, re.M))
    populated = set()
    for i, heading in enumerate(headings):
        end = next(
            (h.start() for h in headings[i + 1 :] if len(h[1]) <= len(heading[1])), len(text)
        )
        content = re.sub(r"^#{1,6}\s+.*$", "", text[heading.end() : end], flags=re.M).strip()
        if len(content) >= 12:
            populated.add(normalized(heading[2]))
    return [name for name in required if normalized(name) not in populated]


def check_documentation(
    files: dict[str, bytes],
    spec: dict[str, Any],
    policy: DocumentationPolicy,
) -> CheckResult:
    errors = []
    texts = {}
    for requirement in policy.documents:
        data = files.get(requirement.path)
        if data is None:
            errors.append(f"{requirement.path}: missing file")
            continue
        try:
            text = plain_markdown(data.decode("utf-8"))
        except UnicodeDecodeError:
            errors.append(f"{requirement.path}: invalid UTF-8")
            continue
        texts[requirement.path] = text
        missing = missing_sections(text, requirement.sections)
        if missing:
            errors.append(f"{requirement.path}: missing/empty sections: {', '.join(missing)}")

    analysis = texts.get("docs/system-analysis.md", "")
    if analysis and not re.search(r"\bFR-\d+\b", analysis):
        errors.append("docs/system-analysis.md: missing numbered FR requirements")

    api = texts.get("docs/api.md", "")
    api_sections = next(d.sections for d in policy.documents if d.path == "docs/api.md")
    blocks = list(re.finditer(r"^##\s+(.+?)\s*$", api, re.M))
    for endpoint in spec.get("endpoints", []):
        expected = f"{endpoint.get('method', '')} {endpoint.get('path', endpoint['id'])}".strip()
        block = next(
            (i for i, h in enumerate(blocks) if normalized(h[1]) == normalized(expected)), None
        )
        if block is None:
            errors.append(f"docs/api.md: missing endpoint {expected}")
        else:
            end = blocks[block + 1].start() if block + 1 < len(blocks) else len(api)
            if missing_sections(api[blocks[block].end() : end], api_sections):
                errors.append(f"docs/api.md: incomplete endpoint {expected}")
    message = (
        "; ".join(errors) if errors else f"Required document structure: {policy.policyVersion}."
    )
    return CheckResult("documentation", not errors, message[:8192])
