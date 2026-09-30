"""Builder tools specialized for LinkedIn post packages."""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.schemas import CarouselSlide, LinkedInFormat, LinkedInPost
from agentic_company.tools.filesystem import resolve_in_workspace


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return text[:60] or "post"


def make_linkedin_builder_tools(workspace_root: str) -> list[StructuredTool]:
    root = Path(workspace_root).resolve()

    class WritePostArgs(BaseModel):
        id: str = Field(description="Slug id, e.g. post-01-leadership")
        format: LinkedInFormat = "text"
        hook: str
        body: str
        cta: str = ""
        hashtags: list[str] = Field(default_factory=list)
        mention_targets: list[str] = Field(default_factory=list)
        image_prompts: list[str] = Field(default_factory=list)
        carousel_slides: list[CarouselSlide] = Field(default_factory=list)
        poll_options: list[str] = Field(default_factory=list)
        tone: str = ""
        audience: str = ""
        goal: str = ""
        notes: str = ""

    class CampaignArgs(BaseModel):
        title: str
        brand: str = ""
        goal: str = ""
        audience: str = ""
        posting_order: list[str] = Field(default_factory=list)

    class Empty(BaseModel):
        pass

    def write_linkedin_post(
        id: str,
        hook: str,
        body: str,
        format: LinkedInFormat = "text",
        cta: str = "",
        hashtags: list[str] | None = None,
        mention_targets: list[str] | None = None,
        image_prompts: list[str] | None = None,
        carousel_slides: list[dict] | list[CarouselSlide] | None = None,
        poll_options: list[str] | None = None,
        tone: str = "",
        audience: str = "",
        goal: str = "",
        notes: str = "",
    ) -> str:
        post_id = _slugify(id)
        slides = []
        for slide in carousel_slides or []:
            if isinstance(slide, CarouselSlide):
                slides.append(slide)
            else:
                slides.append(CarouselSlide.model_validate(slide))

        post = LinkedInPost(
            id=post_id,
            format=format,
            hook=hook,
            body=body,
            cta=cta,
            hashtags=hashtags or [],
            mention_targets=mention_targets or [],
            image_prompts=image_prompts or [],
            carousel_slides=slides,
            poll_options=poll_options or [],
            tone=tone,
            audience=audience,
            goal=goal,
            notes=notes,
        )

        if not post.hook.strip() or not post.body.strip():
            return "Error: hook and body are required"
        if post.format == "carousel_document" and not post.carousel_slides:
            return "Error: carousel_document requires carousel_slides"
        if post.format == "single_image" and not post.image_prompts:
            return "Error: single_image requires at least one image_prompt"
        if post.format == "poll" and not (2 <= len(post.poll_options) <= 4):
            return "Error: poll format requires 2-4 poll_options"
        if post.format == "carousel_document" and not post.image_prompts:
            post.image_prompts = [s.image_prompt for s in post.carousel_slides if s.image_prompt]

        folder = resolve_in_workspace(root, f"linkedin_posts/{post_id}")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "post.json").write_text(
            json.dumps(post.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (folder / "body.txt").write_text(post.body, encoding="utf-8")
        if post.image_prompts:
            (folder / "image_prompt.txt").write_text(post.image_prompts[0], encoding="utf-8")
        if post.carousel_slides:
            lines = []
            for slide in sorted(post.carousel_slides, key=lambda s: s.order):
                lines.append(
                    f"## Page {slide.order}: {slide.headline}\n\n"
                    f"{slide.body}\n\n"
                    f"Visual: {slide.image_prompt}\n"
                )
            (folder / "slides.md").write_text("\n".join(lines), encoding="utf-8")
        if post.poll_options:
            (folder / "poll.txt").write_text(
                "\n".join(f"- {opt}" for opt in post.poll_options),
                encoding="utf-8",
            )
        return f"Wrote LinkedIn package linkedin_posts/{post_id}/"

    def write_linkedin_campaign_readme(
        title: str,
        brand: str = "",
        goal: str = "",
        audience: str = "",
        posting_order: list[str] | None = None,
    ) -> str:
        posts_dir = resolve_in_workspace(root, "linkedin_posts")
        posts_dir.mkdir(parents=True, exist_ok=True)
        order = posting_order or []
        if not order and posts_dir.exists():
            order = sorted(
                p.name for p in posts_dir.iterdir() if p.is_dir() and (p / "post.json").exists()
            )
        body = (
            f"# {title}\n\n"
            f"- Brand: {brand or '—'}\n"
            f"- Goal: {goal or '—'}\n"
            f"- Audience: {audience or '—'}\n\n"
            f"## Posting order\n"
            + ("\n".join(f"{i}. `{pid}`" for i, pid in enumerate(order, start=1)) or "1. (add posts)")
            + "\n"
        )
        (posts_dir / "README.md").write_text(body, encoding="utf-8")
        return f"Wrote linkedin_posts/README.md with {len(order)} post(s) listed"

    def list_linkedin_posts() -> str:
        posts_dir = root / "linkedin_posts"
        if not posts_dir.is_dir():
            return "(no linkedin_posts/ yet)"
        lines: list[str] = []
        for folder in sorted(posts_dir.iterdir()):
            if not folder.is_dir():
                continue
            meta = folder / "post.json"
            if not meta.is_file():
                lines.append(f"{folder.name}/ (missing post.json)")
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                lines.append(
                    f"{folder.name}/ format={data.get('format')} hook={str(data.get('hook', ''))[:60]}"
                )
            except json.JSONDecodeError:
                lines.append(f"{folder.name}/ (invalid post.json)")
        return "\n".join(lines) if lines else "(empty linkedin_posts/)"

    return [
        StructuredTool.from_function(
            write_linkedin_post,
            name="write_linkedin_post",
            description=(
                "Create a validated LinkedIn post package under linkedin_posts/<id>/ "
                "(post.json, body.txt, optional image_prompt/slides/poll)"
            ),
            args_schema=WritePostArgs,
        ),
        StructuredTool.from_function(
            write_linkedin_campaign_readme,
            name="write_linkedin_campaign_readme",
            description="Write linkedin_posts/README.md campaign overview and posting order",
            args_schema=CampaignArgs,
        ),
        StructuredTool.from_function(
            list_linkedin_posts,
            name="list_linkedin_posts",
            description="List LinkedIn packages already written under linkedin_posts/",
            args_schema=Empty,
        ),
    ]
