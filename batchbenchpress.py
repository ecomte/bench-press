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

after a run:
  Tell Claude "publish everyone's lineups" (or name specific people) to update the phone links.
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
        write_site_index(args.site, [u for u, c, _ in results if c == 0])

    print("\n" + "=" * 64)
    print("Batch done")
    for user, code, secs in results:
        print("  %-24s %s  (%.0fs)" % (user, "ok" if code == 0 else "FAILED (exit %d)" % code, secs))
    failed = [u for u, c, _ in results if c != 0]
    if failed:
        print("\nRe-run just the failed ones with:  python3 batchbenchpress.py " + " ".join(failed))
    if not args.site:
        print('\nPhone links: tell Claude "publish everyone\'s lineups".')
    sys.exit(1 if failed else 0)


def write_site_index(site, users):
    """Landing page for the hosted site: one link per person who built successfully."""
    import html
    links = "\n".join('    <li><a href="%s/">%s</a></li>' % (html.escape(u.lstrip("@").lower()), html.escape(u))
                      for u in users)
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bench Press</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; }
    li { margin: 8px 0; }
  </style>
</head>
<body>
  <h1>Bench Press</h1>
  <p>Let's eat a W. Pick your page:</p>
  <ul>
%s
  </ul>
</body>
</html>
""" % links
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write(page)


if __name__ == "__main__":
    main()
