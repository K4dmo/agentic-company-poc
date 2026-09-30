"""LinkedIn Share on LinkedIn (UGC Posts) client.

Based on:
https://learn.microsoft.com/en-gb/linkedin/consumer/integrations/self-serve/share-on-linkedin
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API = "https://api.linkedin.com/v2"


def _token() -> str:
    return (
        os.getenv("LINKEDIN_ACCESS_TOKEN")
        or os.getenv("LINKEDIN_OAUTH_TOKEN")
        or ""
    ).strip()


def _headers(token: str | None = None, *, json_body: bool = False) -> dict[str, str]:
    tok = token or _token()
    headers = {
        "Authorization": f"Bearer {tok}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, dict[str, str], bytes]:
    body = data
    hdrs = headers or _headers(token, json_body=payload is not None)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read()
        raise RuntimeError(
            f"LinkedIn API {exc.code} {method} {url}: {err.decode('utf-8', errors='replace')[:1000]}"
        ) from exc


def resolve_person_urn(token: str | None = None) -> str:
    """Resolve authenticated member Person URN (urn:li:person:...)."""
    configured = (os.getenv("LINKEDIN_PERSON_URN") or "").strip()
    if configured:
        return configured if configured.startswith("urn:li:person:") else f"urn:li:person:{configured}"

    tok = token or _token()
    if not tok:
        raise RuntimeError(
            "LINKEDIN_ACCESS_TOKEN is required to publish. "
            "Create a token with w_member_social (Share on LinkedIn product)."
        )

    # OpenID Connect userinfo (preferred with Sign In with LinkedIn)
    try:
        status, _, raw = _request("GET", f"{API}/userinfo", token=tok, headers=_headers(tok))
        if status < 400:
            data = json.loads(raw.decode("utf-8"))
            sub = data.get("sub")
            if sub:
                return sub if str(sub).startswith("urn:li:person:") else f"urn:li:person:{sub}"
    except Exception:  # noqa: BLE001
        pass

    # Legacy me endpoint
    status, _, raw = _request(
        "GET",
        f"{API}/me",
        token=tok,
        headers=_headers(tok),
    )
    data = json.loads(raw.decode("utf-8"))
    person_id = data.get("id")
    if not person_id:
        raise RuntimeError("Could not resolve LinkedIn person URN from /userinfo or /me")
    return f"urn:li:person:{person_id}"


def register_image_upload(person_urn: str, *, token: str | None = None) -> dict[str, str]:
    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": person_urn,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }
    _, _, raw = _request(
        "POST",
        f"{API}/assets?action=registerUpload",
        token=token,
        payload=payload,
    )
    data = json.loads(raw.decode("utf-8"))
    value = data.get("value") or {}
    mechanism = value.get("uploadMechanism") or {}
    upload = mechanism.get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest") or {}
    upload_url = upload.get("uploadUrl")
    asset = value.get("asset")
    if not upload_url or not asset:
        raise RuntimeError(f"LinkedIn registerUpload missing uploadUrl/asset: {data}")
    return {"upload_url": upload_url, "asset": asset}


def upload_image_file(upload_url: str, image_path: Path, *, token: str | None = None) -> None:
    content = image_path.read_bytes()
    ctype = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    headers = {
        "Authorization": f"Bearer {token or _token()}",
        "Content-Type": ctype,
    }
    # LinkedIn docs use --upload-file (PUT-like binary upload to uploadUrl)
    req = urllib.request.Request(upload_url, data=content, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"Image upload failed with status {resp.status}")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LinkedIn image upload {exc.code}: {err[:800]}") from exc


def create_ugc_post(
    *,
    text: str,
    person_urn: str | None = None,
    visibility: str = "PUBLIC",
    article_url: str | None = None,
    article_title: str | None = None,
    article_description: str | None = None,
    image_asset: str | None = None,
    image_title: str | None = None,
    image_description: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create a LinkedIn share via POST /v2/ugcPosts."""
    author = person_urn or resolve_person_urn(token)
    vis = visibility.upper()
    if vis not in {"PUBLIC", "CONNECTIONS"}:
        vis = "PUBLIC"

    share_content: dict[str, Any] = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": "NONE",
    }

    if image_asset:
        share_content["shareMediaCategory"] = "IMAGE"
        share_content["media"] = [
            {
                "status": "READY",
                "description": {"text": image_description or ""},
                "media": image_asset,
                "title": {"text": image_title or "Image"},
            }
        ]
    elif article_url:
        share_content["shareMediaCategory"] = "ARTICLE"
        share_content["media"] = [
            {
                "status": "READY",
                "description": {"text": article_description or ""},
                "originalUrl": article_url,
                "title": {"text": article_title or article_url},
            }
        ]

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": vis},
    }
    status, headers, raw = _request(
        "POST",
        f"{API}/ugcPosts",
        token=token,
        payload=payload,
    )
    rest_id = headers.get("X-RestLi-Id") or headers.get("x-restli-id") or ""
    return {
        "ok": True,
        "status": status,
        "ugc_post_id": rest_id,
        "author": author,
        "visibility": vis,
        "share_media_category": share_content["shareMediaCategory"],
        "raw_headers": {k: v for k, v in headers.items() if k.lower().startswith("x-")},
        "body": raw.decode("utf-8", errors="replace")[:2000] if raw else "",
    }


def publish_share(
    *,
    text: str,
    image_path: str | Path | None = None,
    article_url: str | None = None,
    article_title: str | None = None,
    visibility: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """High-level publish: optional image upload, then ugcPosts create."""
    tok = token or _token()
    if not tok:
        return {
            "ok": False,
            "error": (
                "LINKEDIN_ACCESS_TOKEN missing. Add Share on LinkedIn (w_member_social) "
                "and set the member access token in .env"
            ),
        }

    try:
        person = resolve_person_urn(tok)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    vis = (visibility or os.getenv("LINKEDIN_VISIBILITY", "PUBLIC")).upper()
    image_asset = None
    resolved_image: Path | None = None
    if image_path:
        resolved_image = Path(image_path).expanduser().resolve()
        if not resolved_image.is_file():
            return {"ok": False, "error": f"Image not found: {resolved_image}"}
        try:
            reg = register_image_upload(person, token=tok)
            upload_image_file(reg["upload_url"], resolved_image, token=tok)
            image_asset = reg["asset"]
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Image upload failed: {exc}"}

    try:
        result = create_ugc_post(
            text=text,
            person_urn=person,
            visibility=vis,
            article_url=article_url,
            article_title=article_title,
            image_asset=image_asset,
            image_title=resolved_image.name if resolved_image else None,
            token=tok,
        )
        if image_asset:
            result["image_asset"] = image_asset
            result["image_path"] = str(resolved_image)
        if article_url:
            result["article_url"] = article_url
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
