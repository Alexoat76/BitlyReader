#!/usr/bin/env -S uv run
"""Bitly CLI Reader - Entry Point.

This module provides the command-line interface (CLI) for interacting with the
Bitly API v4. It supports direct argument execution and an interactive menu
powered by the `rich` library.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Any

import questionary
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.status import Status
from rich.table import Table

from client import BitlyClient, BitlyError, BitlyUpgradeRequiredError
from exporter import export_bitlinks

# Initialize global Rich console for premium terminal rendering
console = Console()

custom_style = questionary.Style(
    [
        ("qmark", "fg:#00ffff bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#00ff00 bold"),
        ("pointer", "fg:#ffff00 bold"),
        ("highlighted", "fg:#ffff00 bold"),
        ("choice", "fg:#cccccc"),
    ]
)


def configure_env() -> str:
    """Check for Bitly Access Token in the environment and prompt if missing.

    This function attempts to load the token from the .env file. If the token
    is not found, it interactively prompts the user for the token and securely
    saves it back to the .env file.

    Returns:
        str: The validated Bitly Generic Access Token.

    Raises:
        SystemExit: If user declines token or provides an empty one.

    """
    load_dotenv()
    token = os.getenv("BITLY_ACCESS_TOKEN")

    if token and token.strip() not in (
        "",
        "your_access_token_here",
        "your_generated_access_token_here",
    ):
        return token

    # Token is missing, guide the user to enter it interactively
    console.print(
        Panel.fit(
            "[bold yellow]Bitly Access Token not found![/bold yellow]\n\n"
            "To consume data from the Bitly API, you need a Generic "
            "Access Token.\n"
            "You can generate one in [bold cyan]Bitly settings -> "
            "API[/bold cyan]\n"
            "at https://app.bitly.com/settings/api/.",
            title="Configuration Setup",
            border_style="yellow",
        )
    )

    setup_now = questionary.confirm(
        "Would you like to set up your Access Token now?", style=custom_style
    ).ask()

    if not setup_now:
        console.print(
            "[bold red]Error: BITLY_ACCESS_TOKEN is required to run this "
            "tool. Exiting.[/bold red]"
        )
        sys.exit(1)

    entered_token = questionary.password(
        "Please enter/paste your Bitly Access Token", style=custom_style
    ).ask()

    if not entered_token or not entered_token.strip():
        console.print(
            "[bold red]Error: Invalid token entered. Exiting.[/bold red]"
        )
        sys.exit(1)

    # Save token to .env file for future runs
    try:
        with open(".env", "a") as f:
            f.write(f"\nBITLY_ACCESS_TOKEN={entered_token.strip()}\n")
        console.print(
            "[bold green]Success: Token saved to .env file![/bold green]\n"
        )
    except Exception as err:
        console.print(
            f"[yellow]Warning: Could not save token to .env file: "
            f"{err}[/yellow]"
        )

    return str(entered_token.strip())


def enrich_links_with_analytics(
    client: BitlyClient, links: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fetch and attach detailed analytics for each link.

    Args:
        client: The BitlyClient instance.
        links: A list of link dictionaries to enrich.

    Returns:
        The enriched list of links.

    """
    console.print(
        "[bold blue]Fetching advanced analytics for links...[/bold blue]"
    )

    for link in track(links, description="Enriching data"):
        bitlink_id = link.get("id")
        if not bitlink_id:
            continue

        clean_id = bitlink_id.replace("https://", "").replace("http://", "")

        # Get total clicks
        try:
            summary = client.get_click_summary(clean_id)
            link["total_clicks"] = summary.get("total_clicks", 0)
        except BitlyError:
            link["total_clicks"] = "N/A"

        # Get referrers
        try:
            refs = client.get_referrers(clean_id).get("metrics", [])
            link["referrers"] = refs
        except BitlyUpgradeRequiredError:
            link["referrers"] = "Upgrade Required"
        except BitlyError:
            link["referrers"] = "N/A"

        # Get countries
        try:
            countries = client.get_countries(clean_id).get("metrics", [])
            link["countries"] = countries
        except BitlyUpgradeRequiredError:
            link["countries"] = "Upgrade Required"
        except BitlyError:
            link["countries"] = "N/A"

    return links


