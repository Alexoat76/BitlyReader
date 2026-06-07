#!/usr/bin/env -S uv run
"""Unit Tests for Main Module CLI.

This module provides unit tests for main.py, testing environment configuration,
analytics enrichment, and some CLI logic.
"""

import contextlib
import os
import unittest
from unittest.mock import MagicMock, patch

from client import BitlyClient
from main import configure_env, enrich_links_with_analytics


class TestMain(unittest.TestCase):
    """Test suite for main functions."""

    @patch.dict(
        os.environ, {"BITLY_ACCESS_TOKEN": "valid_token_123"}, clear=True
    )
    @patch("main.load_dotenv")
    def test_configure_env_existing_token(self, mock_load):
        """Verify configure_env returns token if it exists in environment."""
        token = configure_env()
        self.assertEqual(token, "valid_token_123")
        mock_load.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch("main.load_dotenv")
    @patch("main.questionary.confirm")
    def test_configure_env_missing_token_user_declines(
        self, mock_confirm, mock_load
    ):
        """Verify configure_env exits if user declines setup."""
        mock_confirm_instance = MagicMock()
        mock_confirm_instance.ask.return_value = False
        mock_confirm.return_value = mock_confirm_instance

        with self.assertRaises(SystemExit) as cm:
            configure_env()
        self.assertEqual(cm.exception.code, 1)

    @patch("main.track")
    def test_enrich_links_with_analytics(self, mock_track):
        """Verify enrich_links_with_analytics populates fields properly."""
        mock_client = MagicMock(spec=BitlyClient)
        mock_client.get_click_summary.return_value = {"total_clicks": 100}
        mock_client.get_referrers.return_value = {
            "metrics": [{"value": "direct", "clicks": 50}]
        }
        mock_client.get_countries.return_value = {
            "metrics": [{"value": "US", "clicks": 50}]
        }

        # Mock track to just return the iterable
        mock_track.side_effect = lambda it, **kwargs: it

        links = [{"id": "bit.ly/123"}]
        enriched = enrich_links_with_analytics(mock_client, links)

        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["total_clicks"], 100)
        self.assertEqual(enriched[0]["referrers"][0]["value"], "direct")
        self.assertEqual(enriched[0]["countries"][0]["value"], "US")

        mock_client.get_click_summary.assert_called_once_with("bit.ly/123")
        mock_client.get_referrers.assert_called_once_with("bit.ly/123")
        mock_client.get_countries.assert_called_once_with("bit.ly/123")

    @patch("main.console")
    def test_display_account_info(self, mock_console):
        """Verify display_account_info formats correctly."""
        mock_client = MagicMock(spec=BitlyClient)
        mock_client.get_user.return_value = {
            "login": "test",
            "name": "user",
            "emails": [{"email": "test@test.com", "is_primary": True}],
            "default_group_guid": "G1",
        }
        mock_client.list_groups.return_value = [
            {"guid": "G1", "name": "Group 1"}
        ]

        from main import display_account_info

        guid = display_account_info(mock_client)
        self.assertEqual(guid, "G1")
        mock_client.get_user.assert_called_once()

    @patch("main.console")
    def test_display_bitlinks(self, mock_console):
        """Verify display_bitlinks formats correctly."""
        mock_client = MagicMock(spec=BitlyClient)
        mock_client.list_bitlinks.return_value = {
            "links": [
                {
                    "id": "1",
                    "title": "A",
                    "link": "http",
                    "long_url": "long",
                    "created_at": "2026-06-06T12:00:00Z",
                }
            ]
        }

        from main import display_bitlinks

        links = display_bitlinks(mock_client, "G1")
        self.assertEqual(len(links), 1)

    @patch("main.console")
    def test_view_link_analytics(self, mock_console):
        """Verify view_link_analytics fetches all metrics."""
        mock_client = MagicMock(spec=BitlyClient)
        mock_client.get_click_summary.return_value = {"total_clicks": 100}
        mock_client.get_referrers.return_value = {
            "metrics": [{"value": "direct", "clicks": 50}]
        }
        mock_client.get_countries.return_value = {
            "metrics": [{"value": "US", "clicks": 50}]
        }

        from main import view_link_analytics

        view_link_analytics(mock_client, "bit.ly/123")
        mock_client.get_click_summary.assert_called_once()

    @patch("main.configure_env")
    @patch("main.BitlyClient")
    @patch("sys.argv", ["main.py", "--list", "--group-guid", "G1"])
    def test_main_list_args(self, mock_client_cls, mock_config):
        """Verify main handles --list argument."""
        mock_config.return_value = "token"
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch("main.display_bitlinks") as mock_disp:
            from main import main

            with contextlib.suppress(SystemExit):
                main()
            mock_disp.assert_called_once_with(mock_client, "G1")

    @patch("main.configure_env")
    @patch("main.BitlyClient")
    @patch("sys.argv", ["main.py", "--shorten", "http://long", "--title", "T"])
    def test_main_shorten_args(self, mock_client_cls, mock_config):
        """Verify main handles --shorten argument."""
        mock_config.return_value = "token"
        mock_client = MagicMock()
        mock_client.get_user.return_value = {"default_group_guid": "G1"}
        mock_client_cls.return_value = mock_client

        from main import main

        with contextlib.suppress(SystemExit):
            main()
        mock_client.shorten_url.assert_called_once()

    @patch("main.configure_env")
    @patch("main.BitlyClient")
    @patch(
        "sys.argv",
        [
            "main.py",
            "--export",
            "csv",
            "--bitlink",
            "bit.ly/123",
            "--with-analytics",
        ],
    )
    def test_main_export_args(self, mock_client_cls, mock_config):
        """Verify main handles --export argument."""
        mock_config.return_value = "token"
        mock_client = MagicMock()
        mock_client.list_groups.return_value = []
        mock_client.get_bitlink_details.return_value = {"id": "1"}
        mock_client_cls.return_value = mock_client

        with (
            patch("main.export_bitlinks") as mock_exp,
            patch("main.enrich_links_with_analytics") as mock_enrich,
        ):
            mock_enrich.return_value = [{"id": "1"}]
            from main import main

            with contextlib.suppress(SystemExit):
                main()
            mock_exp.assert_called_once()

    @patch("main.questionary.select")
    @patch("main.display_account_info")
    def test_run_interactive_menu_account_info(self, mock_disp, mock_select):
        """Verify run_interactive_menu handles account info option."""
        mock_client = MagicMock()
        mock_select.return_value.ask.side_effect = [
            "1. Show account info & profile details",
            "5. Exit",
        ]
        from main import run_interactive_menu

        with contextlib.suppress(SystemExit):
            run_interactive_menu(mock_client)
        mock_disp.assert_called_once()

    @patch("main.questionary.select")
    @patch("main.explore_group_menu")
    def test_run_interactive_menu_explore(self, mock_exp, mock_select):
        """Verify run_interactive_menu routes to group menu."""
        mock_client = MagicMock()
        mock_client.get_user.return_value = {"default_group_guid": "G1"}
        mock_select.return_value.ask.side_effect = [
            "2. Explore default group bitlinks and options",
            "5. Exit",
        ]
        from main import run_interactive_menu

        with contextlib.suppress(SystemExit):
            run_interactive_menu(mock_client)
        mock_exp.assert_called_once()

    @patch("main.questionary")
    @patch("main.export_bitlinks")
    @patch("main.enrich_links_with_analytics")
    def test_explore_group_menu_export_json(
        self, mock_enrich, mock_export, mock_q
    ):
        """Verify explore_group_menu handles JSON export flow."""
        mock_client = MagicMock()
        mock_client.get_bitlink_details.return_value = {"id": "bit.ly/123"}
        mock_enrich.return_value = [{"id": "bit.ly/123"}]

        mock_select_ask = MagicMock()
        mock_select_ask.side_effect = [
            "4. Export bitlinks to JSON",
            "Specific Link",
            "Yes",
            "7. Return to main menu",
        ]
        mock_q.select.return_value.ask = mock_select_ask
        mock_q.text.return_value.ask.return_value = "bit.ly/123"

        from main import explore_group_menu

        explore_group_menu(mock_client, "G1", "Group 1")
        mock_export.assert_called_once()

    @patch("main.questionary")
    @patch("main.export_bitlinks")
    @patch("main.enrich_links_with_analytics")
    def test_explore_group_menu_export_all(
        self, mock_enrich, mock_export, mock_q
    ):
        """Verify explore_group_menu handles ALL links BOTH export flow."""
        mock_client = MagicMock()
        mock_client.list_bitlinks.return_value = {
            "links": [{"id": "bit.ly/123"}]
        }
        mock_enrich.return_value = [{"id": "bit.ly/123"}]

        mock_select_ask = MagicMock()
        mock_select_ask.side_effect = [
            "6. Export bitlinks to BOTH (JSON & CSV)",
            "All Links",
            "Yes",
            "7. Return to main menu",
        ]
        mock_q.select.return_value.ask = mock_select_ask

        from main import explore_group_menu

        explore_group_menu(mock_client, "G1", "Group 1")
        self.assertEqual(mock_export.call_count, 1)

    @patch("main.questionary")
    def test_shorten_url_interactive(self, mock_q):
        """Verify shorten_url_interactive captures inputs correctly."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "id": "1",
            "link": "http://bit.ly/1",
        }
        mock_q.text.return_value.ask.side_effect = [
            "http://example.com",
            "My Title",
            "",
        ]

        from main import shorten_url_interactive

        shorten_url_interactive(mock_client, "G1")
        mock_client.shorten_url.assert_called_once_with(
            long_url="http://example.com",
            title="My Title",
            group_guid="G1",
            domain="bit.ly",
        )

    @patch("main.os.path.exists", return_value=False)
    @patch("main.load_dotenv")
    @patch("main.questionary")
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_configure_env_creates_file(
        self, mock_file, mock_q, mock_load, mock_exists
    ):
        """Verify configure_env creates .env when token is provided."""
        mock_q.confirm.return_value.ask.return_value = True
        mock_q.password.return_value.ask.return_value = "new_token_456"

        from main import configure_env

        token = configure_env()
        self.assertEqual(token, "new_token_456")
        mock_file.assert_called_once()

    @patch("main.configure_env")
    @patch("main.BitlyClient")
    @patch("sys.argv", ["main.py", "--analytics", "bit.ly/123"])
    def test_main_analytics_args(self, mock_client_cls, mock_config):
        """Verify main handles --analytics argument."""
        mock_config.return_value = "token"
        with patch("main.view_link_analytics") as mock_ana:
            from main import main

            with contextlib.suppress(SystemExit):
                main()
            mock_ana.assert_called()

    @patch("main.questionary.select")
    @patch("main.questionary.text")
    @patch("main.view_link_analytics")
    def test_run_interactive_menu_analytics(
        self, mock_ana, mock_text, mock_select
    ):
        """Verify run_interactive_menu routes to analytics."""
        mock_client = MagicMock()
        mock_select.return_value.ask.side_effect = [
            "4. View analytics for any bitlink (direct input)",
            "5. Exit",
        ]
        mock_text.return_value.ask.return_value = "bit.ly/123"
        from main import run_interactive_menu

        with contextlib.suppress(SystemExit):
            run_interactive_menu(mock_client)
        mock_ana.assert_called_once_with(mock_client, "bit.ly/123")


if __name__ == "__main__":
    unittest.main()
