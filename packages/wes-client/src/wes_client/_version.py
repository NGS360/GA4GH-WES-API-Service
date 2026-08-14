"""
The package version, read from installed metadata rather than hardcoded.

Kept in its own module because both ``__init__`` and ``client`` need it, and
``client`` cannot import from ``__init__`` without a cycle.

Read from metadata rather than written as a literal so it cannot disagree with
pyproject.toml. A hardcoded copy is exactly the kind of thing that stays at the
old number through a release and then misreports itself in the User-Agent, which
is the one place this value is visible to anyone debugging a production request.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wes-client")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    # Imported straight out of a source checkout with no install. Not an error
    # worth raising: the version is cosmetic here, and failing would make the
    # package unimportable for anyone poking at it with PYTHONPATH.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
