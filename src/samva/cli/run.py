"""CLI: start the Samva voice agent."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel

from ..agent.agent import VoiceAgent
from ..config import AVAILABLE_VOICES, Config
from ..prompts import list_prompts

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samva-run",
        description="Start the Samva real-time voice agent.",
    )
    p.add_argument(
        "--store",
        metavar="NAME",
        default=None,
        help="Knowledge base store name (default from config/env)",
    )
    p.add_argument(
        "--no-kb",
        action="store_true",
        help="Disable knowledge base — agent answers from Gemini only",
    )
    p.add_argument(
        "--voice",
        choices=AVAILABLE_VOICES,
        default=None,
        help=f"Agent voice (default: Kore). Options: {', '.join(AVAILABLE_VOICES)}",
    )
    p.add_argument(
        "--prompt",
        metavar="TEXT",
        default=None,
        help="Override the system prompt with a literal string",
    )
    p.add_argument(
        "--prompt-template",
        metavar="NAME",
        default=None,
        help=(
            f"Use a named prompt template from samva/prompts/. "
            f"Available: {', '.join(list_prompts())}"
        ),
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = Config()
        if args.store:
            config.kb_store_name = args.store
        if args.no_kb:
            config.enable_kb = False
        if args.voice:
            config.voice_name = args.voice
        if args.prompt:
            config.system_prompt = args.prompt
        if args.prompt_template:
            config.prompt_template = args.prompt_template
            config.system_prompt = ""  # force template resolution
        config.validate()
    except ValueError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    agent = VoiceAgent(config)

    kb_line = "(disabled)"
    if config.enable_kb:
        try:
            store_name = agent.setup_knowledge_base()
            docs = agent.kb.list_documents(store_name)
            kb_line = f"{config.kb_store_name} ([cyan]{len(docs)} doc(s)[/cyan])"
        except Exception as exc:
            console.print(f"[red]Failed to connect to knowledge base:[/red] {exc}")
            sys.exit(1)

    console.print(
        Panel(
            f"[bold]Model:[/bold]           {config.live_model}\n"
            f"[bold]Knowledge Base:[/bold]   {kb_line}\n"
            f"[bold]Voice:[/bold]           {config.voice_name}\n"
            f"[bold]Prompt template:[/bold]  {config.prompt_template}\n"
            f"[bold]Tools:[/bold]           {', '.join(agent.tools.names()) or '(none yet)'}\n\n"
            "[dim]Speak into your microphone. Press Ctrl+C to stop.[/dim]",
            title="[green]Samva Voice Agent[/green]",
            expand=False,
        )
    )

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")


if __name__ == "__main__":
    main()
