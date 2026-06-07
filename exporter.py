"""Data Export Module.

This module handles the exportation of Bitly links into standardized
formats (JSON, CSV). It enforces security best practices by preventing Path
Traversal attacks via sanitized filenames, and mitigating CSV Formula Injection
by sanitizing malicious spreadsheet formulas.
"""

import csv
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.status import Status

# Initialize console for rich output
console = Console()
logger = logging.getLogger(__name__)


def _sanitize_filename(filename: str) -> str:
    """Sanitize a string to be safely used as a filename.

    Args:
        filename (str): The raw filename to sanitize.

    Returns:
        str: A safe, alphanumeric string without path traversal characters.

    """
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", filename.lower()).strip("_")
    # Prevent empty filenames if input was entirely special characters
    return safe_name if safe_name else "export"


def log_audit_event(group_name: str, record_count: int, formats: str) -> None:
    """Log an audit event to a JSON Lines file.

    Args:
        group_name: Name of the exported group.
        record_count: Number of records exported.
        formats: Formats exported (csv, json, both).

    """
    os.makedirs("logs", exist_ok=True)
    with open("logs/audit.jsonl", "a", encoding="utf-8") as f:
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "group": group_name,
            "records_exported": record_count,
            "formats": formats,
        }
        f.write(json.dumps(event) + "\n")


def _sanitize_csv_field(value: Any) -> str:
    """Sanitize a CSV field to prevent Formula Injection attacks.

    If a field starts with '=', '+', '-', or '@', opening the resulting CSV in
    Excel or other spreadsheet programs can lead to arbitrary code execution.
    This function mitigates that by prepending a single quote.

    Args:
        value (Any): The raw value to sanitize.

    Returns:
        str: The sanitized string value.

    """
    str_val = str(value) if value is not None else ""
    if str_val and str_val.startswith(("=", "+", "-", "@")):
        return f"'{str_val}"
    return str_val


def export_bitlinks(
    group_name: str,
    links: list[dict[str, Any]],
    format_type: str,
    output_dir: str | Path = ".",
    is_single_link: bool = False,
    has_analytics: bool = False,
) -> None:
    """Export bitlinks to a consolidated single file (JSON or CSV).

    Args:
        group_name (str): The name of the group.
        links (list[dict[str, Any]]): The list of bitlinks to export.
        format_type (str): The format to export to ('json', 'csv', or 'both').
        output_dir (str | Path, optional): Directory to save the exported file.
            Defaults to current directory.
        is_single_link (bool, optional): Whether this is a single link export.
        has_analytics (bool, optional): Whether links have detailed analytics.

    Raises:
        ValueError: If an unsupported format_type is provided.
        OSError: If there is a filesystem error during file creation.

    """
    if format_type not in ("json", "csv", "both"):
        raise ValueError(f"Unsupported format_type: {format_type}")

    # Inject last_updated timestamp into each link
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for link in links:
        link["last_updated"] = last_updated

    # Determine Base Directory and Filename
    base_output = Path(output_dir).resolve() / "output"

    if is_single_link:
        target_dir = base_output / "specifics"
        if links and links[0].get("id"):
            base_filename = _sanitize_filename(links[0]["id"])
        else:
            base_filename = "untitled"
    else:
        target_dir = base_output / "general"
        base_filename = "bitlinks"

    if has_analytics:
        base_filename = f"{base_filename}_enriched"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        console.print(
            f"[bold red]Failed to create directory {target_dir}: "
            f"{err}[/bold red]"
        )
        return

    formats_to_export = (
        ["json", "csv"] if format_type == "both" else [format_type]
    )

    for fmt in formats_to_export:
        filename = f"{base_filename}.{fmt}"
        output_path = target_dir / filename

        with Status(
            f"[bold blue]Exporting {len(links)} links to {filename}...",
            console=console,
        ):
            try:
                if fmt == "json":
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(links, f, indent=4, ensure_ascii=False)

                elif fmt == "csv":
                    with open(
                        output_path, "w", newline="", encoding="utf-8"
                    ) as f:
                        writer = csv.writer(f)
                        if links:
                            all_keys: set[str] = set()
                            for link in links:
                                all_keys.update(link.keys())
                            headers = sorted(all_keys)
                            writer.writerow(headers)

                            for link in links:
                                row = []
                                for header in headers:
                                    val = link.get(header)
                                    if isinstance(val, (dict, list)):
                                        val = json.dumps(val)
                                    sanitized_val = _sanitize_csv_field(val)
                                    row.append(sanitized_val)
                                writer.writerow(row)
            except Exception as err:
                console.print(
                    f"[bold red]Failed to export {fmt}: {err}[/bold red]"
                )
                continue

        console.print(
            Panel(
                f"[bold green]Data exported successfully![/bold green]\n"
                f"Export Type: [bold cyan]Consolidated[/bold cyan]\n"
                f"Format: [bold cyan]{fmt.upper()}[/bold cyan]\n"
                f"Exported Count: [bold white]{len(links)}[/bold white]\n"
                f"File: [bold white]{output_path}[/bold white]",
                title="Export Success!",
                border_style="green",
                expand=False,
            )
        )

        log_audit_event(group_name, len(links), fmt)
