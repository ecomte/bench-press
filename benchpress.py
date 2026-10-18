#!/usr/bin/env python3
"""Bench Press: fantasy football lineup helper for my Sleeper leagues.

Syncs my rosters, pulls Sleeper stats + projections, ranks every defense against
each position, recommends a lineup per league, and flags byes, injuries and empty slots.

examples:
  python3 benchpress.py                next week with games left, for me (EComte)
  python3 benchpress.py --open         same, then open lineups/lineups-ecomte.html in the browser
  python3 benchpress.py -w 8           look ahead to week 8
  python3 benchpress.py -u SomeFriend  run it for a friend -> lineups/lineups-somefriend.html
  python3 benchpress.py -u SomeFriend -w 8 -o
  python3 batchbenchpress.py           me + every friend in config batch_users

what it writes (in this folder):
  lineups/lineups-<user>.html    tabbed lineup page, one tab per team (mine: lineups/lineups-ecomte.html)
  reports/<season>_weekNN.md     weekly report: give this to Claude
  sheets/*.csv                   QB/RB/WR/TE/K/DEF + DEF_vs_POS, shared by everyone
                                 (rostered_by column says whose team each player is on)
  sheets/<user>/                 that person's lineups.csv and game_log.csv
  data/                          API cache, roster snapshot, artifact.html (phone copy)
  (a friend's run uses lineups/lineups-<user>.html and reports/<user>/)

after a run:
  - Make the swaps in the Sleeper app (the API is read-only).
  - Phone: tell Claude "publish my lineups" to update
    https://claude.ai/artifact/88VThYJeg3jj7zhtVWaGMm
  - Deeper look: paste ANALYZE-PROMPT.md into a Claude chat.

best times to run: Tue/Wed after waivers, and Sunday morning for late injury news.
settings (username, league nicknames, tab order, matchup weight): config/config.json
"""

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# helper modules live in python-subscripts/, settings + page template in config/
sys.path.insert(0, os.path.join(HERE, "python-subscripts"))

import analysis as A  # noqa: E402
import sleeper as S  # noqa: E402

SHEETS = os.path.join(HERE, "sheets")
REPORTS = os.path.join(HERE, "reports")
DATA = os.path.join(HERE, "data")
LINEUPS = os.path.join(HERE, "lineups")  # local lineup pages, one per person


def load_config():
    path = os.path.join(HERE, "config", "config.json")
    with open(path) as f:
        return json.load(f)


def eastern_stamp(now):
    """Run time for the pages and report, shown in US Eastern time with its label
    (EDT in summer, EST in winter), e.g. "Sat Oct 17, 3:22 PM EDT"."""
    try:
        from zoneinfo import ZoneInfo
        when = now.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # no time zone data: fall back to this Mac's local time
        when = now.astimezone()
    return when.strftime("%a %b %d, %I:%M %p %Z").replace(" 0", " ")


