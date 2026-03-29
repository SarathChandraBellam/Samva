"""CLI: start the Samva Twilio bridge server."""
from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samva-serve",
        description="Start the Samva Twilio bridge (FastAPI + Uvicorn).",
    )
    p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p.add_argument(
        "--public-host",
        metavar="HOST",
        default=None,
        help=(
            "Publicly reachable host:port for the Twilio stream URL "
            "(e.g. abc123.ngrok.io). "
            "Overrides SAMVA_PUBLIC_HOST env var."
        ),
    )
    p.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    import logging
    import os
    import uvicorn

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.public_host:
        os.environ["SAMVA_PUBLIC_HOST"] = args.public_host

    public_host = os.environ.get("SAMVA_PUBLIC_HOST", f"localhost:{args.port}")
    webhook_url = f"https://{public_host}/voice"
    stream_url = f"wss://{public_host}/media"

    console.print(
        Panel(
            f"[bold]Listening:[/bold]    {args.host}:{args.port}\n"
            f"[bold]Webhook URL:[/bold]  [cyan]{webhook_url}[/cyan]\n"
            f"[bold]Stream URL:[/bold]   [cyan]{stream_url}[/cyan]\n\n"
            "[dim]Set your Twilio phone number's Voice webhook to the Webhook URL above.\n"
            "Use ngrok or a public server to expose this port.[/dim]",
            title="[green]Samva Twilio Bridge[/green]",
            expand=False,
        )
    )

    try:
        uvicorn.run(
            "samva.twilio_bridge.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="debug" if args.verbose else "info",
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