def display_account_info(client: BitlyClient) -> str | None:
    """Fetch and display the authenticated user's profile and default group.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.

    Returns:
        Optional[str]: The default group GUID if found.

    """
    with Status("[bold blue]Retrieving account details...", console=console):
        try:
            user = client.get_user()
            groups = client.list_groups()
        except BitlyError as err:
            console.print(
                f"[bold red]\nFailed to retrieve account details: "
                f"{err}[/bold red]"
            )
            return None

    default_group = user.get("default_group_guid")

    emails = user.get("emails") or []
    primary_email = next(
        (e["email"] for e in emails if e.get("is_primary")), "N/A"
    )

    panel_content = [
        f"[bold cyan]User Name:[/bold cyan] {user.get('name', 'N/A')}",
        f"[bold cyan]Login:[/bold cyan] {user.get('login', 'N/A')}",
        f"[bold cyan]Primary Email:[/bold cyan] {primary_email}",
        f"[bold cyan]Default Group GUID:[/bold cyan] "
        f"{default_group or 'N/A'}\n",
    ]

    console.print(
        Panel(
            "\n".join(panel_content),
            title="Authenticated User Profile",
            border_style="magenta",
            expand=False,
        )
    )

    if groups:
        table = Table(
            title="Available Groups", header_style="bold magenta", expand=True
        )
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Group GUID", style="green", no_wrap=True)
        table.add_column("Group Name", style="white")
        table.add_column("Is Default", style="yellow")

        for idx, grp in enumerate(groups, 1):
            guid = grp.get("guid", "")
            is_def = "Yes" if guid == default_group else "No"
            table.add_row(
                str(idx), guid, grp.get("name", "Unnamed Group"), is_def
            )

        console.print(table)

    return default_group


def display_bitlinks(
    client: BitlyClient, group_guid: str
) -> list[dict[str, Any]] | None:
    """Fetch and list available bitlinks in a group via a Rich table.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        group_guid (str): The group GUID.

    Returns:
        Optional[list[dict[str, Any]]]: Bitlinks if successful, else None.

    """
    with Status("[bold blue]Fetching bitlinks...", console=console):
        try:
            response = client.list_bitlinks(group_guid, page=1, size=100)
            links = response.get("links") or []
        except BitlyError as err:
            console.print(
                f"[bold red]\nFailed to retrieve bitlinks: {err}[/bold red]"
            )
            return None

    if not links:
        console.print("[yellow]No bitlinks found in this group.[/yellow]")
        return []

    table = Table(title="Bitlinks", header_style="bold magenta", expand=True)
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Short Link", style="green", no_wrap=True)
    table.add_column("Long URL", style="blue")
    table.add_column("Created", style="yellow")

    for idx, link in enumerate(links, 1):
        created_str = link.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            formatted_date = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            formatted_date = created_str

        table.add_row(
            str(idx),
            link.get("title") or "Untitled Link",
            link.get("link", ""),
            link.get("long_url", ""),
            formatted_date,
        )

    console.print(table)
    return links


