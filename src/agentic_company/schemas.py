"""Pydantic schemas for structured agent I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentic_company.roles.registry import RoleId

InstagramFormat = Literal["single", "carousel", "reel_script"]
LinkedInFormat = Literal["text", "single_image", "carousel_document", "poll"]


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
    deliverable_kind: Literal[
        "software",
        "instagram_posts",
        "linkedin_posts",
        "github_issue",
        "mixed",
    ] = Field(
        default="software",
        description="Primary deliverable type inferred from the brief",
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


class CarouselSlide(BaseModel):
    order: int
    headline: str = ""
    body: str = ""
    image_prompt: str = ""


class InstagramPost(BaseModel):
    """Canonical Instagram post package written by the Builder."""

    id: str = Field(description="Slug id, e.g. post-01-hook")
    platform: Literal["instagram"] = "instagram"
    format: InstagramFormat = "single"
    hook: str = Field(description="First line / scroll-stopper")
    caption: str = Field(description="Full caption including line breaks")
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    alt_text: str = ""
    image_prompts: list[str] = Field(
        default_factory=list,
        description="Detailed prompts for image generation (1 for single, N for carousel)",
    )
    carousel_slides: list[CarouselSlide] = Field(default_factory=list)
    tone: str = ""
    audience: str = ""
    notes: str = ""


class InstagramCampaign(BaseModel):
    title: str
    brand: str = ""
    goal: str = ""
    posts: list[InstagramPost]


INSTAGRAM_POST_FILE_GUIDE = """
For Instagram deliverables, write files under posts/:
  posts/README.md                 — campaign overview (goal, audience, posting order)
  posts/<id>/post.json            — InstagramPost JSON (required)
  posts/<id>/caption.txt          — caption plain text (required)
  posts/<id>/image_prompt.txt     — primary visual prompt (required for single/reel)
  posts/<id>/slides.md            — carousel slide copy if format=carousel

post.json must match InstagramPost fields: id, platform, format, hook, caption, cta,
hashtags, alt_text, image_prompts, carousel_slides, tone, audience, notes.
Do not generate binary images; image_prompts are text for a designer/generator.
""".strip()


class LinkedInPost(BaseModel):
    """Canonical LinkedIn post package written by the Builder."""

    id: str = Field(description="Slug id, e.g. post-01-thought-leadership")
    platform: Literal["linkedin"] = "linkedin"
    format: LinkedInFormat = "text"
    hook: str = Field(description="Opening hook line (first ~140 chars matter most)")
    body: str = Field(description="Full post body with line breaks")
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    mention_targets: list[str] = Field(
        default_factory=list,
        description="People/companies to mention (names or @handles)",
    )
    image_prompts: list[str] = Field(
        default_factory=list,
        description="Visual prompts for image or document-carousel slides",
    )
    carousel_slides: list[CarouselSlide] = Field(
        default_factory=list,
        description="Document carousel pages when format=carousel_document",
    )
    poll_options: list[str] = Field(
        default_factory=list,
        description="2-4 poll options when format=poll",
    )
    tone: str = ""
    audience: str = ""
    goal: str = Field(default="", description="e.g. awareness, leads, hiring")
    notes: str = ""


class LinkedInCampaign(BaseModel):
    title: str
    brand: str = ""
    goal: str = ""
    posts: list[LinkedInPost]


LINKEDIN_POST_FILE_GUIDE = """
For LinkedIn deliverables, write files under linkedin_posts/:
  linkedin_posts/README.md              — campaign overview (goal, audience, posting order)
  linkedin_posts/<id>/post.json         — LinkedInPost JSON (required)
  linkedin_posts/<id>/body.txt          — full post body (required)
  linkedin_posts/<id>/image_prompt.txt  — visual prompt when image/carousel
  linkedin_posts/<id>/slides.md         — document carousel pages if applicable

post.json fields: id, platform, format (text|single_image|carousel_document|poll),
hook, body, cta, hashtags, mention_targets, image_prompts, carousel_slides,
poll_options, tone, audience, goal, notes.
Prefer professional tone, strong first line, short paragraphs, clear CTA.
Do not generate binary images.
""".strip()
