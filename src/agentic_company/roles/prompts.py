"""Specialist prompt fragments."""

from agentic_company.roles.registry import REGISTRY, RoleId


def specialist_focus(role: RoleId) -> str:
    return REGISTRY[role].focus


def specialist_title(role: RoleId) -> str:
    return REGISTRY[role].title
