"""Builder tools specialized for Instagram post packages."""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.schemas import CarouselSlide, InstagramFormat, InstagramPost
from agentic_company.tools.filesystem import resolve_in_workspace


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return text[:60] or "post"


def make_instagram_builder_tools(workspace_root: str) -> list[StructuredTool]:
    root = Path(workspace_root).resolve()

    class WritePostArgs(BaseModel):
        id: str = Field(description="Slug id, e.g. post-01-energy-hook")
        format: InstagramFormat = "single"
        hook: str
        caption: str
        cta: str = ""
        hashtags: list[str] = Field(default_factory=list)
        alt_text: str = ""
        image_prompts: list[str] = Field(default_factory=list)
        carousel_slides: list[CarouselSlide] = Field(default_factory=list)
        tone: str = ""
        audience: str = ""
        notes: str = ""

    class CampaignArgs(BaseModel):
        title: str
        brand: str = ""
        goal: str = ""
        audience: str = ""
        posting_order: list[str] = Field(
            default_factory=list,
            description="Ordered list of post ids",
        )

    class Empty(BaseModel):
        pass

    def write_instagram_post(
        id: str,
        hook: str,
        caption: str,
        format: InstagramFormat = "single",
        cta: str = "",
        hashtags: list[str] | None = None,
        alt_text: str = "",
        image_prompts: list[str] | None = None,
        carousel_slides: list[dict] | list[CarouselSlide] | None = None,
        tone: str = "",
        audience: str = "",
        notes: str = "",
    ) -> str:
        post_id = _slugify(id)
        slides = []
        for slide in carousel_slides or []:
            if isinstance(slide, CarouselSlide):
                slides.append(slide)
            else:
                slides.append(CarouselSlide.model_validate(slide))
        post = InstagramPost(
            id=post_id,
            format=format,
            hook=hook,
            caption=caption,
            cta=cta,
            hashtags=hashtags or [],
            alt_text=alt_text,
            image_prompts=image_prompts or [],
            carousel_slides=slides,
            tone=tone,
            audience=audience,
            notes=notes,
        )
        if post.format == "carousel" and not post.carousel_slides:
            return "Error: carousel format requires carousel_slides"
        if not post.image_prompts and post.format != "carousel":
            return "Error: provide at least one image_prompt (or video prompt for reel_script)"
        if post.format == "carousel" and not post.image_prompts:
            post.image_prompts = [s.image_prompt for s in post.carousel_slides if s.image_prompt]

        folder = resolve_in_workspace(root, f"posts/{post_id}")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "post.json").write_text(
            json.dumps(post.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (folder / "caption.txt").write_text(post.caption, encoding="utf-8")
        primary_prompt = (post.image_prompts or [""])[0]
        (folder / "image_prompt.txt").write_text(primary_prompt, encoding="utf-8")
        if post.carousel_slides:
            lines = []
            for slide in sorted(post.carousel_slides, key=lambda s: s.order):
                lines.append(
                    f"## Slide {slide.order}: {slide.headline}\n\n"
                    f"{slide.body}\n\n"
                    f"Image prompt: {slide.image_prompt}\n"
                )
            (folder / "slides.md").write_text("\n".join(lines), encoding="utf-8")
        return f"Wrote Instagram package posts/{post_id}/ (post.json, caption.txt, image_prompt.txt)"

    def write_campaign_readme(
        title: str,
        brand: str = "",
        goal: str = "",
        audience: str = "",
        posting_order: list[str] | None = None,
    ) -> str:
        posts_dir = resolve_in_workspace(root, "posts")
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
        path = posts_dir / "README.md"
        path.write_text(body, encoding="utf-8")
        return f"Wrote posts/README.md with {len(order)} post(s) listed"

    def list_instagram_posts() -> str:
        posts_dir = root / "posts"
        if not posts_dir.is_dir():
            return "(no posts/ yet)"
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
        return "\n".join(lines) if lines else "(empty posts/)"

    return [
        StructuredTool.from_function(
            write_instagram_post,
            name="write_instagram_post",
            description=(
                "Create a validated Instagram post package under posts/<id>/ "
                "(post.json, caption.txt, image_prompt.txt, optional slides.md)"
            ),
            args_schema=WritePostArgs,
        ),
        StructuredTool.from_function(
            write_campaign_readme,
            name="write_campaign_readme",
            description="Write posts/README.md campaign overview and posting order",
            args_schema=CampaignArgs,
        ),
        StructuredTool.from_function(
            list_instagram_posts,
            name="list_instagram_posts",
            description="List Instagram packages already written under posts/",
            args_schema=Empty,
        ),
    ]