def shorten_url_interactive(client: BitlyClient, default_group: str) -> None:
    """Guide the user to shorten a URL interactively.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        default_group (str): Default group GUID.

    """
    long_url = questionary.text(
        "Enter the long URL to shorten", style=custom_style
    ).ask()

    if not long_url or not long_url.strip():
        console.print("[bold red]URL must not be empty.[/bold red]")
        return

    title = (
        questionary.text(
            "Enter an optional title/label for the link",
            default="",
            style=custom_style,
        ).ask()
        or ""
    )

    domain = (
        questionary.text(
            "Enter an optional domain (e.g. 'bit.ly')",
            default="bit.ly",
            style=custom_style,
        ).ask()
        or "bit.ly"
    )

    with Status("[bold blue]Shortening URL...", console=console):
        try:
            result = client.shorten_url(
                long_url=long_url.strip(),
                group_guid=default_group,
                domain=domain.strip() or None,
                title=title.strip() or None,
            )
        except BitlyError as err:
            console.print(f"[bold red]Failed to shorten URL: {err}[/bold red]")
            return

    panel_content = [
        f"[bold cyan]Short Link:[/bold cyan] {result.get('link', 'N/A')}",
        f"[bold cyan]Long URL:[/bold cyan] {result.get('long_url', 'N/A')}",
        f"[bold cyan]Title:[/bold cyan] "
        f"{result.get('title') or 'Untitled Link'}",
    ]
    console.print(
        Panel(
            "\n".join(panel_content),
            title="Shorten Success!",
            border_style="green",
            expand=False,
        )
    )


def view_link_analytics(client: BitlyClient, bitlink: str) -> None:
    """Fetch and present analytics for a specific bitlink.

    Handles plan limitations (HTTP 402 Upgrade Required) gracefully.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        bitlink (str): The shortened link (domain/hash).

    """
    # Remove http:// or https:// if present
    clean_bitlink = bitlink.replace("https://", "").replace("http://", "")

    console.print(
        f"\n[bold cyan]Fetching analytics for {clean_bitlink}...[/bold cyan]"
    )

    # Click Summary
    try:
        with Status("[bold blue]Fetching click summary...", console=console):
            summary = client.get_click_summary(clean_bitlink)
        total_clicks = summary.get("total_clicks", 0)
        console.print(
            Panel(
                f"[bold green]Total Clicks:[/bold green] {total_clicks}",
                title="Engagement Summary",
                border_style="green",
                expand=False,
            )
        )
    except BitlyUpgradeRequiredError:
        console.print(
            Panel(
                "[bold yellow]Upgrade Required[/bold yellow]\n\n"
                "Your Bitly account plan does not allow API access to "
                "click metrics.\n"
                "To see total click counts, please upgrade your "
                "Bitly subscription.",
                title="Click Summary",
                border_style="yellow",
                expand=False,
            )
        )
        return
    except BitlyError as err:
        console.print(
            f"[bold red]Error fetching click summary: {err}[/bold red]"
        )
        return

    # If clicks are available, we can fetch referrers and countries
    try:
        with Status(
            "[bold blue]Retrieving referrers & countries...", console=console
        ):
            referrers = client.get_referrers(clean_bitlink).get("metrics", [])
            countries = client.get_countries(clean_bitlink).get("metrics", [])

        # Display Referrers Table
        if referrers:
            ref_table = Table(title="Top Referrers", header_style="bold green")
            ref_table.add_column("Referrer Domain", style="cyan")
            ref_table.add_column("Clicks", justify="right", style="magenta")
            for ref in referrers:
                ref_table.add_row(
                    ref.get("value", "unknown"), str(ref.get("clicks", 0))
                )
            console.print(ref_table)
        else:
            console.print(
                "[yellow]No referrer data available for this link.[/yellow]"
            )

        # Display Countries Table
        if countries:
            ct_table = Table(title="Top Countries", header_style="bold green")
            ct_table.add_column("Country Code", style="cyan")
            ct_table.add_column("Clicks", justify="right", style="magenta")
            for ct in countries:
                ct_table.add_row(
                    ct.get("value", "unknown"), str(ct.get("clicks", 0))
                )
            console.print(ct_table)
        else:
            console.print(
                "[yellow]No country data available for this link.[/yellow]"
            )

    except BitlyUpgradeRequiredError:
        console.print(
            "[yellow]Note: Referrer and country breakdown requires an "
            "upgraded plan.[/yellow]"
        )
    except BitlyError as err:
        console.print(
            f"[bold red]Error fetching detailed metrics: {err}[/bold red]"
        )


