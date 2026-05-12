#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.11"
# dependencies = [
# ]
# ///

import logging
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import IO


def full_oer_path(oer_path: Path, relative_path: Path) -> Path:
    return oer_path / relative_path


def full_canon_path(relative_path: Path) -> Path:
    return Path("./data/") / relative_path


def parse_path(pathstring: str) -> (str, Path):
    if len(pathstring) == 0:
        raise ValueError("Empty path string")

    parsetype = "file"
    if pathstring[-1] == "/":
        parsetype = "dir"
    return (parsetype, Path(pathstring))


def load_scaffold(filename: str = "./scaffold.txt") -> dict:
    scaffold_file = Path(filename)
    with scaffold_file.open() as f:
        return parse_scaffold(f)


def parse_scaffold(f: IO) -> dict:
    scaffold = {"create": [], "delete": []}

    for ln, line in enumerate(f):
        if ".." in line:
            raise ValueError("Navigating to parent directories in file paths is not allowed")

        match line[0]:
            case "+":
                path = parse_path(line[2:].strip())
                logging.info(f"{ln}: Create '{path}'")
                scaffold["create"].append(path)
            case "-":
                path = parse_path(line[2:].strip())
                logging.info(f"{ln}: Delete '{path}'")
                scaffold["delete"].append(path)
            case _:
                logging.info(f"{ln}: Comment")

    return scaffold


def check_data_directory(scaffold: dict) -> False | True:
    result = True
    for filetype, file in scaffold["create"]:
        path = full_canon_path(file)
        if not path.exists():
            result = False
            logging.warning(f"{file} does not exist in './data/'")
        elif filetype == "dir" and not path.is_dir():
            result = False
            logging.warning(f"{file} is not a directory in './data'")
        elif filetype == "file" and not path.is_file():
            result = False
            logging.warning(f"{file} is not a file in './data'")

    return result


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

    # Configure logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    # Load the scaffolding structure file
    scaffold = load_scaffold()
    logging.info(f"OER Path: {args.oer_path}")
    logging.info(f"Update mode: {args.update}")
    logging.info(scaffold)

    if not check_data_directory(scaffold):
        sys.exit(1)


if __name__ == "__main__":
    main()
