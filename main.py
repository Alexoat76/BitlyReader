#!/usr/bin/env -S uv run
"""Bitly CLI Reader - Entry Point.

This module provides the command-line interface (CLI) for interacting with the
Bitly API v4. It supports direct argument execution and an interactive menu
powered by the `rich` library.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.status import Status
from rich.table import Table

from client import BitlyClient, BitlyError, BitlyUpgradeRequiredError

# Initialize global Rich console for premium terminal rendering
console = Console()


def configure_env() -> str:
    """Check for Bitly Access Token in the environment and prompt if missing.

    This function attempts to load the token from the .env file. If the token
    is not found, it interactively prompts the user for the token and securely
    saves it back to the .env file.

    Returns:
        str: The validated Bitly Generic Access Token.

    Raises:
        SystemExit: If the user declines to provide a token or provides an empty one.

    """
    load_dotenv()
    token = os.getenv("BITLY_ACCESS_TOKEN")

    if token:
        return token

    # Token is missing, guide the user to enter it interactively
    console.print(
        Panel.fit(
            "[bold yellow]Bitly Access Token not found![/bold yellow]\n\n"
            "To consume data from the Bitly API, you need a Generic Access Token.\n"
            "You can generate one in [bold cyan]Bitly settings -> API[/bold cyan]\n"
            "at https://app.bitly.com/settings/api/.",
            title="Configuration Setup",
            border_style="yellow",
        )
    )

    setup_now = Confirm.ask("Would you like to set up your Access Token now?")
    if not setup_now:
        console.print(
            "[bold red]Error: BITLY_ACCESS_TOKEN is required to run this tool. Exiting.[/bold red]"
        )
        sys.exit(1)

    entered_token = Prompt.ask("Please enter/paste your Bitly Access Token", password=True)
    if not entered_token.strip():
        console.print("[bold red]Error: Invalid token entered. Exiting.[/bold red]")
        sys.exit(1)

    # Save token to .env file for future runs
    try:
        with open(".env", "a") as f:
            f.write(f"\nBITLY_ACCESS_TOKEN={entered_token.strip()}\n")
        console.print("[bold green]Success: Token saved to .env file![/bold green]\n")
    except Exception as err:
        console.print(f"[yellow]Warning: Could not save token to .env file: {err}[/yellow]")

    return entered_token.strip()


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
            console.print(f"[bold red]\nFailed to retrieve account details: {err}[/bold red]")
            return None

    default_group = user.get("default_group_guid")

    emails = user.get("emails") or []
    primary_email = next((e["email"] for e in emails if e.get("is_primary")), "N/A")

    panel_content = [
        f"[bold cyan]User Name:[/bold cyan] {user.get('name', 'N/A')}",
        f"[bold cyan]Login:[/bold cyan] {user.get('login', 'N/A')}",
        f"[bold cyan]Primary Email:[/bold cyan] {primary_email}",
        f"[bold cyan]Default Group GUID:[/bold cyan] {default_group or 'N/A'}\n",
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
        table = Table(title="Available Groups", header_style="bold magenta", expand=True)
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Group GUID", style="green", no_wrap=True)
        table.add_column("Group Name", style="white")
        table.add_column("Is Default", style="yellow")

        for idx, grp in enumerate(groups, 1):
            guid = grp.get("guid", "")
            is_def = "Yes" if guid == default_group else "No"
            table.add_row(str(idx), guid, grp.get("name", "Unnamed Group"), is_def)

        console.print(table)

    return default_group


def display_bitlinks(client: BitlyClient, group_guid: str) -> list[dict[str, Any]] | None:
    """Fetch and list all available bitlinks in a group in a beautiful Rich table.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        group_guid (str): The group GUID.

    Returns:
        Optional[list[dict[str, Any]]]: A list of bitlinks if successful, otherwise None.

    """
    with Status("[bold blue]Fetching bitlinks...", console=console):
        try:
            response = client.list_bitlinks(group_guid, page=1, size=100)
            links = response.get("links") or []
        except BitlyError as err:
            console.print(f"[bold red]\nFailed to retrieve bitlinks: {err}[/bold red]")
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
    long_url = Prompt.ask("Enter the long URL to shorten")
    if not long_url.strip():
        console.print("[bold red]URL must not be empty.[/bold red]")
        return

    title = Prompt.ask("Enter an optional title/label for the link", default="")
    domain = Prompt.ask("Enter an optional domain (e.g. 'bit.ly')", default="bit.ly")

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
        f"[bold cyan]Title:[/bold cyan] {result.get('title') or 'Untitled Link'}",
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

    console.print(f"\n[bold cyan]Fetching analytics for {clean_bitlink}...[/bold cyan]")

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
                "Your Bitly account plan does not allow API access to click metrics.\n"
                "To see total click counts, please upgrade your Bitly subscription.",
                title="Click Summary",
                border_style="yellow",
                expand=False,
            )
        )
        return
    except BitlyError as err:
        console.print(f"[bold red]Error fetching click summary: {err}[/bold red]")
        return

    # If clicks are available, we can fetch referrers and countries
    try:
        with Status("[bold blue]Retrieving referrers & countries...", console=console):
            referrers = client.get_referrers(clean_bitlink).get("metrics", [])
            countries = client.get_countries(clean_bitlink).get("metrics", [])

        # Display Referrers Table
        if referrers:
            ref_table = Table(title="Top Referrers", header_style="bold green")
            ref_table.add_column("Referrer Domain", style="cyan")
            ref_table.add_column("Clicks", justify="right", style="magenta")
            for ref in referrers:
                ref_table.add_row(ref.get("value", "unknown"), str(ref.get("clicks", 0)))
            console.print(ref_table)
        else:
            console.print("[yellow]No referrer data available for this link.[/yellow]")

        # Display Countries Table
        if countries:
            ct_table = Table(title="Top Countries", header_style="bold green")
            ct_table.add_column("Country Code", style="cyan")
            ct_table.add_column("Clicks", justify="right", style="magenta")
            for ct in countries:
                ct_table.add_row(ct.get("value", "unknown"), str(ct.get("clicks", 0)))
            console.print(ct_table)
        else:
            console.print("[yellow]No country data available for this link.[/yellow]")

    except BitlyUpgradeRequiredError:
        console.print(
            "[yellow]Note: Referrer and country breakdown requires an upgraded plan.[/yellow]"
        )
    except BitlyError as err:
        console.print(f"[bold red]Error fetching detailed metrics: {err}[/bold red]")


def export_bitlinks(group_name: str, links: list[dict[str, Any]], format_type: str) -> None:
    """Export bitlinks to separate files in a group-and-date folder.

    Each link will be written to its own file named using its hash.

    Args:
        group_name (str): The name of the group.
        links (list[dict[str, Any]]): The list of bitlinks.
        format_type (str): The format to export to ('json' or 'csv').

    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Clean the group name for use as a folder name
    safe_group_name = "".join(c for c in group_name if c.isalnum() or c in ("-", "_")).rstrip()
    folder_name = f"{safe_group_name}_{date_str}"
    os.makedirs(folder_name, exist_ok=True)

    for link in links:
        bitlink_id = link.get("id", "")
        # Extract the hash/id part (e.g., bit.ly/3PRgy0g -> 3PRgy0g)
        link_hash = bitlink_id.split("/")[-1] if "/" in bitlink_id else bitlink_id

        file_path = os.path.join(folder_name, f"{link_hash}.{format_type}")

        if format_type == "json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(link, f, indent=4, ensure_ascii=False)
        elif format_type == "csv":
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Field", "Value"])
                for key, val in link.items():
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    writer.writerow([key, val])

    console.print(
        f"[bold green]Successfully exported {len(links)} bitlink(s) "
        f"to '{folder_name}' folder![/bold green]"
    )


