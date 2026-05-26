"""Core scaffolding logic: parsing the scaffold manifest and checking data files."""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Iterable, Iterator
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


class EntryStatus(StrEnum):
    """Status of a single path when an OER is compared against the scaffold."""

    OK = "ok"
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    UNTRACKED = "untracked"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DiffItem:
    """A single path's status in an OER diff, with its path relative to the OER root."""

    status: EntryStatus
    path: Path
    detail: str = ""


@dataclass
class OerDiff:
    """The full set of per-path statuses produced by comparing an OER to the scaffold."""

    items: list[DiffItem] = field(default_factory=list)

    def has_drift(self) -> bool:
        """Return ``True`` if any item is not in sync (i.e. has a non-OK status)."""
        return any(i.status is not EntryStatus.OK for i in self.items)


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


def iter_packaged_files(entry: ScaffoldEntry) -> Iterator[Path]:
    """Yield every packaged file covered by ``entry``, relative to ``data/``.

    For a ``FILE`` entry this is just ``entry.path``. For a ``DIR`` entry the
    packaged ``data/<entry.path>`` tree is walked recursively and the path of
    every regular file is yielded (each starting with ``entry.path``).
    """
    if entry.kind is EntryKind.FILE:
        yield entry.path
        return

    def walk(resource: Traversable, rel: Path) -> Iterator[Path]:
        for child in resource.iterdir():
            child_rel = rel / child.name
            if child.is_dir():
                yield from walk(child, child_rel)
            elif child.is_file():
                yield child_rel

    root = package_data_root().joinpath(*entry.path.parts)
    yield from walk(root, entry.path)


def read_packaged_bytes(rel: Path) -> bytes:
    """Read the bytes of the packaged file at ``data/<rel>``."""
    return package_data_root().joinpath(*rel.parts).read_bytes()


