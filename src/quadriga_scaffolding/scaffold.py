"""Core scaffolding logic: parsing the scaffold manifest and checking data files."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import NamedTuple


class EntryKind(StrEnum):
    """Kind of scaffold entry: a regular file or a directory."""

    FILE = "file"
    DIR = "dir"


class ScaffoldEntry(NamedTuple):
    """A single manifest entry: an ``EntryKind`` paired with its relative ``Path``."""

    kind: EntryKind
    path: Path


@dataclass(frozen=True)
class Scaffold:
    """Parsed scaffold manifest, split into ``create`` and ``delete`` entries."""

    create: list[ScaffoldEntry] = field(default_factory=list)
    delete: list[ScaffoldEntry] = field(default_factory=list)


def package_data_root() -> Traversable:
    """Return the packaged ``data/`` directory as a Traversable resource."""
    return files("quadriga_scaffolding") / "data"


def parse_path(pathstring: str) -> ScaffoldEntry:
    """Parse a manifest path into a ``ScaffoldEntry``.

    A trailing ``/`` marks the entry as a directory; otherwise it is a file.
    Absolute paths are rejected.
    """
    pathstring = pathstring.strip()
    if len(pathstring) == 0:
        raise ValueError("Empty path string")

    kind = EntryKind.DIR if pathstring[-1] == "/" else EntryKind.FILE
    path = Path(pathstring)
    if path.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {pathstring}")
    return ScaffoldEntry(kind, path)


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
    """Parse manifest lines into a ``Scaffold``.

    Lines starting with ``+ `` add a create entry; lines starting with ``- ``
    add a delete entry; anything else (including blank lines) is treated as a
    comment. ``..`` segments in entry paths are rejected.
    """
    scaffold = Scaffold()

    for ln, line in enumerate(f, start=1):
        if not line.strip():
            continue

        match line[0]:
            case "+":
                entry = parse_path(line[2:])
                if ".." in entry.path.parts:
                    raise ValueError("Navigating to parent directories in file paths is not allowed")
                logging.debug(f"{ln}: Create '{entry}'")
                scaffold.create.append(entry)
            case "-":
                entry = parse_path(line[2:])
                if ".." in entry.path.parts:
                    raise ValueError("Navigating to parent directories in file paths is not allowed")
                logging.debug(f"{ln}: Delete '{entry}'")
                scaffold.delete.append(entry)
            case _:
                logging.debug(f"{ln}: Comment")

    return scaffold


def validate_scaffold(scaffold: Scaffold) -> bool:
    """Validate the scaffold manifest against the packaged ``data/`` tree.

    Only ``create`` entries are checked for existence: every path listed under
    ``create`` must exist in the packaged ``data/`` directory, with the kind
    (file vs. directory) matching the manifest entry. ``delete`` entries are
    not required to exist in ``data/`` — they describe paths to remove from a
    target OER, not source files — and are therefore skipped.

    Additionally, a path must not appear in both ``create`` and ``delete``.

    Returns ``True`` if all checks pass, ``False`` otherwise (warnings are
    logged for each failure).
    """
    result = True

    create_paths = {entry.path for entry in scaffold.create}
    delete_paths = {entry.path for entry in scaffold.delete}
    for overlap in create_paths & delete_paths:
        result = False
        logging.warning(f"{overlap} appears in both create and delete")

    for kind, file in scaffold.create:
        resource = package_data_root().joinpath(*file.parts)
        if not resource.is_dir() and not resource.is_file():
            result = False
            logging.warning(f"{file} does not exist in packaged data/")
        elif kind is EntryKind.DIR and not resource.is_dir():
            result = False
            logging.warning(f"{file} is not a directory in packaged data/")
        elif kind is EntryKind.FILE and not resource.is_file():
            result = False
            logging.warning(f"{file} is not a file in packaged data/")

    return result
