"""
Buy a Twilio phone number and point its webhook at your running server.

Usage:
    uv run python scripts/setup_twilio.py --ngrok-url https://abc123.ngrok-free.app
    uv run python scripts/setup_twilio.py --list-numbers      # show numbers you already own
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
import os

load_dotenv()

from twilio.rest import Client  # noqa: E402

ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(ACCOUNT_SID, AUTH_TOKEN)


def list_owned_numbers() -> None:
    numbers = client.incoming_phone_numbers.list()
    if not numbers:
        print("You don't own any Twilio numbers yet.")
        return
    print(f"Your Twilio numbers ({len(numbers)}):")
    for n in numbers:
        print(f"  {n.phone_number}  sid={n.sid}  webhook={n.voice_url or '(none)'}")


def buy_number(country: str = "US") -> str:
    """Search for an available number and purchase it. Returns the phone number."""
    available = client.available_phone_numbers(country).local.list(limit=5)
    if not available:
        print(f"No available numbers in {country}. Try --country CA or GB.")
        sys.exit(1)

    chosen = available[0]
    print(f"Purchasing {chosen.phone_number} …")
    purchased = client.incoming_phone_numbers.create(phone_number=chosen.phone_number)
    print(f"  Purchased: {purchased.phone_number}  (sid={purchased.sid})")
    return purchased.sid


def set_webhook(number_sid: str, public_url: str) -> None:
    """Point a number's voice webhook to POST /voice on your server."""
    webhook = f"{public_url}/voice"
    client.incoming_phone_numbers(number_sid).update(voice_url=webhook, voice_method="POST")
    print(f"  Webhook set to: {webhook}")


def configure_existing(public_url: str) -> None:
    """Update ALL owned numbers to point at the new URL."""
    numbers = client.incoming_phone_numbers.list()
    if not numbers:
        print("No owned numbers found — buy one first (run without --update-only).")
        sys.exit(1)
    for n in numbers:
        set_webhook(n.sid, public_url)
        print(f"  Updated {n.phone_number}")


def main() -> None:
    p = argparse.ArgumentParser(description="Twilio number setup for Samva")
    p.add_argument("--ngrok-url", metavar="URL",
                   help="Your public ngrok HTTPS URL, e.g. https://abc123.ngrok-free.app")
    p.add_argument("--country", default="US",
                   help="ISO country code for number search (default: US)")
    p.add_argument("--list-numbers", action="store_true",
                   help="List numbers you already own and exit")
    p.add_argument("--update-only", action="store_true",
                   help="Don't buy — just update webhook on existing numbers")
    args = p.parse_args()

    if args.list_numbers:
        list_owned_numbers()
        return

    if not args.ngrok_url:
        p.print_help()
        print("\nERROR: --ngrok-url is required (unless --list-numbers)")
        sys.exit(1)

    public_url = args.ngrok_url.rstrip("/")

    if args.update_only:
        configure_existing(public_url)
    else:
        numbers = client.incoming_phone_numbers.list()
        if numbers:
            print(f"You already own {len(numbers)} number(s) — updating webhook instead of buying.")
            for n in numbers:
                set_webhook(n.sid, public_url)
                print(f"  Updated {n.phone_number}")
        else:
            sid = buy_number(args.country)
            set_webhook(sid, public_url)

    print("\nDone! Next steps:")
    print(f"  1. Make sure the server is running:  uv run samva-serve --public-host {public_url.replace('https://', '')}")
    print(f"  2. Call your Twilio number — it will connect to Samva.")


if __name__ == "__main__":
    main()