def _md5(data: bytes) -> str:
    """Return the MD5 hex digest of ``data`` (used only for change detection)."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def files_differ(target: Path, rel: Path) -> bool:
    """Return ``True`` if the OER file at ``target`` differs from packaged ``data/<rel>``.

    The packaged bytes are read once; if their length already differs from the
    OER file's size the files are known to differ and the OER file is never
    read. Otherwise both sides are compared by MD5 digest rather than by
    holding both byte strings in memory at once. MD5 is used purely for change
    detection, not security.
    """
    packaged = read_packaged_bytes(rel)
    if target.stat().st_size != len(packaged):
        return True
    return _md5(target.read_bytes()) != _md5(packaged)


def _dir_is_recursively_empty(p: Path) -> bool:
    """Return ``True`` iff ``p`` is a directory containing no regular files.

    Empty subdirectories (at any depth) are allowed; any regular file anywhere
    in the tree makes the directory non-empty.
    """
    if not p.is_dir():
        return False
    return not any(child.is_file() for child in p.rglob("*"))


def _count_files(p: Path) -> int:
    """Return the number of regular files anywhere under directory ``p``."""
    return sum(1 for child in p.rglob("*") if child.is_file())


# Ordering of statuses in formatted output: drift first (in legend order), then OK.
_STATUS_ORDER = {
    EntryStatus.ADD: 0,
    EntryStatus.MODIFY: 1,
    EntryStatus.DELETE: 2,
    EntryStatus.UNTRACKED: 3,
    EntryStatus.BLOCKED: 4,
    EntryStatus.OK: 5,
}

_STATUS_LETTER = {
    EntryStatus.ADD: "A",
    EntryStatus.MODIFY: "M",
    EntryStatus.DELETE: "D",
    EntryStatus.UNTRACKED: "?",
    EntryStatus.BLOCKED: "!",
    EntryStatus.OK: " ",
}


def _diff_create_entry(entry: ScaffoldEntry, oer_root: Path) -> Iterator[DiffItem]:
    """Yield diff items for a single ``create`` entry (ADD/MODIFY/OK + UNTRACKED)."""
    packaged = list(iter_packaged_files(entry))
    for rel in packaged:
        target = oer_root / rel
        if not target.is_file():
            yield DiffItem(EntryStatus.ADD, rel)
        elif files_differ(target, rel):
            yield DiffItem(EntryStatus.MODIFY, rel)
        else:
            yield DiffItem(EntryStatus.OK, rel)

    if entry.kind is not EntryKind.DIR:
        return

    packaged_set = set(packaged)
    oer_dir = oer_root / entry.path
    if not oer_dir.is_dir():
        return
    for found in oer_dir.rglob("*"):
        if not found.is_file():
            continue
        rel = found.relative_to(oer_root)
        if rel not in packaged_set:
            yield DiffItem(EntryStatus.UNTRACKED, rel)


def _diff_delete_entry(entry: ScaffoldEntry, oer_root: Path) -> Iterator[DiffItem]:
    """Yield diff items for a single ``delete`` entry (DELETE/BLOCKED, or nothing)."""
    target = oer_root / entry.path
    if entry.kind is EntryKind.FILE:
        if target.is_file():
            yield DiffItem(EntryStatus.DELETE, entry.path)
    elif target.is_dir():
        if _dir_is_recursively_empty(target):
            yield DiffItem(EntryStatus.DELETE, entry.path)
        else:
            n = _count_files(target)
            yield DiffItem(EntryStatus.BLOCKED, entry.path, detail=f"{n} files inside")


def diff_oer(scaffold: Scaffold, oer_root: Path) -> OerDiff:
    """Compare an OER tree against the scaffold manifest.

    Every ``create`` entry is expanded to its packaged files; each file is
    classified as ``ADD`` (missing), ``MODIFY`` (bytes differ), or ``OK``.
    Files found inside a managed ``+ dir/`` but absent from the packaged tree
    are reported ``UNTRACKED``. ``delete`` entries yield ``DELETE`` (present
    file, or present recursively-empty dir) or ``BLOCKED`` (non-empty dir);
    absent delete targets are omitted entirely.

    The scaffold is assumed valid: call :func:`validate_scaffold` first, since
    a ``+ dir/`` entry with no matching packaged directory raises while the
    packaged tree is walked. Path existence is tested with ``is_file`` /
    ``is_dir``, which follow symlinks, so a symlinked tracked file is compared
    (and in ``apply_update`` written) through its target.
    """
    items: list[DiffItem] = []
    for entry in scaffold.create:
        items.extend(_diff_create_entry(entry, oer_root))
    for entry in scaffold.delete:
        items.extend(_diff_delete_entry(entry, oer_root))

    # A file may be covered by both a `+ dir/` and a `+ file` entry; keep one
    # item per path, preferring the status that sorts first (most drifted).
    best: dict[Path, DiffItem] = {}
    for item in items:
        existing = best.get(item.path)
        if existing is None or _STATUS_ORDER[item.status] < _STATUS_ORDER[existing.status]:
            best[item.path] = item

    deduped = sorted(best.values(), key=lambda i: (_STATUS_ORDER[i.status], i.path.as_posix()))
    return OerDiff(items=deduped)


def format_diff(diff: OerDiff, *, show_ok: bool = False) -> str:
    """Render an ``OerDiff`` as git-style status lines, one per drifted item.

    OK items are skipped unless ``show_ok`` is set. Each line is a two-char
    status column followed by the path, with any ``detail`` in parentheses.
    """
    lines: list[str] = []
    for item in diff.items:
        if item.status is EntryStatus.OK and not show_ok:
            continue
        letter = _STATUS_LETTER[item.status]
        line = f"{letter:<2}{item.path.as_posix()}"
        if item.detail:
            line += f" ({item.detail})"
        lines.append(line)
    return "\n".join(lines)


def apply_update(scaffold: Scaffold, oer_root: Path, diff: OerDiff) -> OerDiff:
    """Apply the resolvable actions from ``diff`` to the OER, then re-diff.

    ``ADD``/``MODIFY`` copy the packaged bytes into place (creating parent
    directories). ``DELETE`` unlinks files and removes recursively-empty
    directories. ``UNTRACKED`` files and ``BLOCKED`` (non-empty) directories
    are left untouched; ``BLOCKED`` is logged at WARNING level. A fresh
    ``diff_oer`` is returned so callers get a uniform post-update view.

    Per-item I/O errors (permissions, races) are caught and logged at ERROR
    level so one unwritable path does not abort the whole run; such items will
    still show as drift in the returned diff.
    """
    for item in diff.items:
        target = oer_root / item.path
        try:
            match item.status:
                case EntryStatus.ADD | EntryStatus.MODIFY:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(read_packaged_bytes(item.path))
                case EntryStatus.DELETE:
                    if target.is_file():
                        target.unlink()
                    elif target.is_dir() and _dir_is_recursively_empty(target):
                        shutil.rmtree(target)
                case EntryStatus.BLOCKED:
                    logging.warning(f"{item.path} not deleted ({item.detail}); remove its contents manually")
                case EntryStatus.UNTRACKED | EntryStatus.OK:
                    pass
        except OSError as exc:
            logging.error(f"{item.path}: could not apply {item.status} ({exc})")

    return diff_oer(scaffold, oer_root)
