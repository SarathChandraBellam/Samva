"""CLI: upload files to the Gemini File Search knowledge base."""
from __future__ import annotations

import argparse
import logging
import sys

from google import genai
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import Config
from ..knowledge_base.loader import discover_files
from ..knowledge_base.manager import KnowledgeBaseManager

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samva-setup-kb",
        description="Upload files or a directory to the Samva knowledge base.",
    )
    p.add_argument("path", help="File or directory to upload")
    p.add_argument(
        "--store",
        metavar="NAME",
        default=None,
        help="Knowledge base store display name (default from config)",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List documents already in the store and exit",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = Config()
        config.validate()
    except ValueError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    store_display = args.store or config.kb_store_name
    client = genai.Client(api_key=config.api_key)
    manager = KnowledgeBaseManager(client=client, search_model=config.search_model)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        task = progress.add_task("Connecting to knowledge base…")
        store_name = manager.create_or_get_store(store_display)
        progress.update(task, description=f"Connected: [bold]{store_name}[/bold]")

    console.print(f"[green]Store:[/green] {store_display}")
    console.print(f"[dim]{store_name}[/dim]\n")

    if args.list:
        docs = manager.list_documents(store_name)
        if not docs:
            console.print("[yellow]No documents yet.[/yellow]")
        else:
            console.print(f"[bold]{len(docs)} document(s):[/bold]")
            for d in docs:
                console.print(f"  • {d}")
        return

    files = discover_files(args.path)
    if not files:
        console.print("[yellow]No supported files found at that path.[/yellow]")
        sys.exit(0)

    console.print(f"Uploading [bold]{len(files)}[/bold] file(s)…\n")

    with Progress(SpinnerColumn(), TextColumn("{task.description}")) as progress:
        for f in files:
            task = progress.add_task(f"  {f.name}")
            manager.upload_file(store_name, f)
            progress.update(task, description=f"  [green]✓[/green] {f.name}")

    docs = manager.list_documents(store_name)
    console.print(f"\n[green]Done.[/green] Knowledge base now has [bold]{len(docs)}[/bold] document(s).")


if __name__ == "__main__":
    main()
