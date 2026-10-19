#!/usr/bin/env python3
"""Where does Sleeper's API keep auto-subs? Run this on the Mac after setting an auto-sub
in the Sleeper app:

  python3 tools/autosub_probe.py            your leagues, this week
  python3 tools/autosub_probe.py -w 8       a different week

It prints every field whose name mentions "sub" in your league settings, roster and
matchup, and whether Bench Press already reads your auto-subs. The full responses are
saved to data/autosub_probe.json. If nothing is found, AUTO_SUB_KEYS in
python-subscripts/analysis.py (and the same list in web/benchpress.js) is what to adjust.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "python-subscripts"))

import analysis as A  # noqa: E402
import sleeper as S  # noqa: E402


def sub_fields(obj, path=""):
    """(path, value) for every key anywhere in obj whose name contains 'sub'."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = "%s.%s" % (path, k) if path else str(k)
            if "sub" in str(k).lower():
                out.append((p, v))
            out += sub_fields(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += sub_fields(v, "%s[%d]" % (path, i))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", "--week", type=int)
    ap.add_argument("-u", "--user")
    args = ap.parse_args()
    with open(os.path.join(HERE, "config", "config.json")) as f:
        cfg = json.load(f)
    me = S.user(args.user.lstrip("@") if args.user else (cfg.get("user_id") or cfg["username"]))
    state = S.nfl_state() or {}
    season = str(cfg.get("season") or state.get("league_season") or state.get("season"))
    week = args.week or int(state.get("week") or state.get("display_week") or 1)
    players = S.players() or {}
    name = lambda pid: A.player_name(pid, players.get(str(pid))) if str(pid) in players else pid
    print("Sleeper user %s, season %s, week %d\n" % (me.get("username"), season, week))
    dump = {}
    for lg in S.leagues(me["user_id"], season):
        lid = lg["league_id"]
        # straight from Sleeper, never the cache: an auto-sub can change any minute
        rosters = S._fetch("%s/league/%s/rosters" % (S.V1, lid)) or []
        mu = S._fetch("%s/league/%s/matchups/%d" % (S.V1, lid, week)) or []
        mine = next((r for r in rosters if r.get("owner_id") == me["user_id"] or me["user_id"] in (r.get("co_owners") or [])), None)
        if not mine:
            continue
        mmu = next((m for m in mu if m.get("roster_id") == mine["roster_id"]), None)
        # every team, not just this user's: the opponent's auto-subs matter too
        dump[lg["name"]] = {"league": lg, "roster": mine, "matchup": mmu, "all_rosters": rosters, "all_matchups": mu}
        print("== %s" % lg["name"])
        print("  roster keys:  %s" % sorted(mine))
        print("  roster metadata keys: %s" % sorted((mine.get("metadata") or {})))
        print("  matchup keys: %s" % sorted(mmu or {}))
        print("  every matchup key: %s" % sorted(set(k for m in mu for k in m)))
        print("  every roster key:  %s" % sorted(set(k for r in rosters for k in r)))
        found = sub_fields({"league": lg, "rosters": rosters, "matchups": mu})
        for p, v in found:
            print("  'sub' field:  %s = %s" % (p, json.dumps(v)[:300]))
        if not found:
            print("  no field mentions 'sub'")
        subs = A.auto_subs(mmu, mine)
        print("  Bench Press reads: %s\n" % (", ".join("%s covered by %s" % (name(a), name(b)) for a, b in subs.items()) or "no auto-subs"))
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    path = os.path.join(HERE, "data", "autosub_probe.json")
    with open(path, "w") as f:
        json.dump(dump, f, indent=1)
    print("Full responses: %s" % path)


if __name__ == "__main__":
    main()
