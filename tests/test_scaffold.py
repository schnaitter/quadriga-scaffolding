from pathlib import Path

import pytest

from quadriga_scaffolding.scaffold import EntryKind, Scaffold, ScaffoldEntry, parse_path, parse_scaffold


def test_parse_scaffold_with_filenames() -> None:
    test_file = ["comment\n", "+ add\n", "- subtract\n"]
    assert parse_scaffold(test_file) == Scaffold(
        create=[ScaffoldEntry(EntryKind.FILE, Path("add"))],
        delete=[ScaffoldEntry(EntryKind.FILE, Path("subtract"))],
    )


def test_parse_scaffold_disallows_navigation_to_parent() -> None:
    test_file = ["comment\n", "+ ..\n", "- subtract\n"]
    with pytest.raises(ValueError):
        parse_scaffold(test_file)


def test_parse_path_as_file() -> None:
    assert ScaffoldEntry(EntryKind.FILE, Path("test/test.py")) == parse_path("test/test.py")
    assert ScaffoldEntry(EntryKind.FILE, Path("test")) == parse_path("test")


def test_parse_path_as_directory() -> None:
    assert ScaffoldEntry(EntryKind.DIR, Path("test/test/")) == parse_path("test/test/")
    assert ScaffoldEntry(EntryKind.DIR, Path("test/")) == parse_path("test/")
