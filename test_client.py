#!/usr/bin/env -S uv run
"""Unit Tests for Bitly API Client.

This module provides mock-based unit tests for BitlyClient in client.py.
It verifies authentication checking, URL routing, error code translations,
and parsing behavior for responses, groups, links, and click analytics.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from client import (
    BitlyAPIError,
    BitlyAuthenticationError,
    BitlyClient,
    BitlyForbiddenError,
    BitlyNotFoundError,
    BitlyRateLimitError,
    BitlyUpgradeRequiredError,
)


class TestBitlyClient(unittest.TestCase):
    """Test suite for the BitlyClient class."""

    def setUp(self):
        """Set up test instances with a mock session."""
        self.mock_session = MagicMock(spec=requests.Session)
        self.mock_session.headers = {}
        self.token = "test_bitly_token_abc123"
        self.client = BitlyClient(token=self.token, session=self.mock_session)

    def test_init_raises_on_empty_token(self):
        """Verify client instantiation fails with empty tokens."""
        with self.assertRaises(ValueError):
            BitlyClient("")
        with self.assertRaises(ValueError):
            BitlyClient("   ")

    def test_init_sets_correct_headers(self):
        """Verify client sets API authorization and formatting headers."""
        self.assertEqual(
            self.mock_session.headers["Authorization"], f"Bearer {self.token}"
        )
        self.assertEqual(
            self.mock_session.headers["Accept"], "application/json"
        )
        self.assertEqual(
            self.mock_session.headers["Content-Type"], "application/json"
        )
        self.assertIn("User-Agent", self.mock_session.headers)

    def test_request_success(self):
        """Verify request method parses and returns JSON on status code 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "test_user"}
        self.mock_session.request.return_value = mock_response

        result = self.client._request("GET", "/user")
        self.assertEqual(result, {"login": "test_user"})
        self.mock_session.request.assert_called_once_with(
            "GET", "https://api-ssl.bitly.com/v4/user", timeout=15
        )

    def test_request_raises_auth_error_on_401(self):
        """Verify HTTP 401 returns BitlyAuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyAuthenticationError):
            self.client._request("GET", "/user")

    def test_request_raises_upgrade_required_on_402(self):
        """Verify HTTP 402 returns BitlyUpgradeRequiredError."""
        mock_response = MagicMock()
        mock_response.status_code = 402
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyUpgradeRequiredError):
            self.client._request("GET", "/bitlinks/bit.ly/123/clicks/summary")

    def test_request_raises_forbidden_on_403(self):
        """Verify HTTP 403 returns BitlyForbiddenError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyForbiddenError):
            self.client._request("GET", "/user")

    def test_request_raises_not_found_on_404(self):
        """Verify HTTP 404 returns BitlyNotFoundError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyNotFoundError):
            self.client._request("GET", "/bitlinks/invalid_link")

    def test_request_raises_rate_limit_on_429(self):
        """Verify HTTP 429 returns BitlyRateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyRateLimitError):
            self.client._request("GET", "/user")

    def test_request_raises_general_api_error(self):
        """Verify general status codes raise BitlyAPIError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        self.mock_session.request.return_value = mock_response

        with self.assertRaises(BitlyAPIError):
            self.client._request("GET", "/user")

    def test_get_user(self):
        """Verify get_user hits correct endpoint and parses result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "alexoat76"}
        self.mock_session.request.return_value = mock_response

        result = self.client.get_user()
        self.assertEqual(result, {"login": "alexoat76"})
        self.mock_session.request.assert_called_once_with(
            "GET", "https://api-ssl.bitly.com/v4/user", timeout=15
        )

    def test_list_groups(self):
        """Verify list_groups returns groups array."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "groups": [{"guid": "G1", "name": "Org"}]
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.list_groups()
        self.assertEqual(result, [{"guid": "G1", "name": "Org"}])

    def test_list_bitlinks(self):
        """Verify list_bitlinks passes pagination params."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"links": []}
        self.mock_session.request.return_value = mock_response

        self.client.list_bitlinks("G123", page=2, size=20)
        self.mock_session.request.assert_called_once_with(
            "GET",
            "https://api-ssl.bitly.com/v4/groups/G123/bitlinks",
            timeout=15,
            params={"page": 2, "size": 20},
        )

    def test_shorten_url_without_title(self):
        """Verify shorten_url sends proper payload and ignores PATCH."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "bit.ly/3abc",
            "link": "https://bit.ly/3abc",
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.shorten_url(
            "https://example.com", group_guid="G123"
        )
        self.assertEqual(result["id"], "bit.ly/3abc")
        self.mock_session.request.assert_called_once_with(
            "POST",
            "https://api-ssl.bitly.com/v4/shorten",
            timeout=15,
            json={"long_url": "https://example.com", "group_guid": "G123"},
        )

    @patch.object(BitlyClient, "update_bitlink")
    def test_shorten_url_with_title(self, mock_update):
        """Verify shorten_url performs PATCH when title is specified."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "bit.ly/3abc",
            "link": "https://bit.ly/3abc",
        }
        self.mock_session.request.return_value = mock_response
        mock_update.return_value = {"id": "bit.ly/3abc", "title": "My Title"}

        result = self.client.shorten_url(
            "https://example.com", title="My Title"
        )
        self.assertEqual(result["title"], "My Title")
        mock_update.assert_called_once_with("bit.ly/3abc", title="My Title")

    def test_get_click_summary(self):
        """Verify get_click_summary passes parameters properly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_clicks": 42}
        self.mock_session.request.return_value = mock_response

        result = self.client.get_click_summary(
            "bit.ly/3abc", unit="week", units=4
        )
        self.assertEqual(result["total_clicks"], 42)
        self.mock_session.request.assert_called_once_with(
            "GET",
            "https://api-ssl.bitly.com/v4/bitlinks/bit.ly/3abc/clicks/summary",
            timeout=15,
            params={"unit": "week", "units": 4},
        )

    def test_request_connection_error(self):
        """Verify RequestException translates to BitlyAPIError."""
        self.mock_session.request.side_effect = (
            requests.exceptions.ConnectionError("Connection Refused")
        )
        with self.assertRaises(BitlyAPIError):
            self.client._request("GET", "/user")

    def test_get_bitlink_details(self):
        """Verify get_bitlink_details fetches properly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "bit.ly/3abc",
            "title": "Details",
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.get_bitlink_details("bit.ly/3abc")
        self.assertEqual(result["title"], "Details")
        self.mock_session.request.assert_called_once_with(
            "GET",
            "https://api-ssl.bitly.com/v4/bitlinks/bit.ly/3abc",
            timeout=15,
        )

    def test_update_bitlink(self):
        """Verify update_bitlink sends PATCH."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "bit.ly/3abc",
            "title": "New Title",
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.update_bitlink("bit.ly/3abc", title="New Title")
        self.assertEqual(result["title"], "New Title")
        self.mock_session.request.assert_called_once_with(
            "PATCH",
            "https://api-ssl.bitly.com/v4/bitlinks/bit.ly/3abc",
            timeout=15,
            json={"title": "New Title"},
        )

    def test_get_referrers(self):
        """Verify get_referrers fetches properly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "metrics": [{"value": "direct", "clicks": 10}]
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.get_referrers("bit.ly/3abc")
        self.assertEqual(result["metrics"][0]["value"], "direct")
        self.mock_session.request.assert_called_once_with(
            "GET",
            "https://api-ssl.bitly.com/v4/bitlinks/bit.ly/3abc/referrers",
            timeout=15,
            params={"unit": "day", "units": -1},
        )

    def test_get_countries(self):
        """Verify get_countries fetches properly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "metrics": [{"value": "US", "clicks": 15}]
        }
        self.mock_session.request.return_value = mock_response

        result = self.client.get_countries("bit.ly/3abc")
        self.assertEqual(result["metrics"][0]["value"], "US")
        self.mock_session.request.assert_called_once_with(
            "GET",
            "https://api-ssl.bitly.com/v4/bitlinks/bit.ly/3abc/countries",
            timeout=15,
            params={"unit": "day", "units": -1},
        )


if __name__ == "__main__":
    unittest.main()
