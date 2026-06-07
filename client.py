#!/usr/bin/env python3
"""Bitly API Client Module.

This module provides a world-class, robust client wrapper to interact with the
Bitly API v4, supporting authentication, user details, groups, link
shortening, link metadata retrieval, and click metrics/analytics with
detailed error handling.
"""

import logging
from typing import Any, cast

import requests

# Configure logging
logger = logging.getLogger(__name__)


class BitlyError(Exception):
    """Base exception for all Bitly API related errors."""


class BitlyAuthenticationError(BitlyError):
    """Exception raised when API authentication fails (HTTP 401)."""


class BitlyForbiddenError(BitlyError):
    """Exception raised when access is forbidden (HTTP 403)."""


class BitlyNotFoundError(BitlyError):
    """Exception raised when a requested resource is not found (HTTP 404)."""


class BitlyUpgradeRequiredError(BitlyError):
    """Exception raised when endpoint requires an upgraded plan (HTTP 402)."""


class BitlyRateLimitError(BitlyError):
    """Exception raised when API rate limits are exceeded (HTTP 429)."""


class BitlyAPIError(BitlyError):
    """Exception raised for general API failures (HTTP 4xx or 5xx)."""


class BitlyClient:
    """Client wrapper for the Bitly API v4."""

    BASE_URL = "https://api-ssl.bitly.com/v4"

    def __init__(self, token: str, session: requests.Session | None = None):
        """Initialize the Bitly API client.

        Args:
            token: The Bitly Generic Access Token.
            session: Optional pre-configured requests.Session object.

        Raises:
            ValueError: If the token is empty.

        """
        if not token or not token.strip():
            raise ValueError("Bitly Generic Access Token must not be empty.")

        self.token = token.strip()
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "BitlyReaderCLI/1.0.0",
            }
        )

    def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make an HTTP request to the Bitly API and handle errors.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.).
            endpoint: API endpoint (relative to BASE_URL).
            **kwargs: Additional arguments passed to requests.Session.request.

        Returns:
            The parsed JSON response.

        Raises:
            BitlyAuthenticationError: If the token is invalid or expired (401).
            BitlyForbiddenError: If access is forbidden (403).
            BitlyNotFoundError: If endpoint or resource does not exist (404).
            BitlyUpgradeRequiredError: If an account upgrade is needed (402).
            BitlyRateLimitError: If rate limits are exceeded (429).
            BitlyAPIError: For other network or server errors.

        """
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=15, **kwargs)
        except requests.RequestException as err:
            logger.error(f"Network error contacting Bitly API: {err}")
            raise BitlyAPIError(
                f"Network error: Unable to connect to Bitly API. {err}"
            ) from err

        if response.status_code in (200, 201):
            return cast(dict[str, Any], response.json())

        # Some endpoints return 204 No Content with no response body
        if response.status_code == 204:
            return {}

        # Handle specific error status codes
        if response.status_code == 401:
            raise BitlyAuthenticationError(
                "Authentication failed. Please verify your "
                "Bitly Generic Access Token."
            )
        elif response.status_code == 402:
            raise BitlyUpgradeRequiredError(
                "Upgrade required. Your Bitly account plan does not "
                "allow access to this resource."
            )
        elif response.status_code == 403:
            raise BitlyForbiddenError(
                "Forbidden. You do not have permissions to "
                "access this resource."
            )
        elif response.status_code == 404:
            raise BitlyNotFoundError(f"Resource not found: {endpoint}")
        elif response.status_code == 429:
            raise BitlyRateLimitError(
                "Rate limit exceeded. Bitly restricts API requests. "
                "Please try again shortly."
            )
        else:
            try:
                error_data = response.json()
                error_msg = (
                    error_data.get("description")
                    or error_data.get("message")
                    or response.text
                )
            except ValueError:
                error_msg = response.text

            raise BitlyAPIError(
                f"API Error ({response.status_code}): {error_msg}"
            )

    def get_user(self) -> dict[str, Any]:
        """Retrieve the authenticated user's profile info.

        Returns:
            The parsed JSON response from GET /user.

        """
        return self._request("GET", "/user")

    def list_groups(self) -> list[dict[str, Any]]:
        """List all groups the authenticated user belongs to.

        Returns:
            A list of group dictionaries.

        """
        response = self._request("GET", "/groups")
        return cast(list[dict[str, Any]], response.get("groups", []))

    def list_bitlinks(
        self, group_guid: str, page: int = 1, size: int = 50
    ) -> dict[str, Any]:
        """Retrieve a paginated list of bitlinks in the specified group.

        Args:
            group_guid: The GUID of the group to list bitlinks for.
            page: The page number to retrieve.
            size: The number of bitlinks per page.

        Returns:
            A dictionary containing "links" list and "pagination" metadata.

        """
        params = {"page": page, "size": size}
        return self._request(
            "GET", f"/groups/{group_guid}/bitlinks", params=params
        )

    def shorten_url(
        self,
        long_url: str,
        group_guid: str | None = None,
        domain: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Shorten a long URL into a Bitlink and optionally update its title.

        Args:
            long_url: The original long URL to shorten.
            group_guid: Optional specific group GUID.
            domain: Optional specific domain (e.g., 'bit.ly').
            title: Optional title to set on the shortened link.

        Returns:
            The shortened link metadata dictionary.

        """
        payload: dict[str, Any] = {"long_url": long_url}
        if group_guid:
            payload["group_guid"] = group_guid
        if domain:
            payload["domain"] = domain

        result = self._request("POST", "/shorten", json=payload)

        # If a title is provided, update the bitlink's title using PATCH
        if title and "id" in result:
            bitlink_id = result["id"]
            try:
                result = self.update_bitlink(bitlink_id, title=title)
            except BitlyError as err:
                logger.warning(
                    f"Successfully shortened, but failed to set title: {err}"
                )

        return result

    def get_bitlink_details(self, bitlink: str) -> dict[str, Any]:
        """Retrieve details and metadata for a specific bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').

        Returns:
            The bitlink's metadata.

        """
        return self._request("GET", f"/bitlinks/{bitlink}")

    def update_bitlink(
        self, bitlink: str, title: str | None = None
    ) -> dict[str, Any]:
        """Update fields of an existing bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').
            title: The new title to set.

        Returns:
            The updated bitlink metadata.

        """
        payload = {}
        if title is not None:
            payload["title"] = title

        return self._request("PATCH", f"/bitlinks/{bitlink}", json=payload)

    def get_click_summary(
        self,
        bitlink: str,
        unit: str = "day",
        units: int = -1,
        unit_reference: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve the aggregated click summary for a specific bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').
            unit: The time unit (minute, hour, day, week, month).
            units: The number of units to retrieve (-1 for all).
            unit_reference: An optional ISO-8601 reference timestamp.

        Returns:
            The click summary.

        """
        params: dict[str, Any] = {"unit": unit, "units": units}
        if unit_reference:
            params["unit_reference"] = unit_reference
        return self._request(
            "GET", f"/bitlinks/{bitlink}/clicks/summary", params=params
        )

    def get_clicks(
        self,
        bitlink: str,
        unit: str = "day",
        units: int = -1,
        unit_reference: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve click count history (time-series) for a specific bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').
            unit: The time unit (minute, hour, day, week, month).
            units: The number of units to retrieve (-1 for all).
            unit_reference: An optional ISO-8601 reference timestamp.

        Returns:
            The clicks over time.

        """
        params: dict[str, Any] = {"unit": unit, "units": units}
        if unit_reference:
            params["unit_reference"] = unit_reference
        return self._request(
            "GET", f"/bitlinks/{bitlink}/clicks", params=params
        )

    def get_referrers(
        self,
        bitlink: str,
        unit: str = "day",
        units: int = -1,
        unit_reference: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve click breakdown by referring domains for a bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').
            unit: The time unit (minute, hour, day, week, month).
            units: The number of units to retrieve (-1 for all).
            unit_reference: An optional ISO-8601 reference timestamp.

        Returns:
            The referrer metrics.

        """
        params: dict[str, Any] = {"unit": unit, "units": units}
        if unit_reference:
            params["unit_reference"] = unit_reference
        return self._request(
            "GET", f"/bitlinks/{bitlink}/referrers", params=params
        )

    def get_countries(
        self,
        bitlink: str,
        unit: str = "day",
        units: int = -1,
        unit_reference: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve click breakdown by geographic country for a bitlink.

        Args:
            bitlink: The shortened link (domain/hash, e.g., 'bit.ly/3abc123').
            unit: The time unit (minute, hour, day, week, month).
            units: The number of units to retrieve (-1 for all).
            unit_reference: An optional ISO-8601 reference timestamp.

        Returns:
            The country metrics.

        """
        params: dict[str, Any] = {"unit": unit, "units": units}
        if unit_reference:
            params["unit_reference"] = unit_reference
        return self._request(
            "GET", f"/bitlinks/{bitlink}/countries", params=params
        )
