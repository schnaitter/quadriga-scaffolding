"""Command-line entry point for ``scaffold``."""

from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

from quadriga_scaffolding.scaffold import (
    apply_update,
    diff_oer,
    format_diff,
    format_diff_with_content,
    load_scaffold,
    validate_scaffold,
)


def main() -> None:
    """Run the ``scaffold`` console script."""
    parser = ArgumentParser(description="Update a QUADRIGA OER to contain common files to the latest version.")
    parser.add_argument("oer_path", help="Path to the OER to compare or update")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update files to the newest version instead of just comparing",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to a scaffold manifest to use instead of the packaged one",
    )
    parser.add_argument(
        "--show-ok",
        action="store_true",
        help="Also print in-sync (ok) entries, not just drifted ones",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff of each modified (M) file's contents under its status line",
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

    oer_path = Path(args.oer_path)
    if not oer_path.is_dir():
        parser.error(f"OER path is not a directory: {oer_path}")

    scaffold = load_scaffold(args.manifest)
    logging.info(f"OER Path: {oer_path}")
    logging.info(f"Update mode: {args.update}")
    logging.info(scaffold)

    if not validate_scaffold(scaffold):
        sys.exit(2)

    diff = diff_oer(scaffold, oer_path)
    if args.update:
        diff = apply_update(scaffold, oer_path, diff)
    if args.diff:
        output = format_diff_with_content(diff, oer_path, show_ok=args.show_ok)
    else:
        output = format_diff(diff, show_ok=args.show_ok)
    if output:
        print(output)
    sys.exit(1 if diff.has_drift() else 0)


if __name__ == "__main__":
    main()