def explore_group_menu(
    client: BitlyClient, group_guid: str, group_name: str
) -> None:
    """Explore option sub-menu for a specific group.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        group_guid (str): GUID of the group.
        group_name (str): Name of the group.

    """
    while True:
        console.rule(f"[bold cyan]Group: {group_name}[/bold cyan]")

        choice = questionary.select(
            "Options:",
            choices=[
                "1. List all bitlinks",
                "2. Shorten a new URL",
                "3. View link analytics",
                "4. Export bitlinks to JSON",
                "5. Export bitlinks to CSV",
                "6. Export bitlinks to BOTH (JSON & CSV)",
                "7. Return to main menu",
            ],
            style=custom_style,
        ).ask()

        if not choice or choice.startswith("7"):
            break

        if choice.startswith("1"):
            display_bitlinks(client, group_guid)

        elif choice.startswith("2"):
            shorten_url_interactive(client, group_guid)

        elif choice.startswith("3"):
            links = display_bitlinks(client, group_guid)
            if links:
                num = questionary.text(
                    "Select link # to view analytics (or Enter to cancel)",
                    default="",
                    style=custom_style,
                ).ask()

                if num and num.strip():
                    try:
                        idx = int(num) - 1
                        if 0 <= idx < len(links):
                            view_link_analytics(client, links[idx]["id"])
                        else:
                            console.print(
                                "[bold red]Invalid selection.[/bold red]"
                            )
                    except ValueError:
                        console.print(
                            "[bold red]Please enter a valid integer."
                            "[/bold red]"
                        )

        elif (
            choice.startswith("4")
            or choice.startswith("5")
            or choice.startswith("6")
        ):
            fmt = "both"
            if choice.startswith("4"):
                fmt = "json"
            elif choice.startswith("5"):
                fmt = "csv"

            target_type = questionary.select(
                "Export all links or a specific link?",
                choices=["All Links", "Specific Link"],
                style=custom_style,
            ).ask()

            if not target_type:
                continue

            links_to_export = []
            final_group_name = group_name
            is_single_link = False

            if "Specific" in target_type:
                target_link = questionary.text(
                    "Enter the specific Bitlink ID (e.g. bit.ly/3PRgy0g)",
                    style=custom_style,
                ).ask()

                if not target_link or not target_link.strip():
                    continue

                is_single_link = True
                clean_id = (
                    target_link.strip()
                    .replace("https://", "")
                    .replace("http://", "")
                )
                with Status(
                    f"[bold blue]Fetching details for {clean_id}...",
                    console=console,
                ):
                    try:
                        link_details = client.get_bitlink_details(clean_id)
                        links_to_export = [link_details]
                        final_group_name = (
                            f"SingleLink_{clean_id.replace('/', '_')}"
                        )
                    except BitlyError as err:
                        console.print(
                            f"[bold red]Failed to fetch bitlink: "
                            f"{err}[/bold red]"
                        )
            else:
                with Status(
                    "[bold blue]Fetching all links for export...",
                    console=console,
                ):
                    try:
                        response = client.list_bitlinks(
                            group_guid, page=1, size=100
                        )
                        links_to_export = response.get("links") or []
                    except BitlyError as err:
                        console.print(
                            f"[bold red]Failed to fetch links: "
                            f"{err}[/bold red]"
                        )

            if links_to_export:
                with_analytics = questionary.confirm(
                    "Fetch and include detailed analytics "
                    "(clicks, referrers, countries)?",
                    style=custom_style,
                ).ask()
                has_analytics = bool(with_analytics)
                if has_analytics:
                    links_to_export = enrich_links_with_analytics(
                        client, links_to_export
                    )

                export_bitlinks(
                    final_group_name,
                    links_to_export,
                    fmt,
                    is_single_link=is_single_link,
                    has_analytics=has_analytics,
                )
            else:
                console.print("[yellow]No bitlinks found to export.[/yellow]")


