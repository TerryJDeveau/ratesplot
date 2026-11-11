#!/usr/bin/env python3
"""The daily re-bake (batch 19.2, decision 49): bake the live sources' history again, sort what changed, publish it.

Terry, 2026-10-22: "commit straight to main when a re-bake only adds new values; open a
pull request instead when it revises or refuses something." Run each day by
``.github/workflows/rebake.yml``; by hand, to see what it would do.

``python tools/rebake.py --out DIR`` runs each live source's bake (so far the Bank of
England's, the Bank of Canada's, FRED's, the ECB's, Eurostat's, the ONS's, the Bundesbank's and Statistics
Canada's, ``LIVE_BAKES``) with withdrawn dates accepted, so that every file holds what its source now gives,
and writes to DIR:

* ``append.txt``: the files whose only change is new values after the bake's last date
  (or a new file): they go straight to main;
* ``review.txt``: the files whose history changed: a value revised, a date added within the
  bake, or baked dates the source no longer gives: they go to a pull request;
* ``report.md``: a table of every series and what changed in it, each revision with its size
  (the first 20 of a series), and each download that failed (the run's summary);
* ``append_message.txt``, ``review_message.txt``, ``review.md``: the commit messages and the
  pull request's text.

A file unchanged is in neither list. A series whose download failed keeps its file; the
exit code is then 1, after DIR is written, so the job publishes what did change and then
shows the run failed. The run asks as a drawing does (batch 19.3): a failed request asked
once more only for a dropped connection or a server error, and a source that does not
answer (a timeout, a refused connection, an outage page, a bot check) asked nothing more
in the run, each of its other series failed with it.

Last, the U.S. Census's state and local debt (plan item 23.3, ``bake_census``): the Census
adds a fiscal year each summer. Each run asks only its listing for the next two years after
the module's last (``bake.census_years_listed``); when one is listed, it bakes
``ratesplot/us_archive_data.py`` again (``bake.bake_us_archives``: the historical database's
extract, then every year's estimates, about 74 MB in 2026), and the module goes to the pull
request even when it only gains the new year, since that year changes how the quarters
before it are split between state and local governments (their shares were held from the
year before). While the pull request waits, each day's run bakes it again, as it does every
series under review. ``--census`` bakes it whatever is listed: a test that the runner can.

``python tools/rebake.py --publish DIR [--dry-run]``, in the repository's checkout:
commits the files of ``append.txt`` and pushes them to main (pulling first if main has moved
meanwhile); puts the files of ``review.txt`` on the branch ``rebake-review``, made afresh
from main and force-pushed each day, and opens a pull request from it, or updates the one
already open, which Terry merges to accept the changes. A series under review keeps its old
file on main, new values included, until then; a drawing still asks the source for its recent
part. The commits are authored as Terry (this repository's rule) and committed by
github-actions[bot]. If the pull request cannot be opened (the repository's setting "Allow
GitHub Actions to create and approve pull requests" is off), the branch is pushed anyway, and
the exit code is 1. ``--dry-run`` prints the git and gh commands instead of running them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from ratesplot import http  # noqa: E402
from ratesplot.bake import (  # noqa: E402
    SeriesBake,
    bake_bbk_history,
    bake_boc_history,
    bake_boe_history,
    bake_changes,
    bake_ecb_history,
    bake_eurostat_history,
    bake_fred_history,
    bake_ons_history,
    bake_statcan_history,
    bake_us_archives,
    baked_census_debt,
    census_years_listed,
)

# Each live source baked as data files: its folder under ratesplot/data/ -> its name, its bake.
LIVE_BAKES = {
    "boe": ("Bank of England", bake_boe_history),
    "boc": ("Bank of Canada", bake_boc_history),
    "fred": ("FRED", bake_fred_history),
    "ecb": ("ECB", bake_ecb_history),
    "eurostat": ("Eurostat", bake_eurostat_history),
    "ons": ("ONS", bake_ons_history),
    "bbk": ("Bundesbank", bake_bbk_history),
    "statcan": ("Statistics Canada", bake_statcan_history),
}
# The U.S. Census's state and local debt (23.3): a data module, not a file per series; its two
# levels reported as two series of it. Their "source" sends them to review (``destination``).
CENSUS = "census"
CENSUS_NAME = "U.S. Census"
CENSUS_MODULE = ROOT / "ratesplot" / "us_archive_data.py"
CENSUS_LEVELS = {"p": "Census state debt", "m": "Census local debt"}
REVIEW_BRANCH = "rebake-review"
AUTHOR = "Terry J. Deveau <terryjdeveau@gmail.com>"
COMMITTER = {"GIT_COMMITTER_NAME": "github-actions[bot]", "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}


def destination(result: SeriesBake) -> str | None:
    """Where a series' file goes: "main" (new values only, or a new file), "review" (its history changed), None (unchanged or failed).

    A new Census fiscal year goes to review too (23.3): it changes how the quarters
    before it are split between state and local governments, a revision of drawn values.
    """
    changes = result.changes
    if result.error is not None or changes is None:
        return None
    if changes.history_changed:
        return "review"
    if changes.new_file or len(changes.added):
        return "review" if result.source == CENSUS else "main"
    return None


def _census_series(rows: list[tuple[str, float]]) -> pd.Series:
    """One level of ``EMBEDDED_US_DEBT_BY_LEVEL`` as a date-indexed series, for ``bake_changes``."""
    return pd.Series({pd.Timestamp(date): float(value) for date, value in rows}, dtype=float).sort_index()


def _last_census_year(levels: dict[str, list[tuple[str, float]]]) -> int:
    """The last fiscal year of an ``EMBEDDED_US_DEBT_BY_LEVEL`` (its state level's, as ``check_sources`` reads it)."""
    return max(pd.Timestamp(date).year for date, _value in levels["p"])


def bake_census(force: bool = False, module: Path = CENSUS_MODULE) -> tuple[list[SeriesBake], str]:
    """The Census's state and local debt (23.3): ``(a result per level, a line for the report)``.

    Bakes ``module`` again only when the Census lists a fiscal year newer than its
    last (or ``force``). If no value changed (the bake rewrites the module's
    "Generated ... on" date line in any case), the module is put back as it was, so
    nothing is published. A failure, of the listing or the bake, keeps the module
    and fails both levels, so the run is marked failed.
    """
    before = module.read_bytes()
    old = baked_census_debt(module)
    baked_year = _last_census_year(old)
    try:
        listed = census_years_listed(baked_year)
        if not listed and not force:
            return [], f"{CENSUS_NAME}: baked to fiscal {baked_year}, the newest the Census lists; nothing downloaded but its listing."
        bake_us_archives(module)
    except Exception as exc:  # the job reports it and goes on; the module is kept
        module.write_bytes(before)
        failed = [SeriesBake(CENSUS, code, module, error=f"{type(exc).__name__}: {exc}") for code in CENSUS_LEVELS.values()]
        return failed, f"{CENSUS_NAME}: not baked ({type(exc).__name__}: {exc}); the module kept."
    new = baked_census_debt(module)
    results = []
    for key, code in CENSUS_LEVELS.items():
        after = _census_series(new[key])
        results.append(SeriesBake(CENSUS, code, module, changes=bake_changes(_census_series(old[key]), after),
                                  written=True, values=len(after), last=after.index[-1]))
    why = f"fiscal {', '.join(map(str, listed))} listed" if listed else "asked by --census"
    if not any(destination(result) for result in results):
        module.write_bytes(before)
        return results, f"{CENSUS_NAME}: baked again ({why}), every value as the module's; the module kept."
    return results, f"{CENSUS_NAME}: baked again ({why}), to fiscal {_last_census_year(new)}; for review."


def repository_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _row(name: str, result: SeriesBake) -> str:
    changes = result.changes
    if changes is None:
        return f"| {name} | {result.code} | | | | | | | failed |"
    counts = (len(changes.added), len(changes.revised), len(changes.filled), len(changes.lost))
    last = f"{result.last:%Y-%m-%d}" if result.last is not None else ""
    return (f"| {name} | {result.code} | {result.values:,} | {last} | " + " | ".join(f"{count:,}" for count in counts)
            + f" | {destination(result) or 'unchanged'} |")


def _paths(results: list[tuple[str, SeriesBake]]) -> str:
    """The files of ``results``, one a line, each once (the Census's two levels share their module)."""
    return "".join(path + "\n" for path in dict.fromkeys(repository_path(result.path) for _, result in results))


# Said in the pull request when the Census's module is in it (23.3).
CENSUS_REVIEW_NOTE = (
    "A new Census fiscal year comes here rather than to main because it changes drawn values: the "
    "quarters since the year before were split between state and local governments by that year's "
    "shares, held, and are now split by shares drawn between the two years."
)


def write_outputs(out: Path, results: list[tuple[str, SeriesBake]], today: dt.date, notes: list[str] | None = None) -> None:
    """The lists, the report and the messages (see the module's docstring); ``notes`` are lines for the report."""
    out.mkdir(parents=True, exist_ok=True)
    to_main = [(name, result) for name, result in results if destination(result) == "main"]
    to_review = [(name, result) for name, result in results if destination(result) == "review"]
    failed = [(name, result) for name, result in results if result.error is not None]
    (out / "append.txt").write_text(_paths(to_main), encoding="utf-8")
    (out / "review.txt").write_text(_paths(to_review), encoding="utf-8")
    census_note = [CENSUS_REVIEW_NOTE] if any(result.source == CENSUS for _, result in to_review) else []

    report = [
        f"## Re-bake of {today:%Y-%m-%d}",
        "",
        f"{len(to_main)} series with new values only (to main), {len(to_review)} whose history changed (for review), "
        f"{len(failed)} not downloaded, {len(results) - len(to_main) - len(to_review) - len(failed)} unchanged.",
        *(["", *notes] if notes else []),
        "",
        "| Source | Series | Values | Last date | New | Revised | Added within | Withdrawn | Goes to |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
        *(_row(name, result) for name, result in results),
    ]
    review_sections = []
    for name, result in to_review:
        review_sections += ["", f"### {result.code} ({name}), for review", ""]
        review_sections += [f"- {line}" for line in result.changes.lines]
    report += review_sections
    if failed:
        report += ["", "### Not downloaded (each file kept as it was)", ""]
        report += [f"- {result.code} ({name}): {result.error}" for name, result in failed]
    (out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    added = sum(len(result.changes.added) for _, result in to_main)
    (out / "append_message.txt").write_text(
        f"Re-bake {today:%Y-%m-%d}: {added:,} new value{'' if added == 1 else 's'} in {len(to_main)} series\n\n"
        "The daily re-bake (tools/rebake.py, .github/workflows/rebake.yml): series whose only\n"
        "change is new values after their last baked date.\n\n"
        + "".join(f"{result.code} ({name}): {result.changes.lines[-1]}\n" for name, result in to_main),
        encoding="utf-8",
    )
    codes = ", ".join(result.code for _, result in to_review)
    (out / "review_message.txt").write_text(
        f"Re-bake {today:%Y-%m-%d}: history changed in {codes}\n\n"
        "The daily re-bake found values revised, dates added within the bake, or baked dates\n"
        "withdrawn by the source. On the branch rebake-review for Terry to look at; merging it\n"
        "accepts the source's history.\n\n"
        + "".join(textwrap.fill(line, 90) + "\n\n" for line in census_note)
        + "".join(f"{result.code} ({name}): {line}\n" for name, result in to_review for line in result.changes.lines),
        encoding="utf-8",
    )
    (out / "review.md").write_text(
        f"The daily re-bake of {today:%Y-%m-%d} found history changed in the source for {codes}: "
        "values revised, dates added within the bake, or baked dates no longer given. Merging this "
        "pull request accepts the source's history; until then these series keep their files on "
        "main as they were (a drawing still asks the source for its last months). Each day's "
        "re-bake updates this branch and this pull request.\n\n"
        + "".join(line + "\n\n" for line in census_note) + "\n".join(report) + "\n",
        encoding="utf-8",
    )


def bake(out: Path, census: bool = False) -> int:
    """Every live source's bake, then the Census's (``bake_census``; ``census`` bakes it whatever is listed); DIR written; 1 if any failed."""
    results: list[tuple[str, SeriesBake]] = []
    # One pass, as a drawing: a source that does not answer is asked nothing more in it (19.3).
    with http.drawing_downloads():
        for _folder, (name, bake_source) in LIVE_BAKES.items():
            results += [(name, result) for result in bake_source(accept_withdrawn=True)]
        census_results, census_line = bake_census(force=census)
    results += [(CENSUS_NAME, result) for result in census_results]
    write_outputs(out, results, dt.datetime.now(dt.timezone.utc).date(), [census_line])
    print((out / "report.md").read_text(encoding="utf-8"))
    return 1 if any(result.error is not None for _, result in results) else 0


def run(command: list[str], dry_run: bool, *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess | None:
    """Run ``command`` in the repository (the committer as github-actions[bot]); with ``dry_run``, print it only."""
    print("$ " + " ".join(shlex.quote(part) for part in command), flush=True)
    if dry_run:
        return None
    return subprocess.run(command, cwd=ROOT, check=check, text=True, capture_output=capture, env=os.environ | COMMITTER)


def files_in(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def publish(out: Path, dry_run: bool) -> int:
    to_main, to_review = files_in(out / "append.txt"), files_in(out / "review.txt")
    if not to_main and not to_review:
        print("Nothing changed: nothing to publish.")
        return 0
    if to_main:
        run(["git", "add", "--", *to_main], dry_run)
        run(["git", "commit", "--author", AUTHOR, "-F", str(out / "append_message.txt")], dry_run)
        for _attempt in range(3):
            pushed = run(["git", "push", "origin", "HEAD:main"], dry_run, check=False)
            if pushed is None or pushed.returncode == 0:
                break
            # main moved since the checkout (a push from Buddug): put this commit after it.
            run(["git", "pull", "--rebase", "--autostash", "origin", "main"], dry_run)
        else:
            print("Could not push to main after three tries.")
            return 1
    if not to_review:
        return 0
    run(["git", "switch", "-C", REVIEW_BRANCH], dry_run)
    run(["git", "add", "--", *to_review], dry_run)
    run(["git", "commit", "--author", AUTHOR, "-F", str(out / "review_message.txt")], dry_run)
    run(["git", "push", "--force", "origin", f"{REVIEW_BRANCH}:{REVIEW_BRANCH}"], dry_run)
    title = (out / "review_message.txt").read_text(encoding="utf-8").splitlines()[0]
    listed = run(["gh", "pr", "list", "--head", REVIEW_BRANCH, "--state", "open", "--json", "number", "--jq", ".[0].number"],
                 dry_run, check=False, capture=True)
    number = listed.stdout.strip() if listed is not None and listed.returncode == 0 else ""
    body = str(out / "review.md")
    command = (["gh", "pr", "edit", number, "--title", title, "--body-file", body] if number
               else ["gh", "pr", "create", "--base", "main", "--head", REVIEW_BRANCH, "--title", title, "--body-file", body])
    made = run(command, dry_run, check=False)
    if made is not None and made.returncode != 0:
        repository = os.environ.get("GITHUB_REPOSITORY", "TerryJDeveau/ratesplot")
        print(f"The pull request could not be opened or updated. The changes are on the branch {REVIEW_BRANCH}: "
              f"https://github.com/{repository}/compare/main...{REVIEW_BRANCH}. If GitHub refused it, the "
              "repository's setting is off: Settings, Actions, General, Workflow permissions, "
              "\"Allow GitHub Actions to create and approve pull requests\".")
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--out", type=Path, help="bake, and write the lists, report and messages into this folder")
    task.add_argument("--publish", type=Path, help="commit and push what a bake wrote into this folder")
    parser.add_argument("--dry-run", action="store_true", help="with --publish: print the git and gh commands only")
    parser.add_argument("--census", action="store_true",
                        help="with --out: bake the Census's state and local debt even when it lists no newer fiscal year (a test that the runner can)")
    args = parser.parse_args(argv)
    if args.census and args.out is None:
        parser.error("--census goes with --out")
    return bake(args.out, args.census) if args.out is not None else publish(args.publish, args.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
