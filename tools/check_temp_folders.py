#!/usr/bin/env python3
"""Check ``tools/temp_folders.py`` (batch 41.1): a harness's folders removed at its end, kept on a failed check with --keep; old ones cleared.

* each case run as a harness would be, in a process of its own (the helper's state is
  the process's): a passing run, a failed run, a failed run with ``--keep``, a run
  stopped by an exception with and without ``--keep``, a run that works inside its folder;
* the stale folders, in a made-up folder in place of Temp: those more than a day old
  removed, a younger one, a file of the same name and another program's folder kept,
  a read-only file no obstacle.

    python tools/check_temp_folders.py

Exit status 0 only if every check passes. Its own folders are removed at its end.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import temp_folders  # noqa: E402

DAY = temp_folders.STALE_AFTER_SECONDS

# A harness in miniature: one folder made, a file in it, then the ending asked for.
HARNESS = """
import os, sys
sys.path.insert(0, {tools!r})
import temp_folders
temp_folders.begin(temp_folders.keep_asked())
folder = temp_folders.make("check_temp_folders_case")
(folder / "a file").write_text("x")
print("FOLDER", folder)
how = sys.argv[1]
if how == "inside":
    os.chdir(folder)
if how == "raises":
    raise RuntimeError("stopped part way")
temp_folders.end(failed=how == "fails")
"""


def run_case(how: str, *flags: str) -> tuple[Path, str]:
    """Run the miniature harness; return its folder and its output."""
    done = subprocess.run([sys.executable, "-c", HARNESS.format(tools=str(TOOLS)), how, *flags],
                          capture_output=True, text=True, timeout=60)
    output = done.stdout + done.stderr
    named = [line.split(" ", 1)[1] for line in done.stdout.splitlines() if line.startswith("FOLDER ")]
    return Path(named[0]) if named else Path(), output


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    temp_folders.begin(temp_folders.keep_asked())
    kept: list[Path] = []
    print("-- a harness's own folders")
    for how, flags, stays, said in (
        ("passes", (), False, "1 temporary folder removed: ratesplot_check_temp_folders_case_"),
        ("fails", (), False, "(a check failed: --keep keeps them)"),
        ("fails", ("--keep",), True, "[temp] a check failed: kept for --keep: "),
        ("raises", (), False, "1 temporary folder removed"),
        ("raises", ("--keep",), True, "kept for --keep"),
        ("inside", (), False, "1 temporary folder removed"),
    ):
        folder, output = run_case(how, *flags)
        what = {"passes": "passes", "fails": "fails", "raises": "stops on an exception", "inside": "works inside its folder"}[how]
        label = f"a run that {what}{' with --keep' if flags else ''}: its folder {'kept' if stays else 'removed'}, and said"
        check(label, folder.name.startswith("ratesplot_check_temp_folders_case_") and folder.exists() == stays and said in output, output)
        if folder.name and folder.exists():
            kept.append(folder)
    check("the start's line said how many old folders were removed", "more than a day old removed from" in output, output)
    for folder in kept:  # the cases kept for --keep: this check's to remove
        temp_folders._remove(folder)

    print("-- the folders more than a day old")
    root = temp_folders.make("check_temp_folders_root")
    now = time.time()
    ages = {"ratesplot_old_a": 2 * DAY, "ratesplot_old_b": DAY + 60, "ratesplot_young": DAY - 60, "other_old": 3 * DAY}
    for name, age in ages.items():
        (root / name / "inner").mkdir(parents=True)
        (root / name / "inner" / "data.csv").write_text("1,2")
        os.utime(root / name, (now - age, now - age))
    read_only = root / "ratesplot_old_a" / "inner" / "data.csv"
    os.chmod(read_only, stat.S_IREAD)
    (root / "ratesplot_file_old").write_text("a file, no harness's")
    os.utime(root / "ratesplot_file_old", (now - 3 * DAY, now - 3 * DAY))
    removed, left = temp_folders.clear_stale(root=root, now=now)
    check("older than a day: removed, a read-only file in one too", sorted(path.name for path in removed) == ["ratesplot_old_a", "ratesplot_old_b"]
          and not left and not (root / "ratesplot_old_a").exists(), (removed, left))
    check("younger than a day: kept", (root / "ratesplot_young").is_dir())
    check("a folder not named ratesplot_*: kept, however old", (root / "other_old").is_dir())
    check("a file named ratesplot_*: kept", (root / "ratesplot_file_old").is_file())
    # In Temp itself, as a harness's start runs it: a folder this run made, dated three days back, is not stale.
    os.utime(root, (now - 3 * DAY, now - 3 * DAY))
    removed, _left = temp_folders.clear_stale()
    check("a folder this run made: never stale, however old it looks", root.is_dir() and root not in removed, removed)

    print(f"[temp folders] {sum(results)} of {len(results)} checks passed")
    temp_folders.end(failed=not all(results))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
