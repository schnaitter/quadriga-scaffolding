"""Command-line entry point for ``scaffold``."""

from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser

from quadriga_scaffolding.scaffold import load_scaffold, validate_scaffold


def main() -> None:
    parser = ArgumentParser(description="Update a QUADRIGA OER to contain common files to the latest version.")
    parser.add_argument("oer_path", help="Path to the OER to compare or update")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update files to the newest version instead of just comparing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show INFO level logging messages",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Show DEBUG level logging messages (implies --verbose)",
    )

    args = parser.parse_args()

    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    scaffold = load_scaffold()
    logging.info(f"OER Path: {args.oer_path}")
    logging.info(f"Update mode: {args.update}")
    logging.info(scaffold)

    if not validate_scaffold(scaffold):
        sys.exit(1)


if __name__ == "__main__":
    main()
