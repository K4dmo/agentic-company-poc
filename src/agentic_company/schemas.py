"""Pydantic schemas for structured agent I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RoleId = Literal["tester", "docs_writer", "security_reviewer"]


class PlanOutput(BaseModel):
    plan: str = Field(description="Ordered implementation plan with scope and non-goals")
    acceptance_criteria: list[str] = Field(
        description="Checklist the critic will use to pass or fail"
    )
    file_outline: list[str] = Field(
        description="Expected relative file paths under the workspace"
    )
    hired_specialists: list[RoleId] = Field(
        default_factory=list,
        description="Optional specialists from the fixed registry to consult before building",
    )


class CritiqueOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    summary: str
    criteria_results: list[str] = Field(
        description="Per-criterion notes from acceptance_criteria"
    )
    revision_notes: list[str] = Field(
        default_factory=list,
        description="Concrete fixes for the builder when verdict is fail",
    )


class SpecialistOutput(BaseModel):
    role: RoleId
    notes: str = Field(description="Actionable guidance for the builder")
    risks: list[str] = Field(default_factory=list)


class BuilderDone(BaseModel):
    summary: str
    files_touched: list[str] = Field(default_factory=list)


class HumanDecision(BaseModel):
    action: Literal["approve", "revise", "abort"]
    brief: str | None = None
    revision_notes: str | None = None
