"""Core scaffolding logic: parsing the scaffold manifest and checking data files."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

ScaffoldEntry = tuple[str, Path]
Scaffold = dict[str, list[ScaffoldEntry]]


def package_data_root() -> Traversable:
    """Return the packaged ``data/`` directory as a Traversable resource."""
    return files("quadriga_scaffolding") / "data"


def full_oer_path(oer_path: Path, relative_path: Path) -> Path:
    return oer_path / relative_path


def full_canon_path(relative_path: Path) -> Traversable:
    """Resolve ``relative_path`` against the packaged ``data/`` directory."""
    resource: Traversable = package_data_root()
    for part in relative_path.parts:
        resource = resource / part
    return resource


def parse_path(pathstring: str) -> ScaffoldEntry:
    if len(pathstring) == 0:
        raise ValueError("Empty path string")

    parsetype = "file"
    if pathstring[-1] == "/":
        parsetype = "dir"
    path = Path(pathstring)
    if path.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {pathstring}")
    return (parsetype, path)


def load_scaffold(filename: str | Path | None = None) -> Scaffold:
    """Load and parse the scaffold manifest.

    If ``filename`` is ``None``, load the manifest shipped with the package.
    """
    if filename is None:
        resource = package_data_root() / "scaffold.txt"
        with as_file(resource) as path, path.open() as f:
            return parse_scaffold(f)

    with Path(filename).open() as f:
        return parse_scaffold(f)


def parse_scaffold(f: Iterable[str]) -> Scaffold:
    scaffold: Scaffold = {"create": [], "delete": []}

    for ln, line in enumerate(f):
        if not line.strip():
            continue

        match line[0]:
            case "+":
                path = parse_path(line[2:].strip())
                if ".." in path[1].parts:
                    raise ValueError("Navigating to parent directories in file paths is not allowed")
                logging.info(f"{ln}: Create '{path}'")
                scaffold["create"].append(path)
            case "-":
                path = parse_path(line[2:].strip())
                if ".." in path[1].parts:
                    raise ValueError("Navigating to parent directories in file paths is not allowed")
                logging.info(f"{ln}: Delete '{path}'")
                scaffold["delete"].append(path)
            case _:
                logging.info(f"{ln}: Comment")

    return scaffold


def check_data_directory(scaffold: Scaffold) -> bool:
    """Verify that every file/dir scheduled for creation exists in packaged data/."""
    result = True
    for filetype, file in scaffold["create"]:
        resource = full_canon_path(file)
        if not resource.is_dir() and not resource.is_file():
            result = False
            logging.warning(f"{file} does not exist in packaged data/")
        elif filetype == "dir" and not resource.is_dir():
            result = False
            logging.warning(f"{file} is not a directory in packaged data/")
        elif filetype == "file" and not resource.is_file():
            result = False
            logging.warning(f"{file} is not a file in packaged data/")

    return result
