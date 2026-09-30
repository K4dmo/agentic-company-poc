"""Instagram post package schema tests."""

from __future__ import annotations

from agentic_company.roles.registry import ALLOWED_ROLES, normalize_hired
from agentic_company.schemas import InstagramCampaign, InstagramPost


def test_social_roles_registered() -> None:
    assert "social_copywriter" in ALLOWED_ROLES
    assert "visual_designer" in ALLOWED_ROLES
    assert normalize_hired(["social_copywriter", "hacker"]) == ["social_copywriter"]


def test_instagram_post_roundtrip() -> None:
    post = InstagramPost(
        id="post-01",
        format="carousel",
        hook="Stop scrolling",
        caption="Body copy",
        cta="Comment YES",
        hashtags=["#launch"],
        alt_text="Product on a desk",
        image_prompts=["Soft light product shot, 4:5"],
        carousel_slides=[
            {"order": 1, "headline": "Problem", "body": "Pain", "image_prompt": "slide 1 art"},
            {"order": 2, "headline": "Fix", "body": "Solution", "image_prompt": "slide 2 art"},
        ],
        tone="bold",
        audience="founders",
    )
    campaign = InstagramCampaign(title="Launch week", brand="Acme", goal="awareness", posts=[post])
    data = campaign.model_dump()
    assert data["posts"][0]["platform"] == "instagram"
    assert len(data["posts"][0]["carousel_slides"]) == 2
