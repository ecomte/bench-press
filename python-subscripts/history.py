"""Past seasons' weekly stats, saved in the repo by tools/stats_backfill.py.

data/history/stats/<season>.json.gz holds one finished regular season:
  {"season": "2024", "weeks": {"1": [row, ...], ...}, "players": {player_id: {...}}}
Each row is one player-game from Sleeper's weekly stats (only players who were active), without the
bulky "player" object; the season's "players" map holds those once. load() puts them back, so
rows come out shaped like sleeper.week_stats() and work with analysis.py as they are.
"""

import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "data", "history", "stats")  # tracked by git, unlike the rest of data/

# Player fields kept per season (the rest of Sleeper's player object is news/injury noise)
PLAYER_KEYS = ("first_name", "last_name", "position", "fantasy_positions", "team", "years_exp")
# Weekly rank fields are 999 for most rows and easy to recompute, so they aren't stored
SKIP_STATS = ("pos_rank_half_ppr", "pos_rank_ppr", "pos_rank_std")


def path(season):
    return os.path.join(FOLDER, "%s.json.gz" % season)


def seasons():
    """Seasons saved in the repo, oldest first."""
    if not os.path.isdir(FOLDER):
        return []
    return sorted(f.split(".")[0] for f in os.listdir(FOLDER) if f.endswith(".json.gz"))


def compact(season, weekly):
    """weekly: {week: sleeper.week_stats() rows} -> the saved form."""
    weeks, players = {}, {}
    for w, rows in sorted(weekly.items()):
        out = []
        for r in rows:
            s = r.get("stats") or {}
            if not (s.get("gp") or s.get("gms_active") or s.get("pts_std")):
                continue  # inactive that week; these rows carry no points
            pid = r.get("player_id")
            pl = r.get("player") or {}
            players.setdefault(pid, {k: pl.get(k) for k in PLAYER_KEYS})
            out.append({
                "player_id": pid, "team": r.get("team"), "opponent": r.get("opponent"),
                "game_id": r.get("game_id"), "date": r.get("date"),
                "stats": {k: v for k, v in s.items() if k not in SKIP_STATS},
            })
        if out:
            weeks[str(w)] = out
    return {"season": str(season), "weeks": weeks, "players": players}


def save(season, weekly):
    data = compact(season, weekly)
    os.makedirs(FOLDER, exist_ok=True)
    # mtime=0 keeps the file byte-identical when the data hasn't changed (no noise in git)
    with open(path(season), "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return data


def load(season):
    """{week (int): rows shaped like sleeper.week_stats()}, or {} if the season isn't saved."""
    if not os.path.exists(path(season)):
        return {}
    with gzip.open(path(season), "rt", encoding="utf-8") as f:
        data = json.load(f)
    players = data.get("players") or {}
    weekly = {}
    for w, rows in data["weeks"].items():
        for r in rows:
            r["player"] = players.get(r["player_id"]) or {}
            r["week"], r["season"] = int(w), data["season"]
        weekly[int(w)] = rows
    return weekly