def explore_group_menu(client: BitlyClient, group_guid: str, group_name: str) -> None:
    """Explore option sub-menu for a specific group.

    Args:
        client (BitlyClient): The initialized Bitly API client instance.
        group_guid (str): GUID of the group.
        group_name (str): Name of the group.

    """
    while True:
        console.rule(f"[bold cyan]Group: {group_name}[/bold cyan]")
        console.print("\n[bold]Options:[/bold]")
        console.print("1. List all bitlinks")
        console.print("2. Shorten a new URL")
        console.print("3. View link analytics")
        console.print("4. Export bitlinks to JSON")
        console.print("5. Export bitlinks to CSV")
        console.print("6. Return to main menu")

        choice = Prompt.ask("Choose an action", choices=["1", "2", "3", "4", "5", "6"], default="6")

        if choice == "1":
            display_bitlinks(client, group_guid)

        elif choice == "2":
            shorten_url_interactive(client, group_guid)

        elif choice == "3":
            links = display_bitlinks(client, group_guid)
            if links:
                num = Prompt.ask("Select link # to view analytics (or Enter to cancel)", default="")
                if num.strip():
                    try:
                        idx = int(num) - 1
                        if 0 <= idx < len(links):
                            view_link_analytics(client, links[idx]["id"])
                        else:
                            console.print("[bold red]Invalid selection.[/bold red]")
                    except ValueError:
                        console.print("[bold red]Please enter a valid integer.[/bold red]")

        elif choice in ("4", "5"):
            fmt = "json" if choice == "4" else "csv"
            with Status("[bold blue]Fetching all links for export...", console=console):
                try:
                    response = client.list_bitlinks(group_guid, page=1, size=100)
                    links = response.get("links") or []
                except BitlyError as err:
                    console.print(f"[bold red]Failed to fetch links: {err}[/bold red]")
                    links = []

            if links:
                export_bitlinks(group_name, links, fmt)
            else:
                console.print("[yellow]No bitlinks found to export.[/yellow]")

        elif choice == "6":
            break


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
        console.rule("[bold cyan]Bitly API Data Consumer & Shortener[/bold cyan]")
        console.print("\n[bold]Main Menu:[/bold]")
        console.print("1. Show account info & profile details")
        console.print("2. Explore default group bitlinks and options")
        console.print("3. Explore a specific group by index")
        console.print("4. View analytics for any bitlink (direct input)")
        console.print("5. Exit")

        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5"], default="5")

        if choice == "1":
            display_account_info(client)

        elif choice == "2":
            if default_group:
                # Find group name
                group_name = next(
                    (g["name"] for g in groups if g["guid"] == default_group), "Default Group"
                )
                explore_group_menu(client, default_group, group_name)
            else:
                console.print(
                    "[bold red]No default group configured on your Bitly account.[/bold red]"
                )

        elif choice == "3":
            if not groups:
                console.print("[yellow]No groups found.[/yellow]")
                continue

            display_account_info(client)
            num = Prompt.ask("Select group # to explore (or Enter to cancel)", default="")
            if num.strip():
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(groups):
                        explore_group_menu(client, groups[idx]["guid"], groups[idx]["name"])
                    else:
                        console.print("[bold red]Invalid selection.[/bold red]")
                except ValueError:
                    console.print("[bold red]Please enter a valid integer.[/bold red]")

        elif choice == "4":
            bitlink = Prompt.ask("Enter Bitlink ID (e.g. bit.ly/3PRgy0g)")
            if bitlink.strip():
                view_link_analytics(client, bitlink.strip())

        elif choice == "5":
            console.print("\n[bold green]Goodbye![/bold green]")
            break


