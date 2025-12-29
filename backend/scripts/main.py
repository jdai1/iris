#!/usr/bin/env python3
"""Main CLI for iris scraper - consolidated commands."""

import sys

import argparse

# Initialize custom logger before importing other modules
from app.utils.logger import scraper_logger  # noqa: F401

import app.db as db
from scripts.db import reset_domain
from scripts.scrape import scrape_domain_cmd
from app.utils.db_utils import print_domain_state


def main():
    parser = argparse.ArgumentParser(
        description="Iris scraper CLI - manage domain scraping and database operations"
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Command to run", required=True
    )

    # Scrape command
    scrape_parser = subparsers.add_parser(
        "scrape",
        help="Scrape a domain and display the results",
    )
    scrape_parser.add_argument(
        "url",
        type=str,
        help="URL of the domain to scrape (e.g., https://jdai1.github.io)",
    )
    scrape_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum BFS depth for crawling (default: 10)",
    )
    scrape_parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for parallel processing (default: 50)",
    )

    # Show command
    show_parser = subparsers.add_parser(
        "show",
        help="Show domain state and related data",
    )
    show_parser.add_argument(
        "url",
        type=str,
        help="URL of the domain to show (e.g., https://jdai1.github.io)",
    )

    # Reset command
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset a domain by deleting scraped data and resetting status to PENDING",
    )
    reset_parser.add_argument(
        "url",
        type=str,
        help="URL of the domain to reset (e.g., https://jdai1.github.io)",
    )
    reset_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    try:
        if args.command == "scrape":
            scrape_domain_cmd(
                url=args.url,
                max_depth=args.max_depth,
                batch_size=args.batch_size,
            )

        elif args.command == "show":
            print_domain_state(args.url)

        elif args.command == "reset":
            reset_domain(args.url, confirm=args.yes)

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        db.session.rollback()
        sys.exit(1)


if __name__ == "__main__":
    main()
