"""The version as the program shows it and saves it (batch 11.7): "v7.9, build: 1a2b3c4".

A module of its own, below ``frontend``, since ``export`` writes it into the
data it saves (batch 37.2) and ``frontend`` imports ``export``.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__


def _started_commit(folder: Path) -> str | None:
    """The commit ``folder``'s git checkout is at, abbreviated (``.git/HEAD``, a branch's ref or packed-refs); None without one.

    Read once, when the program starts: the web page's server pulls the
    daily job's commits without loading their code again, so the commit it
    started from is the one its code is.
    """
    git = folder / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="ascii").strip()
        if not head.startswith("ref: "):
            return head[:7] or None
        ref = head.removeprefix("ref: ")
        if (git / ref).is_file():
            return (git / ref).read_text(encoding="ascii").strip()[:7] or None
        for line in (git / "packed-refs").read_text(encoding="ascii").splitlines():
            if line.endswith(" " + ref):
                return line[:7]
    except (OSError, UnicodeDecodeError):
        pass
    return None


_STARTED_COMMIT = _started_commit(Path(__file__).resolve().parents[1])


def version_text() -> str:
    """The version as the window and the page show it (batch 11.7): "v6.5, build: 8c3e41b" (Terry, 2026-10-28), the commit left off where there is no checkout."""
    return f"v{__version__}, build: {_STARTED_COMMIT}" if _STARTED_COMMIT else f"v{__version__}"