def main() -> None:
    """Parse command line arguments and execute the tool workflow.

    Raises:
        SystemExit: On critical failures or user cancellation.

    """
    try:
        parser = argparse.ArgumentParser(
            description="A world-class CLI tool to fetch, shorten, and analyze Bitly links."
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
            choices=["csv", "json"],
            help="Export all bitlinks for the default group directly.",
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
                console.print("[bold red]Error: No default group found.[/bold red]")
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
                    console.print("[bold green]Shortened successfully![/bold green]")
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
                group_name = next((g["name"] for g in groups if g["guid"] == group_guid), "Group")
            else:
                user = client.get_user()
                group_guid = user.get("default_group_guid")
                group_name = next(
                    (g["name"] for g in groups if g["guid"] == group_guid), "Default Group"
                )

            if not group_guid:
                console.print("[bold red]Error: Group GUID could not be determined.[/bold red]")
                sys.exit(1)

            with Status("[bold blue]Fetching links for export...", console=console):
                try:
                    response = client.list_bitlinks(group_guid, page=1, size=100)
                    links = response.get("links") or []
                except BitlyError as err:
                    console.print(f"[bold red]Failed to fetch links: {err}[/bold red]")
                    sys.exit(1)

            if links:
                export_bitlinks(group_name, links, args.export)
            else:
                console.print("[yellow]No bitlinks found to export.[/yellow]")

        else:
            # Run the interactive terminal menu
            run_interactive_menu(client)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Session cancelled by user. Goodbye![/bold yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
