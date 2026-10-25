#!/usr/bin/env python3
"""Cross-post newly published LinkedIn posts to a Google Business Profile."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from dateutil import parser as date_parser
from dotenv import load_dotenv

GOOGLE_BUSINESS_SCOPE = "https://www.googleapis.com/auth/business.manage"

ROOT = Path(__file__).resolve().parent
POSTS_PATH = ROOT / "posts.json"
load_dotenv(ROOT / ".env")

API_BASE = os.getenv("GOOGLE_BUSINESS_API_BASE", "https://mybusiness.googleapis.com/v4")
TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_SUMMARY_LENGTH = 1500


def parse_timestamp(value):
    if not value:
        return None
    parsed = date_parser.isoparse(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_posts(path=POSTS_PATH):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict) and isinstance(data.get("posts"), list):
        return data["posts"], data
    raise ValueError("posts.json must be an array or an object containing a posts array")


def save_posts(container, path=POSTS_PATH):
    """Atomically persist state so a successful Google post is never silently lost."""
    directory = path.parent
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(container, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def google_access_token(session=requests):
    access_token = os.getenv("GOOGLE_BUSINESS_ACCESS_TOKEN")
    if access_token:
        return access_token

    refresh_token = os.getenv("GOOGLE_BUSINESS_REFRESH_TOKEN")
    client_id = os.getenv("GOOGLE_BUSINESS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_BUSINESS_CLIENT_SECRET")
    if all((refresh_token, client_id, client_secret)):
        response = session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Google OAuth refresh failed (HTTP {response.status_code}): {response.text[:300]}")
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("Google OAuth refresh response did not contain access_token")
        return token

    try:
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=[GOOGLE_BUSINESS_SCOPE])
        credentials.refresh(Request())
        if credentials.token:
            return credentials.token
    except Exception as error:
        raise RuntimeError(
            "Google Business credentials are incomplete. Run `gcloud auth application-default login "
            "--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/business.manage` "
            "or configure GOOGLE_BUSINESS_CLIENT_ID, GOOGLE_BUSINESS_CLIENT_SECRET, and "
            f"GOOGLE_BUSINESS_REFRESH_TOKEN. ({error})"
        ) from error

    raise RuntimeError("Google Application Default Credentials did not provide an access token")


def eligible_posts(posts, start_at):
    candidates = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        if not post.get("linkedInPostId") or post.get("googleBusinessPostId"):
            continue
        published_at = parse_timestamp(post.get("postedAt"))
        if published_at is None or published_at < start_at:
            continue
        content = (post.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_SUMMARY_LENGTH:
            raise ValueError(
                f"LinkedIn post {post.get('linkedInPostId')} is {len(content)} characters; "
                f"Google Business posts allow at most {MAX_SUMMARY_LENGTH}. Edit it before retrying."
            )
        candidates.append(post)
    return candidates


def create_local_post(post, access_token, session=requests):
    account_id = os.getenv("GOOGLE_BUSINESS_ACCOUNT_ID")
    location_id = os.getenv("GOOGLE_BUSINESS_LOCATION_ID")
    if not account_id or not location_id:
        raise RuntimeError("Set GOOGLE_BUSINESS_ACCOUNT_ID and GOOGLE_BUSINESS_LOCATION_ID.")

    url = f"{API_BASE}/accounts/{account_id}/locations/{location_id}/localPosts"
    payload = {
        "languageCode": os.getenv("GOOGLE_BUSINESS_LANGUAGE_CODE", "en-US"),
        "summary": post["content"].strip(),
        "topicType": "STANDARD",
    }
    cta_url = os.getenv("GOOGLE_BUSINESS_CTA_URL")
    if cta_url:
        payload["callToAction"] = {
            "actionType": os.getenv("GOOGLE_BUSINESS_CTA_TYPE", "LEARN_MORE"),
            "url": cta_url,
        }

    response = session.post(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Google Business post failed (HTTP {response.status_code}): {response.text[:500]}")
    post_id = response.json().get("name")
    if not post_id:
        raise RuntimeError("Google Business response did not include the local post name")
    return post_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show eligible posts without calling Google or changing posts.json.")
    args = parser.parse_args(argv)

    start_at_value = os.getenv("GOOGLE_BUSINESS_CROSSPOST_START_AT")
    if not start_at_value:
        print("No cross-post watermark configured; nothing will be published.")
        print("Set GOOGLE_BUSINESS_CROSSPOST_START_AT to the UTC timestamp when cross-posting begins.")
        return 0
    start_at = parse_timestamp(start_at_value)
    if start_at is None:
        raise ValueError("GOOGLE_BUSINESS_CROSSPOST_START_AT must be an ISO-8601 timestamp")

    posts, container = load_posts()
    candidates = eligible_posts(posts, start_at)
    print(f"Eligible LinkedIn posts: {len(candidates)}")
    for post in candidates:
        print(f"- {post['linkedInPostId']}: {post.get('postingDate', 'unscheduled')} — {post['content'][:72]}")

    if args.dry_run:
        print("DRY RUN: no Google Business posts created and posts.json unchanged.")
        return 0
    if not candidates:
        return 0

    token = google_access_token()
    for post in candidates:
        google_post_id = create_local_post(post, token)
        post["googleBusinessPostId"] = google_post_id
        post["googleBusinessPostedAt"] = datetime.now(timezone.utc).isoformat()
        save_posts(container)
        print(f"Cross-posted {post['linkedInPostId']} -> {google_post_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