def run_interactive_menu(client: BitlyClient) -> None:
    """Run the main CLI interactive application loop.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.

    """
    # Fetch default group guid first
    try:
        user = client.get_user()
        default_group = user.get("default_group_guid")
        groups = client.list_groups()
    except BitlyError as err:
        console.print(f"[bold red]Connection error: {err}[/bold red]")
        sys.exit(1)

    while True:
        console.rule(
            "[bold cyan]Bitly API Data Consumer & Shortener[/bold cyan]"
        )

        choice = questionary.select(
            "Main Menu:",
            choices=[
                "1. Show account info & profile details",
                "2. Explore default group bitlinks and options",
                "3. Explore a specific group by index",
                "4. View analytics for any bitlink (direct input)",
                "5. Exit",
            ],
            style=custom_style,
        ).ask()

        if not choice or choice.startswith("5"):
            console.print("\n[bold green]Goodbye![/bold green]")
            break

        if choice.startswith("1"):
            display_account_info(client)

        elif choice.startswith("2"):
            if default_group:
                # Find group name
                group_name = next(
                    (g["name"] for g in groups if g["guid"] == default_group),
                    "Default Group",
                )
                explore_group_menu(client, default_group, group_name)
            else:
                console.print(
                    "[bold red]No default group configured on your "
                    "Bitly account.[/bold red]"
                )

        elif choice.startswith("3"):
            if not groups:
                console.print("[yellow]No groups found.[/yellow]")
                continue

            display_account_info(client)
            num = questionary.text(
                "Select group # to explore (or Enter to cancel)",
                default="",
                style=custom_style,
            ).ask()

            if num and num.strip():
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(groups):
                        explore_group_menu(
                            client, groups[idx]["guid"], groups[idx]["name"]
                        )
                    else:
                        console.print(
                            "[bold red]Invalid selection.[/bold red]"
                        )
                except ValueError:
                    console.print(
                        "[bold red]Please enter a valid integer.[/bold red]"
                    )

        elif choice.startswith("4"):
            bitlink = questionary.text(
                "Enter Bitlink ID (e.g. bit.ly/3PRgy0g)", style=custom_style
            ).ask()

            if bitlink and bitlink.strip():
                view_link_analytics(client, bitlink.strip())


