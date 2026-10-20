"""Shared data files for the hosted site's live Refresh button (web/benchpress.js).

The scheduled build already does the slow work (the 5 MB player list, every finished
week's stats, defense-vs-position ranks). This writes the results into <site>/data/ as
small JSON files, so a phone only has to fetch this week's rosters, projections and
live points from Sleeper when someone taps Refresh.
"""

import json
import os

import analysis as A

# Stat keys most Sleeper leagues score. Each run adds the keys its own leagues score,
# so leagues with unusual settings still get the stats they need.
BASE_SCORING_KEYS = [
    "pass_yd", "pass_td", "pass_int", "pass_2pt", "pass_int_td", "pass_sack",
    "rush_yd", "rush_td", "rush_2pt", "rec", "rec_yd", "rec_td", "rec_2pt", "bonus_rec_te",
    "fum", "fum_lost", "fum_rec_td",
    "fgm", "fgmiss", "fgm_0_19", "fgm_20_29", "fgm_30_39", "fgm_40_49", "fgm_50p", "fgm_yds",
    "xpm", "xpmiss",
    "def_td", "def_st_td", "st_td", "sack", "int", "fum_rec", "safe", "blk_kick", "def_4_and_stop",
    "pts_allow_0", "pts_allow_1_6", "pts_allow_7_13", "pts_allow_14_20", "pts_allow_21_27",
    "pts_allow_28_34", "pts_allow_35p",
    "idp_tkl", "idp_tkl_solo", "idp_tkl_ast", "idp_tkl_loss", "idp_sack", "idp_qb_hit", "idp_int",
    "idp_pass_def", "idp_ff", "idp_fum_rec", "idp_def_td", "idp_safe", "idp_blk_kick",
    "pts_half_ppr",
]


def _slim(stats, keys):
    return {k: v for k, v in (stats or {}).items() if k in keys and isinstance(v, (int, float)) and v}


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def write(site, cfg, season, week, matchup_weight, players, schedule, proj_list, live_list,
          stats_weeks, dvp, logs, injuries, scoring_keys, tough=None):
    out = os.path.join(os.path.abspath(site), "data")
    static_path = os.path.join(out, "static.json")

    keys = set(BASE_SCORING_KEYS) | set(scoring_keys)
    if os.path.exists(static_path):  # keep the keys earlier runs in this batch added
        try:
            with open(static_path) as f:
                keys |= set(json.load(f).get("scoring_keys") or [])
        except Exception:
            pass

    _dump(static_path, {
        "season": season, "week": week, "matchup_weight": matchup_weight, "stats_weeks": stats_weeks,
        "owner": {"username": cfg.get("username"), "user_id": cfg.get("user_id")},
        "league_nicknames": cfg.get("league_nicknames") or {},
        "league_order": cfg.get("league_order") or [],
        "ignore_leagues": cfg.get("ignore_leagues") or [],
        "scoring_keys": sorted(keys),
        "dvp": {pos: {t: dict({"rank": r["rank"], "of": r["of"], "mult": r["mult"]}, **({"easy": r["easy"]} if r.get("easy") else {}))
                      for t, r in rows.items()}
                for pos, rows in dvp.items() if not pos.startswith("_")},
        "smash_gap": float(cfg.get("smash_alert_gap", 3.0)),
        "return_min": float(cfg.get("return_watch_min", 5.0)),
        "tough": tough or {},  # players who hold up against tough defenses (analysis.tough_profile)
        "logs": {pid: [_slim(e["stats"], keys) for e in entries] for pid, entries in logs.items()},
        "injuries": {t: v for t, v in injuries.items()},
    })

    fields = ("first_name", "last_name", "position", "fantasy_positions", "team", "injury_status")
    slim = {}
    for pid, p in players.items():
        if A.player_pos(p) in A.ALL_POS and (p.get("active") or p.get("team")):
            slim[pid] = {k: p[k] for k in fields if p.get(k) not in (None, "", [])}
    _dump(os.path.join(out, "players.json"), slim)

    # Copies of this week's Sleeper app data, used if a browser can't call api.sleeper.com directly.
    _dump(os.path.join(out, "schedule.json"), schedule)

    def rows(lst):
        return [{"player_id": r["player_id"], "stats": _slim(r.get("stats"), keys),
                 "player": {"injury_status": (r.get("player") or {}).get("injury_status")}}
                for r in lst or [] if r.get("player_id")]
    _dump(os.path.join(out, "projections_w%02d.json" % week), rows(proj_list))
    _dump(os.path.join(out, "live_w%02d.json" % week), rows(live_list))
