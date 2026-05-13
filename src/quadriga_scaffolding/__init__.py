"""QUADRIGA OER scaffolding tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("quadriga-scaffolding")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.0.0+unknown"
