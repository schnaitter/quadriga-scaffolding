"""Command-line entry point for ``scaffold``."""

from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser

from quadriga_scaffolding.scaffold import check_data_directory, load_scaffold


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

    args = parser.parse_args()

    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    scaffold = load_scaffold()
    logging.info(f"OER Path: {args.oer_path}")
    logging.info(f"Update mode: {args.update}")
    logging.info(scaffold)

    if not check_data_directory(scaffold):
        sys.exit(1)


if __name__ == "__main__":
    main()
