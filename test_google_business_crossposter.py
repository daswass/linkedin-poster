import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, mock

import google_business_crossposter as crossposter


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class GoogleBusinessCrossposterTests(TestCase):
    def test_eligible_posts_only_accepts_new_linkedin_publications(self):
        start = datetime(2026, 10, 25, tzinfo=timezone.utc)
        posts = [
            {"linkedInPostId": "new", "postedAt": "2026-10-25T01:00:00Z", "content": "New"},
            {"linkedInPostId": "old", "postedAt": "2026-10-24T23:59:59Z", "content": "Old"},
            {"linkedInPostId": "done", "postedAt": "2026-10-25T01:00:00Z", "content": "Done", "googleBusinessPostId": "gbp"},
            {"postedAt": "2026-10-25T01:00:00Z", "content": "No LinkedIn ID"},
        ]
        self.assertEqual([post["linkedInPostId"] for post in crossposter.eligible_posts(posts, start)], ["new"])

    def test_create_local_post_uses_standard_post_and_optional_cta(self):
        post = {"content": "A concise post"}
        session = FakeSession(FakeResponse(200, {"name": "accounts/a/locations/l/localPosts/p"}))
        with mock.patch.dict("os.environ", {
            "GOOGLE_BUSINESS_ACCOUNT_ID": "a",
            "GOOGLE_BUSINESS_LOCATION_ID": "l",
            "GOOGLE_BUSINESS_CTA_URL": "https://example.com",
        }, clear=False):
            result = crossposter.create_local_post(post, "token", session)
        self.assertEqual(result, "accounts/a/locations/l/localPosts/p")
        args, kwargs = session.calls[0]
        self.assertTrue(args[0].endswith("/accounts/a/locations/l/localPosts"))
        self.assertEqual(kwargs["json"]["topicType"], "STANDARD")
        self.assertEqual(kwargs["json"]["callToAction"]["actionType"], "LEARN_MORE")

    def test_save_posts_is_valid_json(self):
        path = Path(self.id().replace(".", "_"))
        # This test only exercises serialization via a temporary directory.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "posts.json"
            crossposter.save_posts([{"content": "ok"}], target)
            self.assertEqual(json.loads(target.read_text()), [{"content": "ok"}])