def main() -> None:
    """Parse command line arguments and execute the tool workflow.

    Raises:
        SystemExit: On critical failures or user cancellation.

    """
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        filename="logs/run.log",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.info("BitlyReader CLI started.")
    try:
        parser = argparse.ArgumentParser(
            prog="BitlyReader",
            description=(
                "BitlyReader CLI 🚀\n"
                "A world-class data pipeline for consuming, shortening, and "
                "exporting Bitly link analytics.\n"
                "----------------------------------------------------------"
            ),
            epilog=(
                "Examples:\n"
                "  Launch the interactive graphical menu:\n"
                "  $ uv run main.py\n\n"
                "  Export all links in both CSV and JSON formats "
                "with analytics:\n"
                "  $ uv run main.py --export both --with-analytics\n\n"
                "  Shorten a custom URL and set a title:\n"
                "  $ uv run main.py --shorten https://github.com "
                "--title 'GitHub'\n"
            ),
            formatter_class=argparse.RawTextHelpFormatter,
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all bitlinks directly for the default group.",
        )
        parser.add_argument(
            "--shorten",
            type=str,
            help="Directly shorten a URL.",
        )
        parser.add_argument(
            "--title",
            type=str,
            help="Specify a title for the shortened URL (requires --shorten).",
        )
        parser.add_argument(
            "--analytics",
            type=str,
            help="Directly print click analytics for the specified bitlink.",
        )
        parser.add_argument(
            "--export",
            choices=["csv", "json", "both"],
            help="Export bitlinks directly.",
        )
        parser.add_argument(
            "--with-analytics",
            action="store_true",
            help="Fetch and include analytics for each exported bitlink.",
        )
        parser.add_argument(
            "--bitlink",
            type=str,
            help="Specify a single bitlink to export instead of the group.",
        )
        parser.add_argument(
            "--group-guid",
            type=str,
            help="Specify a group GUID to use instead of default group.",
        )

        args = parser.parse_args()

        if args.title and not args.shorten:
            parser.error("--title requires --shorten to be specified.")

        # Ensure environment token is configured
        token = configure_env()
        client = BitlyClient(token=token)

        if args.list:
            group_guid = args.group_guid
            if not group_guid:
                user = client.get_user()
                group_guid = user.get("default_group_guid")

            if group_guid:
                display_bitlinks(client, group_guid)
            else:
                console.print(
                    "[bold red]Error: No default group found.[/bold red]"
                )
                sys.exit(1)

        elif args.shorten:
            group_guid = args.group_guid
            if not group_guid:
                user = client.get_user()
                group_guid = user.get("default_group_guid")

            with Status("[bold blue]Shortening URL...", console=console):
                try:
                    result = client.shorten_url(
                        long_url=args.shorten,
                        group_guid=group_guid,
                        title=args.title,
                    )
                    console.print(
                        "[bold green]Shortened successfully![/bold green]"
                    )
                    console.print(f"Short Link: {result.get('link')}")
                except BitlyError as err:
                    console.print(f"[bold red]API Error: {err}[/bold red]")
                    sys.exit(1)

        elif args.analytics:
            view_link_analytics(client, args.analytics)

        elif args.export:
            group_guid = args.group_guid
            groups = client.list_groups()

            if group_guid:
                group_name = next(
                    (g["name"] for g in groups if g["guid"] == group_guid),
                    "Group",
                )
            else:
                user = client.get_user()
                group_guid = user.get("default_group_guid")
                group_name = next(
                    (g["name"] for g in groups if g["guid"] == group_guid),
                    "Default Group",
                )

            if not group_guid:
                console.print(
                    "[bold red]Error: Group GUID could not be determined."
                    "[/bold red]"
                )
                sys.exit(1)

            links_to_export = []
            final_group_name = group_name
            is_single_link = False

            if args.bitlink:
                is_single_link = True
                clean_id = args.bitlink.replace("https://", "").replace(
                    "http://", ""
                )
                with Status(
                    f"[bold blue]Fetching details for {clean_id}...",
                    console=console,
                ):
                    try:
                        link_details = client.get_bitlink_details(clean_id)
                        links_to_export = [link_details]
                        final_group_name = (
                            f"SingleLink_{clean_id.replace('/', '_')}"
                        )
                    except BitlyError as err:
                        console.print(
                            f"[bold red]Failed to fetch bitlink: "
                            f"{err}[/bold red]"
                        )
                        sys.exit(1)
            else:
                with Status(
                    "[bold blue]Fetching links for export...", console=console
                ):
                    try:
                        response = client.list_bitlinks(
                            group_guid, page=1, size=100
                        )
                        links_to_export = response.get("links") or []
                    except BitlyError as err:
                        console.print(
                            f"[bold red]Failed to fetch links: "
                            f"{err}[/bold red]"
                        )
                        sys.exit(1)

            if links_to_export:
                has_analytics = bool(args.with_analytics)
                if has_analytics:
                    links_to_export = enrich_links_with_analytics(
                        client, links_to_export
                    )
                export_bitlinks(
                    final_group_name,
                    links_to_export,
                    args.export,
                    is_single_link=is_single_link,
                    has_analytics=has_analytics,
                )
            else:
                console.print("[yellow]No bitlinks found to export.[/yellow]")

        else:
            # Run the interactive terminal menu
            run_interactive_menu(client)

    except KeyboardInterrupt:
        console.print(
            "\n[bold yellow]Session cancelled by user. Goodbye![/bold yellow]"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
