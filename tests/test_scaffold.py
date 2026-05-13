from pathlib import Path

import pytest

from quadriga_scaffolding.scaffold import parse_path, parse_scaffold


def test_parse_scaffold_with_filenames() -> None:
    test_file = ["comment\n", "+ add\n", "- subtract\n"]
    assert parse_scaffold(test_file) == {"create": [("file", Path("add"))], "delete": [("file", Path("subtract"))]}


def test_parse_scaffold_disallows_navigation_to_parent() -> None:
    test_file = ["comment\n", "+ ..\n", "- subtract\n"]
    with pytest.raises(ValueError):
        parse_scaffold(test_file)


def test_parse_path_as_file() -> None:
    assert ("file", Path("test/test.py")) == parse_path("test/test.py")
    assert ("file", Path("test")) == parse_path("test")


def test_parse_path_as_directory() -> None:
    assert ("dir", Path("test/test/")) == parse_path("test/test/")
    assert ("dir", Path("test/")) == parse_path("test/")
