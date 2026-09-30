"""Fixed specialist role registry — allowlisted hiring only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RoleId = Literal["tester", "docs_writer", "security_reviewer"]

ALLOWED_ROLES: tuple[RoleId, ...] = ("tester", "docs_writer", "security_reviewer")


@dataclass(frozen=True)
class RoleSpec:
    id: RoleId
    title: str
    focus: str


REGISTRY: dict[RoleId, RoleSpec] = {
    "tester": RoleSpec(
        id="tester",
        title="Tester",
        focus="Test strategy, edge cases, pytest layout, assertions to require",
    ),
    "docs_writer": RoleSpec(
        id="docs_writer",
        title="Docs Writer",
        focus="README structure, usage examples, API docs the builder should include",
    ),
    "security_reviewer": RoleSpec(
        id="security_reviewer",
        title="Security Reviewer",
        focus="Input validation, injection, secrets, unsafe subprocess/path usage",
    ),
}


def normalize_hired(roles: list[str] | None) -> list[RoleId]:
    if not roles:
        return []
    out: list[RoleId] = []
    for role in roles:
        if role in REGISTRY and role not in out:
            out.append(role)  # type: ignore[arg-type]
    return out


def describe_registry() -> str:
    lines = [f"- {spec.id}: {spec.focus}" for spec in REGISTRY.values()]
    return "\n".join(lines)
