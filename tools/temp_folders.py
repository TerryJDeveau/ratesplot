#!/usr/bin/env python3
r"""The harnesses' temporary folders (batch 41.1): made in Temp as ``ratesplot_…``, removed when the harness ends.

Terry, 2026-11-10: "I recently had to clean up C:\Users\Terry\AppData\Local\Temp\ on Buddug
with a very large number of RatesPlot related subdirectories. They appeared to be growing
without bounds." Measured that day: the program itself makes nothing in Temp (the bake's
folders are removed when it is done, and the bake runs only in ``tools/bake_archives.py``
and the daily job). The harnesses made them with ``tempfile.mkdtemp``: ``verify_gui.py``
seven a run (its scratch APPDATA and six test folders, removed with ``ignore_errors`` or
not at all), ``check_last_good.py`` four (about 30 MB a run: two copies of the baked data,
10 MB each, and a folder of kept copies), ``check_refresh.py`` two. A folder a harness
makes is of use to that run alone, and to someone looking into a failed check soon after;
a day later, to no one. So no pass at the program's start: the harnesses tidy their own
(plan decision 124).

* ``make(name)``, in place of ``tempfile.mkdtemp``: a new folder ``ratesplot_NAME_xxxxxxxx``
  in Temp, removed at the harness's end;
* ``begin(keep)``, at a harness's start: the ``ratesplot_…`` folders in Temp more than a
  day old removed (a harness stopped part way, or one run before batch 41), with a line
  saying how many;
* ``end(failed)``, at its end: every folder it made removed, or kept when a check failed
  and ``--keep`` was given; the log names them either way. A harness that stops before
  ``end`` (an exception, ``parser.error``) is counted as failed (``atexit``).

A harness that makes no folder of its own need not call any of this.
"""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

# What every harness's folder is named from: the stale folders are found by it.
PREFIX = "ratesplot_"

# "More than a day old" (the plan, 41.1): a folder kept after a failed check is
# looked into the same day, and no harness runs for a day.
STALE_AFTER_SECONDS = 24 * 60 * 60

_made: list[Path] = []
_keep = False
_ended = False
_registered = False


def keep_asked(argv: list[str] | None = None) -> bool:
    """Whether ``--keep`` is on the command line, for a harness without a parser of its own."""
    return "--keep" in (sys.argv[1:] if argv is None else argv)


def temp_root() -> Path:
    """Temp, where every folder is made (``tempfile.gettempdir``: %TEMP% on Windows)."""
    return Path(tempfile.gettempdir())


def make(name: str) -> Path:
    """A new folder ``ratesplot_NAME_xxxxxxxx`` in Temp, removed when the harness ends (``end``)."""
    _register()
    path = Path(tempfile.mkdtemp(prefix=f"{PREFIX}{name}_"))
    _made.append(path)
    return path


def begin(keep: bool = False, *, root: Path | None = None, now: float | None = None) -> list[Path]:
    """At a harness's start: ``--keep`` noted, and the ``ratesplot_…`` folders more than a day old removed; return them.

    One line says how many, and names any that could not be removed (a file
    another program holds open); a later harness's start tries again.
    """
    global _keep
    _keep = keep
    _register()
    root = root or temp_root()
    removed, left = clear_stale(root=root, now=now)
    line = f"[temp] {len(removed)} {PREFIX}* folder{'' if len(removed) == 1 else 's'} more than a day old removed from {root}"
    if left:
        line += f"; {len(left)} could not be: {', '.join(path.name for path in left)}"
    print(line, flush=True)
    return removed


def clear_stale(*, root: Path | None = None, now: float | None = None) -> tuple[list[Path], list[Path]]:
    """Remove the ``ratesplot_…`` folders in ``root`` (Temp) last changed more than a day before ``now``.

    Returns (removed, could not be removed). A folder this harness made is
    never one (it is new); files named ``ratesplot_…`` are left alone, being
    no harness's.
    """
    root = root or temp_root()
    now = time.time() if now is None else now
    removed: list[Path] = []
    left: list[Path] = []
    for path in sorted(root.glob(f"{PREFIX}*")):
        try:
            if not path.is_dir() or path in _made or now - path.stat().st_mtime <= STALE_AFTER_SECONDS:
                continue
        except OSError:  # gone since the listing
            continue
        (removed if _remove(path) else left).append(path)
    return removed, left


def end(failed: bool) -> None:
    """At a harness's end: every folder it made removed, or kept if ``failed`` and ``--keep`` was given; the log names them.

    Called once; a second call does nothing.
    """
    global _ended
    if _ended:
        return
    _ended = True
    if not _made:
        return
    if failed and _keep:
        print(f"[temp] a check failed: kept for --keep: {', '.join(str(path) for path in _made)}", flush=True)
        return
    # Windows cannot remove the folder a process works in (check_refresh works in one of its own).
    here = Path.cwd()
    if any(here == path or path in here.parents for path in _made):
        os.chdir(temp_root())
    removed = [path for path in _made if _remove(path)]
    left = [path for path in _made if path not in removed]
    line = f"[temp] {len(removed)} temporary folder{'' if len(removed) == 1 else 's'} removed: {', '.join(path.name for path in removed)}"
    if failed:
        line += " (a check failed: --keep keeps them)"
    print(line, flush=True)
    if left:
        print(f"[temp] could not remove {', '.join(str(path) for path in left)}: a harness's start removes it after a day", flush=True)


def _remove(path: Path) -> bool:
    """Remove ``path`` and all it holds, a read-only file too; whether it is gone."""

    def writable_then_again(function, name, _exc) -> None:
        os.chmod(name, stat.S_IWRITE)
        function(name)

    try:
        shutil.rmtree(path, onexc=writable_then_again)
    except OSError:
        pass
    return not path.exists()


def _register() -> None:
    """The fallback for a harness that stops before ``end``: counted as failed, so ``--keep`` keeps its folders."""
    global _registered
    if not _registered:
        _registered = True
        atexit.register(lambda: end(failed=True))