def write_csv(path, rows, cols=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        cols = cols or ["(no rows)"]
    cols = cols or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser(prog="benchpress.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", "--week", type=int, metavar="N",
                    help="week to set lineups for (default: the next week with games left)")
    ap.add_argument("-o", "--open", action="store_true",
                    help="open the lineup page in your browser when done")
    ap.add_argument("-u", "--user", metavar="USERNAME",
                    help="run for a different Sleeper username, e.g. a friend (a leading @ is fine). "
                         "Output goes to lineups/lineups-<username>.html, reports/<username>/ and sheets/<username>/")
    args = ap.parse_args()

    cfg = load_config()
    W = float(cfg.get("matchup_weight", 0.5))
    nick = cfg.get("league_nicknames", {}) if not (args.user and args.user.lstrip("@").lower() != cfg["username"].lower()) else {}
    now = dt.datetime.now()

    # ---- who am I, what week is it ------------------------------------------------
    print("Sleeper: looking up %s" % (args.user or cfg["username"]))
    other = args.user and args.user.lstrip("@").lower() != cfg["username"].lower()
    if other:
        uname = args.user.lstrip("@")
        me = S.user(uname)
    else:
        uname = cfg["username"]
        me = S.user(cfg.get("user_id") or uname)
    if not me:
        sys.exit("Couldn't find Sleeper user %r" % uname)
    tag = me.get("username") or uname.lower()
    tag = tag.lower()
    # Position sheets + DEF_vs_POS are shared by everyone (sheets/); lineups and game log are per person.
    SHEETS = os.path.join(HERE, "sheets")
    USER_SHEETS = os.path.join(SHEETS, tag)
    REPORTS = os.path.join(HERE, "reports", tag) if other else os.path.join(HERE, "reports")
    if other:
        print("Running for %s (not you): output goes to lineups/lineups-%s.html" % (me.get("display_name") or uname, tag))
    user_id = me["user_id"]
    state = S.nfl_state() or {}
    season = str(cfg.get("season") or state.get("league_season") or state.get("season"))
    sched = A.Schedule(S.schedule(season))
    week = args.week or sched.target_week()
    print("Season %s, setting lineups for week %d" % (season, week))

    # ---- shared data ----------------------------------------------------------------
    print("Players database (refreshed at most once a day)...")
    players = S.players() or {}
    weekly = {}
    for w in range(1, week):
        if not sched.week_complete(w) and w != week - 1:
            continue
        weekly[w] = S.week_stats(season, w, final=(w < week - 1))
    print("Stats: weeks %s" % (", ".join(str(w) for w in sorted(weekly)) or "none yet"))
    proj_list = S.week_projections(season, week)
    proj = {r["player_id"]: r for r in proj_list if r.get("player_id")}
    print("Projections: %d players for week %d" % (len(proj), week))
    today = dt.date.today()
    started = [t for t in sched.by_week.get(week, {}) if A.game_state(sched.game(week, t), today) != "pre"]
    live_stats = {}
    if started:
        for r in S.week_stats(season, week, final=False, max_age_hours=0.1):
            if r.get("player_id"):
                live_stats[r["player_id"]] = r.get("stats") or {}
        print("Week %d games already started for %d teams; pulled their points" % (week, len(started)))

    dvp = A.defense_vs_position(weekly)
    logs, meta = A.build_player_logs(weekly, dvp)
    inj = A.team_injuries(players)
    byes_now = sched.byes(week)

    def injury_of(pid):
        pr = proj.get(pid)
        if pr and pr.get("player") is not None:
            return (pr["player"].get("injury_status") or "")
        return (players.get(pid) or {}).get("injury_status") or ""

    # ---- leagues ------------------------------------------------------------------------
    leagues = [l for l in S.leagues(user_id, season) if l.get("status") not in ("pre_draft",)]
    leagues = [l for l in leagues if l["league_id"] not in cfg.get("ignore_leagues", [])]
    order = cfg.get("league_order") or []
    leagues.sort(key=lambda l: (order.index(l["league_id"]) if l["league_id"] in order else 99, l["name"]))
    print("Leagues: %s" % ", ".join(l["name"] for l in leagues))

    snapshot_path = os.path.join(DATA, "rosters_snapshot%s.json" % (("_" + tag) if other else ""))
    old_snap = {}
    if os.path.exists(snapshot_path):
        with open(snapshot_path) as f:
            old_snap = json.load(f)
    new_snap = {}

    owned = {}  # pid -> [league short names]
    out_leagues = []

    for lg in leagues:
        lid = lg["league_id"]
        short = nick.get(lid) or nick.get(lg["name"]) or lg["name"]
        ss = lg.get("scoring_settings") or {}
        rp = lg.get("roster_positions") or []
        slots = [s for s in rp if s not in ("BN", "IR", "TAXI")]
        rosters = S.rosters(lid)
        users = {u["user_id"]: u for u in S.league_users(lid)}
        mine = next((r for r in rosters if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])), None)
        if not mine:
            print("  ! couldn't find my roster in %s" % lg["name"])
            continue
        roster_ids = {r["roster_id"]: r for r in rosters}

        all_pids = [p for p in (mine.get("players") or []) if p]
        reserve = set(mine.get("reserve") or [])
        taxi = set(mine.get("taxi") or [])
        for pid in all_pids:
            owned.setdefault(pid, []).append(short)

        # roster changes since last run
        prev = set(old_snap.get(lid, []))
        added = [p for p in all_pids if prev and p not in prev]
        dropped = [p for p in prev if p not in set(all_pids)]
        new_snap[lid] = all_pids

        def info(pid):
            pl = players.get(pid) or (meta.get(pid) or {})
            pos = A.player_pos(pl) or ("DEF" if pid.isalpha() else "?")
            team = pid if pos == "DEF" else (pl.get("team") or "")
            pr = proj.get(pid)
            status = injury_of(pid)
            game = sched.game(week, team) if team else None
            gstate = A.game_state(game, today)
            locked = gstate in ("live", "final")
            actual = A.score(live_stats[pid], ss) if (locked and pid in live_stats) else (0.0 if locked else None)
            sleeper_pts = A.score((pr or {}).get("stats"), ss)
            opp = game["opp"] if game else None
            row = dvp.get(pos, {}).get(opp) if opp else None
            mult = row["mult"] if row else 1.0
            adj = sleeper_pts * (1 + W * (mult - 1))
            why = ""
            if not team:
                why = "Free agent / no team"
            elif not game:
                why = "BYE"
            elif status in A.OUT_STATUSES:
                why = status
            factor = 0.25 if status == "Doubtful" else 1.0
            lg_log = logs.get(pid, [])
            pts = [A.score(e["stats"], ss) for e in lg_log]
            notes = []
            if opp and pos in ("QB", "RB", "WR", "TE"):
                hurt = [x for x in inj.get(opp, {}).get("def", []) if x["status"] in ("Out", "IR", "Doubtful", "PUP", "Sus")]
                if hurt:
                    notes.append("Opp D banged up: " + ", ".join("%s %s (%s)" % (x["pos"], x["name"], x["status"]) for x in hurt[:4]))
            if team and pos in ("RB", "WR", "TE"):
                for x in inj.get(team, {}).get("off", []):
                    if x["pos"] == "QB" and x["status"] in ("Out", "IR", "Doubtful", "PUP", "Sus"):
                        notes.append("His QB %s is %s" % (x["name"], x["status"]))
            return {
                "id": pid, "name": A.player_name(pid, pl) if pos != "DEF" else (pl.get("first_name", pid) + " " + pl.get("last_name", "")).strip(),
                "pos": pos, "team": team, "status": status,
                "opp": opp, "home": game["home"] if game else None, "day": A.day_label(game["date"]) if game else "",
                "date": game["date"] if game else None,
                "sleeper": round(sleeper_pts * factor, 2), "adj": round(adj * factor, 2),
                "raw_sleeper": round(sleeper_pts, 2),
                "mult": mult, "rank": row["rank"] if row else None, "of": row["of"] if row else None,
                "matchup": A.matchup_text(pos, row), "available": why == "",
                "why": why, "notes": notes,
                "gp": len(pts), "avg": round(sum(pts) / len(pts), 1) if pts else None,
                "last3": round(sum(pts[-3:]) / len(pts[-3:]), 1) if pts else None,
                "reserve": pid in reserve, "taxi": pid in taxi,
                "locked": locked, "game_state": gstate, "actual": actual,
            }

        pool = {pid: info(pid) for pid in all_pids}
        startable = {pid: p for pid, p in pool.items() if not p["reserve"] and not p["taxi"]}
        for p in startable.values():
            p["value_adj"] = p["adj"] if p["available"] else -1
            p["value_sleeper"] = p["sleeper"] if p["available"] else -1
        cur = list(mine.get("starters") or [])
        cur += [None] * (len(slots) - len(cur))
        # players whose game has started can't move: starters stay put, bench stays benched
        preset = [c if (c and c != "0" and c in pool and pool[c]["locked"]) else None for c in cur]
        frozen = set(pid for pid, p in startable.items() if p["locked"])
        rec = A.fill_lineup(slots, startable, "value_adj", preset, frozen)
        rec_sleeper = A.fill_lineup(slots, startable, "value_sleeper", preset, frozen)

        def P(pid):
            if not pid or pid == "0":
                return None
            return pool.get(pid) or info(pid)

        lineup = []
        for i, s in enumerate(slots):
            r_id = rec[i] if A.SLOT_ELIG.get(s) else (cur[i] if cur[i] != "0" else None)
            lineup.append({"slot": s, "label": A.SLOT_LABEL.get(s, s), "rec": P(r_id), "cur": P(cur[i]),
                           "sleeper": P(rec_sleeper[i])})
        rec_set = set(x for x in rec if x)
        cur_set = set(x for x in cur if x and x != "0")
        bench = sorted([p for pid, p in pool.items() if pid not in rec_set and not p["reserve"] and not p["taxi"]],
                       key=lambda p: (-p["adj"], p["name"]))
        stash = sorted([p for p in pool.values() if p["reserve"] or p["taxi"]], key=lambda p: p["name"])

        # ---- alerts -------------------------------------------------------------------
        alerts = []
        def pts(p, key):  # points that count: actual once the game has started, else projection
            return p["actual"] if p["locked"] and p["actual"] is not None else p[key]

        for i, s in enumerate(slots):
            c = P(cur[i])
            if c is not None and c["locked"]:
                continue  # game already started, nothing to do
            if c is None:
                alerts.append({"level": "bad", "text": "Empty %s slot in your Sleeper lineup." % A.SLOT_LABEL.get(s, s)})
            elif not c["available"]:
                alerts.append({"level": "bad", "text": "%s is starting at %s but is %s." % (c["name"], A.SLOT_LABEL.get(s, s), c["why"] if c["why"] != "BYE" else "on a bye")})
            elif c["status"] == "Doubtful":
                alerts.append({"level": "bad", "text": "%s is Doubtful and in your lineup." % c["name"]})
            elif c["status"] == "Questionable":
                alerts.append({"level": "warn", "text": "%s is Questionable (%s game). Check the inactives before kickoff." % (c["name"], c["day"] or "?")})
            elif c["raw_sleeper"] == 0 and c["pos"] != "DEF":
                alerts.append({"level": "warn", "text": "%s is starting with a 0.0 Sleeper projection." % c["name"]})
        ins = [P(x) for x in rec if x and x not in cur_set]
        outs = [P(x) for x in cur if x and x != "0" and x not in rec_set]
        if ins or outs:
            gain = sum(p["adj"] for p in ins) - sum(p["adj"] for p in outs if p["available"])
            alerts.append({"level": "change", "text": "Lineup change: start %s; sit %s (about %+.1f pts)." % (
                ", ".join("%s (%.1f)" % (p["name"], p["adj"]) for p in ins) or "-",
                ", ".join("%s (%s)" % (p["name"], ("%.1f" % p["adj"]) if p["available"] else p["why"]) for p in outs) or "-", gain)})
        a_only = [x for x in rec if x and x not in set(rec_sleeper)]
        s_only = [x for x in rec_sleeper if x and x not in rec_set]
        if a_only or s_only:
            alerts.append({"level": "call", "text": "Matchup call: Sleeper's projections alone would start %s; the matchup data prefers %s. Close one, your call." % (
                ", ".join("%s (%.1f, %s)" % (P(x)["name"], P(x)["sleeper"], P(x)["matchup"] or "no data") for x in s_only),
                ", ".join("%s (%.1f, %s)" % (P(x)["name"], P(x)["sleeper"], P(x)["matchup"] or "no data") for x in a_only))})
        for x in rec:
            p = P(x)
            if p and p["locked"]:
                continue
            if p and p["rank"] and p["rank"] <= 3 and p["pos"] != "DEF":
                alerts.append({"level": "info", "text": "%s faces %s (%s)." % (p["name"], p["opp"], p["matchup"])})
            if p and any(n.startswith("His QB") for n in p["notes"]):
                alerts.append({"level": "warn", "text": "%s: %s" % (p["name"], [n for n in p["notes"] if n.startswith("His QB")][0])})
        early = [P(x) for x in rec if x and not P(x)["locked"] and P(x)["day"] in ("Thu", "Fri", "Wed")]
        done = [P(x) for x in cur if x and x != "0" and P(x)["locked"]]
        if done:
            alerts.append({"level": "info", "text": "Already played (locked): " + ", ".join(
                "%s %.1f%s" % (p["name"], p["actual"] or 0, " live" if p["game_state"] == "live" else "") for p in done)})
        if early:
            alerts.append({"level": "info", "text": "Plays before Sunday (lock early): " + ", ".join("%s (%s)" % (p["name"], p["day"]) for p in early)})
        ir_slots = int((lg.get("settings") or {}).get("reserve_slots") or 0)
        if ir_slots and len(reserve) < ir_slots:
            can_ir = [p for p in bench if p["status"] in ("IR", "Out", "PUP", "Doubtful", "Sus")]
            if can_ir:
                alerts.append({"level": "info", "text": "Open IR spot (%d/%d used). Eligible: %s." % (len(reserve), ir_slots, ", ".join("%s (%s)" % (p["name"], p["status"]) for p in can_ir))})
        if added or dropped:
            alerts.append({"level": "info", "text": "Roster changes since last run: %s%s" % (
                ("added " + ", ".join(A.player_name(p, players.get(p)) for p in added)) if added else "",
                ("; dropped " + ", ".join(A.player_name(p, players.get(p)) for p in dropped)) if dropped else "")})

        # ---- fantasy opponent ---------------------------------------------------------
        opp_info = None
        mu = S.matchups(lid, week)
        mine_mu = next((m for m in mu if m.get("roster_id") == mine["roster_id"]), None)
        if mine_mu and mine_mu.get("matchup_id") is not None:
            o = next((m for m in mu if m.get("matchup_id") == mine_mu["matchup_id"] and m.get("roster_id") != mine["roster_id"]), None)
            if o:
                oro = roster_ids.get(o["roster_id"], {})
                ou = users.get(oro.get("owner_id"), {})
                o_proj = 0.0
                for pid in o.get("starters") or []:
                    if pid and pid != "0":
                        opl = players.get(pid) or {}
                        oteam = pid if pid.isalpha() else opl.get("team")
                        if A.game_state(sched.game(week, oteam), today) in ("live", "final"):
                            o_proj += A.score(live_stats.get(pid, {}), ss)
                        else:
                            o_proj += A.score((proj.get(pid) or {}).get("stats"), ss)
                ost = oro.get("settings") or {}
                opp_info = {
                    "team": (ou.get("metadata") or {}).get("team_name") or ou.get("display_name") or "Opponent",
                    "owner": ou.get("display_name", ""),
                    "proj": round(o_proj, 1),
                    "record": "%d-%d" % (ost.get("wins", 0), ost.get("losses", 0)),
                }
        st = mine.get("settings") or {}
        me_u = users.get(user_id, {})
        out_leagues.append({
            "id": lid, "name": lg["name"], "short": short, "format": A.league_format(lg),
            "team_name": (me_u.get("metadata") or {}).get("team_name") or me_u.get("display_name") or "",
            "record": "%d-%d%s" % (st.get("wins", 0), st.get("losses", 0), ("-%d" % st["ties"]) if st.get("ties") else ""),
            "pf": round(num(st.get("fpts")) + num(st.get("fpts_decimal")) / 100, 1),
            "lineup": lineup, "bench": bench, "stash": stash, "alerts": alerts, "opponent": opp_info,
            "proj_rec": round(sum(pts(P(x), "adj") for x in rec if x), 1),
            "proj_rec_sleeper": round(sum(pts(P(x), "sleeper") for x in rec if x), 1),
            "proj_cur": round(sum(pts(P(x), "sleeper") for x in cur if x and x != "0"), 1),
            "any_locked": any(P(x)["locked"] for x in cur if x and x != "0"),
            "scoring": {k: ss.get(k) for k in ("rec", "pass_td", "bonus_rec_te", "pass_int", "fum_lost")},
        })

    os.makedirs(DATA, exist_ok=True)
    with open(snapshot_path, "w") as f:
        json.dump(new_snap, f)

    # ---- ownership: remember whose rosters each player is on (one file per person) ----------
    owned_dir = os.path.join(DATA, "owned")
    os.makedirs(owned_dir, exist_ok=True)
    who = me.get("display_name") or uname
    with open(os.path.join(owned_dir, "%s.json" % tag), "w") as f:
        json.dump({"name": who, "updated": now.isoformat(timespec="minutes"), "players": owned}, f)
    rostered = {}  # pid -> ["EComte: Nyarsh, Ohio Fantasy", ...]
    for fn in sorted(os.listdir(owned_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(owned_dir, fn)) as f:
                o = json.load(f)
        except Exception:
            continue
        for pid, lgs in (o.get("players") or {}).items():
            rostered.setdefault(pid, []).append("%s: %s" % (o.get("name") or fn[:-5], ", ".join(lgs)))

    # ---- sheets -----------------------------------------------------------------------
    print("Writing sheets...")
    proj_half = {pid: A.num((r.get("stats") or {}).get("pts_half_ppr")) for pid, r in proj.items()}
    sheet_rows = {p: [] for p in A.ALL_POS}
    pids = set(logs) | set(rostered)
    for pid in pids:
        pl = players.get(pid) or meta.get(pid) or {}
        pos = A.player_pos(pl) or ("DEF" if pid.isalpha() else None)
        if pos not in A.ALL_POS:
            continue
        team = pid if pos == "DEF" else pl.get("team") or ""
        game = sched.game(week, team) if team else None
        opp = game["opp"] if game else None
        row = dvp.get(pos, {}).get(opp) if opp else None
        mult = row["mult"] if row else 1.0
        base = {
            "player": A.player_name(pid, pl), "pos": pos, "team": team,
            "rostered_by": "; ".join(rostered.get(pid, [])), "injury": injury_of(pid),
            "bye_week": sched.bye_week(team) if team else "",
        }
        base.update(A.summarize_player(logs.get(pid, []), pos))
        base.update({
            "next_opp": ("vs " if game and game["home"] else "@ ") + opp if opp else ("BYE" if team else "FA"),
            "next_game_day": A.day_label(game["date"]) if game else "",
            "opp_toughness_rank": row["rank"] if row else "",
            "opp_matchup": A.matchup_text(pos, row),
            "opp_multiplier": mult if row else "",
            "sleeper_proj_half": round(proj_half.get(pid, 0), 2),
            "matchup_adj_proj_half": round(proj_half.get(pid, 0) * (1 + W * (mult - 1)), 2),
            "player_id": pid,
        })
        if pos == "DEF":
            d = dvp.get("_def_detail", {}).get(team, {})
            g = d.get("games") or 0
            base.update({
                "pts_allow_pg": round(d.get("pts_allow", 0) / g, 1) if g else "",
                "yds_allow_pg": round(d.get("yds_allow", 0) / g, 1) if g else "",
                "sacks": d.get("sack", 0), "ints": d.get("int", 0), "fum_rec": d.get("fum_rec", 0),
            })
        if base["gp"] == 0 and not base["rostered_by"]:
            continue
        sheet_rows[pos].append(base)

    head = ["player", "pos", "team", "rostered_by", "injury", "bye_week", "next_opp", "next_game_day",
            "opp_toughness_rank", "opp_matchup", "opp_multiplier", "sleeper_proj_half", "matchup_adj_proj_half",
            "gp", "avg_half_ppr", "avg_ppr", "last3_avg_half", "best", "worst",
            "avg_vs_top10_def", "games_vs_top10_def", "avg_vs_other_def", "snap_pct"]
    statcols = {
        "QB": ["pass_att", "pass_cmp", "pass_yd", "pass_td", "int", "rush_att", "rush_yd", "rush_td", "fum_lost"],
        "RB": ["rush_att", "rush_yd", "rush_td", "targets", "tgt_pg", "rec", "rec_yd", "rec_td", "fum_lost"],
        "WR": ["targets", "tgt_pg", "rec", "rec_yd", "rec_td", "rush_att", "rush_yd", "rush_td", "fum_lost"],
        "TE": ["targets", "tgt_pg", "rec", "rec_yd", "rec_td", "fum_lost"],
        "K": ["fgm", "fga", "fg_long", "xpm", "xpa"],
        "DEF": ["pts_allow_pg", "yds_allow_pg", "sacks", "ints", "fum_rec"],
    }
    for pos, rows in sheet_rows.items():
        rows.sort(key=lambda r: (r["rostered_by"] == "", -A.num(r["avg_half_ppr"])))
        cols = [c for c in head if not (pos in ("K", "DEF") and c == "snap_pct")] + statcols[pos] + ["player_id"]
        write_csv(os.path.join(SHEETS, "%s.csv" % pos), rows, cols)

    dv_rows = []
    for t in sorted(sched.teams()):
        r = {"team": t, "bye_week": sched.bye_week(t)}
        for pos in A.OFF_POS:
            x = dvp.get(pos, {}).get(t)
            r["%s_allowed_pg" % pos] = round(x["allowed_pg"], 2) if x else ""
            r["%s_last4_pg" % pos] = round(x["allowed_pg_recent"], 2) if x else ""
            r["%s_rank" % pos] = x["rank"] if x else ""
            r["%s_mult" % pos] = x["mult"] if x else ""
        x = dvp.get("DEF", {}).get(t)
        r["offense_gives_DEF_pg"] = round(x["allowed_pg"], 2) if x else ""
        r["offense_vs_DEF_rank"] = x["rank"] if x else ""
        g = sched.game(week, t)
        r["week%d_opp" % week] = (("vs " if g["home"] else "@ ") + g["opp"]) if g else "BYE"
        dv_rows.append(r)
    write_csv(os.path.join(SHEETS, "DEF_vs_POS.csv"), dv_rows)

    gl = []
    for pid in owned:
        pl = players.get(pid) or meta.get(pid) or {}
        for e in logs.get(pid, []):
            s = e["stats"]
            gl.append({"player": A.player_name(pid, pl), "pos": A.player_pos(pl), "week": e["week"],
                       "team": e["team"], "opp": e["opp"], "opp_toughness_rank": e["opp_rank"] or "",
                       "pts_half_ppr": e["pts_half"], "pts_ppr": e["pts_ppr"],
                       "pass_yd": s.get("pass_yd", ""), "pass_td": s.get("pass_td", ""), "int": s.get("pass_int", ""),
                       "rush_att": s.get("rush_att", ""), "rush_yd": s.get("rush_yd", ""), "rush_td": s.get("rush_td", ""),
                       "targets": s.get("rec_tgt", ""), "rec": s.get("rec", ""), "rec_yd": s.get("rec_yd", ""),
                       "rec_td": s.get("rec_td", ""),
                       "snap_pct": round(100 * A.num(s.get("off_snp")) / A.num(s.get("tm_off_snp")), 1) if A.num(s.get("tm_off_snp")) else "",
                       "leagues": "; ".join(owned[pid])})
    gl.sort(key=lambda r: (r["pos"] or "", r["player"], r["week"]))
    write_csv(os.path.join(USER_SHEETS, "game_log.csv"), gl)

    lu = []
    for L in out_leagues:
        for s in L["lineup"]:
            r, c = s["rec"], s["cur"]
            lu.append({"league": L["short"], "slot": s["label"],
                       "recommended": r["name"] if r else "", "rec_pos": r["pos"] if r else "",
                       "rec_opp": r["opp"] if r else "", "rec_matchup": r["matchup"] if r else "",
                       "rec_adj_proj": r["adj"] if r else "", "rec_sleeper_proj": r["sleeper"] if r else "",
                       "current": c["name"] if c else "(empty)", "current_sleeper_proj": c["sleeper"] if c else "",
                       "rec_game": (r["game_state"] or "") if r else "",
                       "rec_actual": r["actual"] if (r and r["actual"] is not None) else "",
                       "change": "SWAP" if (r and c and r["id"] != c["id"]) or (r and not c) else ""})
    write_csv(os.path.join(USER_SHEETS, "lineups.csv"), lu)

    # tidy up sheets from the old layout (per-person copies of the shared sheets)
    stale = [os.path.join(USER_SHEETS, n + ".csv") for n in A.ALL_POS + ["DEF_vs_POS", "my_game_log"]]
    if not other:
        stale += [os.path.join(SHEETS, "lineups.csv"), os.path.join(SHEETS, "my_game_log.csv")]
    for path in stale:
        if os.path.exists(path):
            os.remove(path)

    # ---- report + page --------------------------------------------------------------------
    payload = {
        "generated": eastern_stamp(now),
        "owner": me.get("display_name") or uname, "is_me": not other,
        "sample": bool(os.environ.get("FF_FIXTURES")),
        "user_sheets": "sheets/%s/" % tag,
        "season": season, "week": week, "byes": byes_now, "matchup_weight": W,
        "stats_weeks": sorted(weekly), "leagues": out_leagues,
    }
    import render
    os.makedirs(REPORTS, exist_ok=True)
    rpath = os.path.join(REPORTS, "%s_week%02d.md" % (season, week))
    with open(rpath, "w") as f:
        f.write(render.report_md(payload, dvp))
    with open(os.path.join(DATA, "latest%s.json" % (("_" + tag) if other else "")), "w") as f:
        json.dump(payload, f, indent=1)
    print("Player photos for the phone page...")
    seen = {}
    for L in out_leagues:
        people = L["bench"] + L["stash"] + [s[k] for s in L["lineup"] for k in ("rec", "cur", "sleeper") if s[k]]
        for p in people:
            seen[p["id"]] = (p["id"], p["pos"], p["team"])
    photos = S.headshots(list(seen.values()))
    os.makedirs(LINEUPS, exist_ok=True)
    hpath = os.path.join(LINEUPS, "lineups-%s.html" % tag)
    moved = os.path.join(HERE, "lineups-%s.html" % tag)  # pages used to sit in the main folder
    if os.path.exists(moved):
        os.remove(moved)
    old_page = os.path.join(HERE, "lineups.html")  # pre-rename name for my own page
    if not other and os.path.exists(old_page):
        os.remove(old_page)
    with open(hpath, "w") as f:
        f.write(render.page_html(payload))
    with open(os.path.join(DATA, "artifact%s.html" % (("_" + tag) if other else "")), "w") as f:
        f.write(render.artifact_html(payload, photos))

    print("")
    for L in out_leagues:
        bad = sum(1 for a in L["alerts"] if a["level"] in ("bad", "change"))
        print("  %-34s %s  proj %.1f%s" % (L["short"][:34], "!! %d to fix" % bad if bad else "ok      ", L["proj_rec"],
                                          ("  vs %s (%.1f)" % (L["opponent"]["team"], L["opponent"]["proj"])) if L["opponent"] else ""))
    print("\nSheets:  %s (shared) and %s" % (SHEETS, USER_SHEETS))
    print("Report:  %s" % rpath)
    print("Lineups: %s" % hpath)
    if args.open:
        subprocess.call(["open", hpath])


num = A.num

if __name__ == "__main__":
    main()
