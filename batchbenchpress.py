#!/usr/bin/env python3
"""Batch Bench Press: run benchpress.py for me and my friends in one go.

Runs `benchpress.py -u <username> -o` once per username, in order. The usernames
come from "batch_users" in config/config.json, unless you name some on the command line.

examples:
  python3 batchbenchpress.py                       everyone in batch_users
  python3 batchbenchpress.py CalebJones23 ryaneorchard   just these two
  python3 batchbenchpress.py --no-open             don't open a browser tab for each
  python3 batchbenchpress.py -w 8                  look ahead to week 8 for everyone
  python3 batchbenchpress.py --no-open --site site build the hosted site (what GitHub Actions runs)

Shared data (player list, weekly stats, projections) is downloaded on the first
run and reused by the rest, so later users only take a few seconds each.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "benchpress.py")


def main():
    ap = argparse.ArgumentParser(prog="batchbenchpress.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("users", nargs="*", metavar="USERNAME",
                    help="Sleeper usernames to run (default: batch_users in config/config.json)")
    ap.add_argument("-w", "--week", type=int, metavar="N", help="week to set lineups for (passed to every run)")
    ap.add_argument("--no-open", action="store_true", help="don't open each lineup page in the browser")
    ap.add_argument("--site", metavar="DIR",
                    help="write each page to DIR/<username>/index.html plus a DIR/index.html list of everyone")
    args = ap.parse_args()

    with open(os.path.join(HERE, "config", "config.json")) as f:
        cfg = json.load(f)
    users = args.users or cfg.get("batch_users") or [cfg["username"]]

    results = []
    for i, user in enumerate(users, 1):
        cmd = [sys.executable, MAIN, "-u", user]
        if not args.no_open:
            cmd.append("-o")
        if args.week:
            cmd += ["-w", str(args.week)]
        if args.site:
            cmd += ["--site", args.site]
        print("\n" + "=" * 64)
        print("[%d/%d] %s" % (i, len(users), user))
        print("=" * 64, flush=True)
        start = time.time()
        code = subprocess.call(cmd, cwd=HERE)
        results.append((user, code, time.time() - start))

    if args.site:
        write_site_index(args.site, [u for u, c, _ in results if c == 0], cfg.get("ntfy_topic"))

    print("\n" + "=" * 64)
    print("Batch done")
    for user, code, secs in results:
        print("  %-24s %s  (%.0fs)" % (user, "ok" if code == 0 else "FAILED (exit %d)" % code, secs))
    failed = [u for u, c, _ in results if c != 0]
    if failed:
        print("\nRe-run just the failed ones with:  python3 batchbenchpress.py " + " ".join(failed))
    sys.exit(1 if failed else 0)


def write_site_index(site, users, ntfy_topic=None):
    """Landing page for the hosted site (a username search that links to the pages that built),
    the live/?u=<name> page for anyone else, and the shared refresh script."""
    import shutil
    sys.path.insert(0, os.path.join(HERE, "python-subscripts"))
    import render
    os.makedirs(os.path.join(site, "live"), exist_ok=True)
    with open(os.path.join(site, "live", "index.html"), "w") as f:
        f.write(render.live_page_html())
    shutil.copy(os.path.join(HERE, "web", "benchpress.js"), os.path.join(site, "benchpress.js"))
    page = render.landing_html(users, ntfy_topic)
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write(page)


if __name__ == "__main__":
    main()
