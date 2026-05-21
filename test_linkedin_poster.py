import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import linkedin_poster


class LinkedInTextPreparationTests(unittest.TestCase):
    def test_prepare_text_unescapes_double_escaped_quotes(self):
        text = 'The board said \\"where is the report?\\" before month-end.'

        prepared = linkedin_poster.prepare_text_for_linkedin(text)

        self.assertEqual(
            prepared,
            'The board said "where is the report?" before month-end.',
        )

    def test_post_payload_uses_clean_commentary_for_escaped_quotes(self):
        captured = {}

        def fake_post(url, json=None, headers=None):
            captured["json"] = json

            class Response:
                status_code = 201
                text = ""
                headers = {"x-restli-id": "urn:li:share:test"}

            return Response()

        with patch.object(linkedin_poster, "LINKEDIN_ACCESS_TOKEN", "token"):
            with patch.object(linkedin_poster.requests, "post", side_effect=fake_post):
                output = StringIO()
                with redirect_stdout(output):
                    post_id = linkedin_poster.post_to_linkedin(
                        'Stop writing \\"I think it was handled\\" in board updates.',
                        "urn:li:organization:123",
                    )

        self.assertEqual(post_id, "urn:li:share:test")
        self.assertEqual(
            captured["json"]["commentary"],
            'Stop writing "I think it was handled" in board updates.',
        )
        self.assertNotIn('\\"', captured["json"]["commentary"])


if __name__ == "__main__":
    unittest.main()
