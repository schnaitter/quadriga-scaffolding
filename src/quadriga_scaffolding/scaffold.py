"""Core scaffolding logic: parsing the scaffold manifest and checking data files."""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
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


# Build/editor/VCS artifacts that are never intentional scaffold content. Any
# path component matching one of these is ignored on both sides of a diff, so
# such files are neither synced from the package nor reported as untracked.
_IGNORED_NAMES = frozenset({"__pycache__", ".DS_Store", ".ipynb_checkpoints", ".git"})
_IGNORED_SUFFIXES = (".pyc", ".pyo")


def is_ignored(rel: Path) -> bool:
    """Return ``True`` if any component of ``rel`` is a build/editor/VCS artifact."""
    if any(part in _IGNORED_NAMES for part in rel.parts):
        return True
    return rel.suffix in _IGNORED_SUFFIXES


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
            if is_ignored(child_rel):
                continue
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


def _iter_content_files(p: Path) -> Iterator[Path]:
    """Yield regular files anywhere under ``p``, excluding build/editor artifacts."""
    for child in p.rglob("*"):
        if child.is_file() and not is_ignored(child):
            yield child


def _count_content_files(p: Path) -> int:
    """Return the number of content files anywhere under directory ``p``.

    Empty subdirectories (at any depth) and ignored artifacts (``__pycache__``,
    ``.DS_Store``, ...) are not counted; ``0`` means the directory is
    recursively empty.
    """
    return sum(1 for _ in _iter_content_files(p))


def _dir_is_recursively_empty(p: Path) -> bool:
    """Return ``True`` iff ``p`` is a directory containing no content files."""
    if not p.is_dir():
        return False
    return next(_iter_content_files(p), None) is None


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
        if is_ignored(rel):
            continue
        if rel not in packaged_set:
            yield DiffItem(EntryStatus.UNTRACKED, rel)


def _diff_delete_entry(entry: ScaffoldEntry, oer_root: Path) -> Iterator[DiffItem]:
    """Yield diff items for a single ``delete`` entry (DELETE/BLOCKED, or nothing)."""
    target = oer_root / entry.path
    if entry.kind is EntryKind.FILE:
        if target.is_file():
            yield DiffItem(EntryStatus.DELETE, entry.path)
    elif target.is_dir():
        n = _count_content_files(target)
        if n == 0:
            yield DiffItem(EntryStatus.DELETE, entry.path)
        else:
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


def _is_binary(data: bytes) -> bool:
    """Return ``True`` if ``data`` looks like binary rather than UTF-8 text.

    A NUL byte is a strong binary signal; otherwise we treat content that does
    not decode as UTF-8 as binary. This mirrors git's "treat as binary unless it
    cleanly decodes" heuristic closely enough for human-facing diff output.
    """
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def diff_file(target: Path, rel: Path) -> str:
    """Return a git-style unified diff of OER file ``target`` vs packaged ``data/<rel>``.

    The packaged version is the "old" (``a/``) side and the OER file is the
    "new" (``b/``) side, so the diff reads as the change ``--update`` would undo
    by overwriting the OER file. If either side is binary, a single
    ``Binary files ... differ`` line is returned instead of a line diff.
    """
    packaged = read_packaged_bytes(rel)
    current = target.read_bytes()
    posix = rel.as_posix()
    if _is_binary(packaged) or _is_binary(current):
        return f"Binary files a/{posix} and b/{posix} differ"

    packaged_lines = packaged.decode("utf-8").splitlines(keepends=True)
    current_lines = current.decode("utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(
        packaged_lines,
        current_lines,
        fromfile=f"a/{posix}",
        tofile=f"b/{posix}",
    )
    return "".join(diff).rstrip("\n")


# ANSI SGR codes used to colorize a unified diff, mirroring git's defaults:
# added lines green, removed lines red, hunk headers cyan, file headers bold.
_ANSI_RESET = "\x1b[0m"
_ANSI_ADD = "\x1b[32m"
_ANSI_DEL = "\x1b[31m"
_ANSI_HUNK = "\x1b[36m"
_ANSI_HEADER = "\x1b[1m"


def colorize_diff(text: str) -> str:
    """Wrap the lines of a unified diff in ANSI color codes, git-diff style.

    Each line is classified by its leading character(s): ``+++``/``---`` file
    headers are bold, ``@@`` hunk headers cyan, ``+`` additions green, ``-``
    removals red, and context lines are left uncolored. ``Binary files ...``
    notes get the same bold treatment as a header. The input is assumed to be
    :func:`diff_file` output; callers decide *whether* to colorize (see
    :func:`should_colorize`).
    """
    out: list[str] = []
    for line in text.split("\n"):
        if line.startswith(("+++", "---")) or line.startswith("Binary files "):
            color = _ANSI_HEADER
        elif line.startswith("@@"):
            color = _ANSI_HUNK
        elif line.startswith("+"):
            color = _ANSI_ADD
        elif line.startswith("-"):
            color = _ANSI_DEL
        else:
            out.append(line)
            continue
        out.append(f"{color}{line}{_ANSI_RESET}")
    return "\n".join(out)


def should_colorize(when: str, stream: object) -> bool:
    """Resolve a ``--color`` choice against the environment and output ``stream``.

    ``when`` is ``"always"``, ``"never"``, or ``"auto"``. ``auto`` enables color
    only when ``stream`` is a TTY and the ``NO_COLOR`` environment variable is
    unset (see https://no-color.org). ``always`` ignores both; ``never`` is
    always off.
    """
    if when == "always":
        return True
    if when == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def format_diff_with_content(
    diff: OerDiff,
    oer_root: Path,
    *,
    show_ok: bool = False,
    color: bool = False,
) -> str:
    """Render ``diff`` as in :func:`format_diff`, with a unified diff after each MODIFY.

    Each status line is emitted exactly as in :func:`format_diff`; every
    ``MODIFY`` line is followed by its :func:`diff_file` output. ``oer_root`` is
    needed to read the current OER files for the content diff. When ``color`` is
    set, each diff body is wrapped in ANSI codes via :func:`colorize_diff`; the
    status lines themselves are never colored.
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
        if item.status is EntryStatus.MODIFY:
            body = diff_file(oer_root / item.path, item.path)
            lines.append(colorize_diff(body) if color else body)
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
