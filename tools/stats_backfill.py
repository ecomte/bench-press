#!/usr/bin/env python3
"""One-time download of past seasons' weekly stats into the repo (data/history/stats/), for
player trends. Uses the same Sleeper stats call as Bench Press (sleeper.week_stats), so the
raw weeks also land in data/cache/ and later runs reuse them. Run it on the Mac:

  python3 tools/stats_backfill.py                 the 5 seasons before this one
  python3 tools/stats_backfill.py -n 3            the 3 seasons before this one
  python3 tools/stats_backfill.py 2021 2022       just these seasons

Finished seasons don't change, so this only needs running once (again next year to add
the season that just ended). Read the files back with history.load(season).
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "python-subscripts"))

import history as H  # noqa: E402
import sleeper as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("seasons", nargs="*", help="seasons to fetch (default: the N before this one)")
    ap.add_argument("-n", type=int, default=5, help="how many past seasons (default 5)")
    args = ap.parse_args()

    if args.seasons:
        seasons = args.seasons
    else:
        now = int(S.nfl_state()["season"])
        seasons = [str(now - back) for back in range(args.n, 0, -1)]

    for season in seasons:
        weekly = {}
        for w in range(1, 19):  # 18-week seasons since 2021; an empty week 18 is just skipped
            rows = S.week_stats(season, w, final=True)
            if rows:
                weekly[w] = rows
            print("  %s week %2d: %d rows" % (season, w, len(rows)), end="\r")
        if not weekly:
            print("%s: no stats from Sleeper, skipped          " % season)
            continue
        data = H.save(season, weekly)
        games = sum(len(r) for r in data["weeks"].values())
        size = os.path.getsize(H.path(season)) / 1e6
        print("%s: %d weeks, %d player-games, %d players -> %s (%.1f MB)" % (
            season, len(data["weeks"]), games, len(data["players"]),
            os.path.relpath(H.path(season), HERE), size))


if __name__ == "__main__":
    main()
