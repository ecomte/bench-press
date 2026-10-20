"""Turns raw Sleeper data into stat sheets, defense-vs-position ranks, and lineup calls."""

import datetime as dt
from collections import defaultdict

OFF_POS = ["QB", "RB", "WR", "TE", "K"]
IDP_POS = ["DL", "LB", "DB"]  # individual defensive players, by Sleeper's fantasy position
ALL_POS = OFF_POS + ["DEF"] + IDP_POS

# Who can play where. Slots not listed here (IR, taxi) are left as you set them.
SLOT_ELIG = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "DL": {"DL"}, "LB": {"LB"}, "DB": {"DB"},
    "IDP_FLEX": {"DL", "LB", "DB"},
}
SLOT_LABEL = {"SUPER_FLEX": "SF", "WRRB_FLEX": "W/R", "REC_FLEX": "W/T", "FLEX": "FLEX", "IDP_FLEX": "IDP"}

# A typical IDP scoring, for the shared IDP sheet and the IDP defense-vs-position ranks only
# (Sleeper's own pts_* totals leave defensive stats out). Lineups always use each league's
# own IDP settings.
IDP_SCORING = {
    "idp_tkl_solo": 1.0, "idp_tkl_ast": 0.5, "idp_tkl_loss": 1.0, "idp_sack": 4.0, "idp_qb_hit": 1.0,
    "idp_int": 3.0, "idp_ff": 3.0, "idp_fum_rec": 3.0, "idp_pass_def": 1.0, "idp_def_td": 6.0,
    "idp_safe": 2.0, "idp_blk_kick": 2.0,
}

OUT_STATUSES = {"Out", "IR", "PUP", "Sus", "NA", "COV", "DNR"}
DEF_POSITIONS = {"DE", "DT", "DL", "LB", "ILB", "OLB", "MLB", "CB", "S", "SS", "FS", "DB", "NT"}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def score(stats, scoring):
    """Fantasy points for a stat line under a league's scoring_settings
    (Sleeper's stat keys and scoring keys are the same names)."""
    total = 0.0
    for k, v in (stats or {}).items():
        w = scoring.get(k)
        if w and isinstance(v, (int, float)):
            total += v * w
    return round(total, 2)


def played(rec):
    s = rec.get("stats") or {}
    return (num(s.get("gp")) > 0 or num(s.get("off_snp")) > 0 or num(s.get("def_snp")) > 0
            or rec.get("player_id", "").isalpha())


def player_pos(pl):
    if not pl:
        return None
    pos = pl.get("position")
    if pos in ALL_POS:
        return pos
    for p in pl.get("fantasy_positions") or []:
        if p in ALL_POS:
            return p
    return pos


def player_fpos(pl, pos):
    """Positions a player can fill. Sleeper lets some defenders play two IDP spots
    (an edge rusher listed DL and LB); everyone else plays only his own position."""
    if pos not in IDP_POS:
        return [pos]
    return [pos] + [p for p in (pl or {}).get("fantasy_positions") or [] if p in IDP_POS and p != pos]


def week_pts(stats, pos):
    """Points for one game in the shared sheets: half PPR, or default IDP scoring for defenders."""
    s = stats or {}
    if pos in IDP_POS:
        return score(s, IDP_SCORING)
    return num(s.get("pts_half_ppr"))


def player_name(pid, pl):
    if not pl:
        return pid
    return ("%s %s" % (pl.get("first_name", ""), pl.get("last_name", ""))).strip() or pid


# ---------------------------------------------------------------------------
# Schedule helpers

class Schedule:
    def __init__(self, games):
        self.games = games or []
        self.by_week = defaultdict(dict)  # week -> team -> info
        for g in self.games:
            w = g.get("week")
            d = g.get("date")
            for team, opp, home in ((g["home"], g["away"], True), (g["away"], g["home"], False)):
                self.by_week[w][team] = {"opp": opp, "home": home, "date": d, "status": g.get("status")}

    def weeks(self):
        return sorted(self.by_week)

    def week_complete(self, w):
        games = [g for g in self.games if g.get("week") == w]
        return bool(games) and all(g.get("status") == "complete" for g in games)

    def target_week(self):
        """First week that still has a game left to play."""
        for w in self.weeks():
            if not self.week_complete(w):
                return w
        return self.weeks()[-1] if self.weeks() else 1

    def game(self, week, team):
        return self.by_week.get(week, {}).get(team)

    def teams(self):
        t = set()
        for w in self.by_week.values():
            t.update(w)
        return t

    def byes(self, week):
        return sorted(self.teams() - set(self.by_week.get(week, {})))

    def bye_week(self, team):
        for w in self.weeks():
            if team not in self.by_week[w]:
                return w
        return None


def game_state(game, today=None):
    """'pre' (not started), 'live' (in progress) or 'final' for a schedule entry. A game dated
    before today counts as final even if the cached schedule still says pre_game."""
    if not game:
        return None
    status = (game.get("status") or "").lower()
    today = today or dt.date.today()
    try:
        played_before_today = dt.date.fromisoformat(game.get("date") or "") < today
    except ValueError:
        played_before_today = False
    if status == "complete" or (status in ("pre_game", "") and played_before_today):
        return "final"
    if status not in ("pre_game", ""):
        return "live"
    return "pre"


def game_left(game, gstate, now_et):
    """Rough share of a game still to play: 1 before kickoff, 0 once final. Sleeper's schedule
    has no game clock, so a live game's progress is guessed from the usual kickoff slots
    (US Eastern): Monday/Thursday 8:15 PM; other days 1:00, 4:15 or 8:20 PM, whichever
    fits; about 3h15m per game."""
    if gstate == "final":
        return 0.0
    if gstate != "live":
        return 1.0
    try:
        gd = dt.date.fromisoformat(game.get("date") or "")
    except ValueError:
        return 0.5
    mins = (now_et.date() - gd).days * 1440 + now_et.hour * 60 + now_et.minute  # since midnight of game day
    if gd.weekday() in (0, 3):
        kick = 20 * 60 + 15
    elif mins - 13 * 60 < 210:
        kick = 13 * 60
    elif mins < 20 * 60 + 20:
        kick = 16 * 60 + 15
    else:
        kick = 20 * 60 + 20
    return min(1.0, max(0.05, 1 - (mins - kick) / 195.0))


def day_label(date_str):
    try:
        d = dt.date.fromisoformat(date_str)
        return d.strftime("%a")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Defense vs position

def defense_vs_position(weekly, last_n=4, shrink_games=4):
    """weekly: {week: [stat records]}. Returns {pos: {def_team: row}} where row has
    points allowed per game to that position, a toughness rank (1 = allows the fewest)
    and a matchup multiplier (1.10 = gives up 10% more than average)."""
    weeks = sorted(weekly)
    recent = set(weeks[-last_n:])
    allowed = {p: defaultdict(lambda: defaultdict(float)) for p in OFF_POS + IDP_POS}  # pos -> def -> week -> pts
    def_pts_vs_offense = defaultdict(dict)  # offense team -> week -> DEF pts scored against them
    def_detail = defaultdict(lambda: defaultdict(float))  # def team -> stat -> total
    def_games = defaultdict(int)
    for w in weeks:
        for rec in weekly[w]:
            pos = player_pos(rec.get("player"))
            opp = rec.get("opponent")
            s = rec.get("stats") or {}
            if not opp:
                continue
            if pos in OFF_POS and played(rec):
                allowed[pos][opp][w] += num(s.get("pts_half_ppr"))
            elif pos in IDP_POS and played(rec):
                # keyed by the OFFENSE the defender faced: how much it gives up to DLs, LBs, DBs
                allowed[pos][opp][w] += week_pts(s, pos)
            elif pos == "DEF":
                def_pts_vs_offense[opp][w] = num(s.get("pts_half_ppr", s.get("pts_std")))
                team = rec.get("team") or rec.get("player_id")
                def_games[team] += 1
                for k in ("pts_allow", "yds_allow", "sack", "int", "fum_rec", "def_td", "td", "pts_half_ppr"):
                    def_detail[team][k] += num(s.get(k))

    out = {}
    for pos in OFF_POS + IDP_POS:
        # every team that played gets a row, even if it allowed 0
        teams = set(allowed[pos])
        rows = {}
        for t in teams:
            g = len(allowed[pos][t])
            tot = sum(allowed[pos][t].values())
            rec_vals = [v for w, v in allowed[pos][t].items() if w in recent]
            rows[t] = {
                "games": g,
                "allowed_pg": tot / g if g else 0.0,
                "allowed_pg_recent": sum(rec_vals) / len(rec_vals) if rec_vals else 0.0,
            }
        if not rows:
            out[pos] = {}
            continue
        avg = sum(r["allowed_pg"] for r in rows.values()) / len(rows)
        order = sorted(rows, key=lambda t: rows[t]["allowed_pg"])
        for i, t in enumerate(order):
            r = rows[t]
            raw = r["allowed_pg"] / avg if avg else 1.0
            weight = r["games"] / float(r["games"] + shrink_games)  # small samples pulled toward average
            r["rank"] = i + 1  # 1 = toughest
            r["of"] = len(order)
            r["mult"] = round(1 + weight * (raw - 1), 3)
            r["vs_avg_pct"] = round((raw - 1) * 100, 1)
        out[pos] = rows

    # Team defenses: how many DEF points do opposing offenses give up?
    rows = {}
    for t, wk in def_pts_vs_offense.items():
        g = len(wk)
        rows[t] = {"games": g, "allowed_pg": sum(wk.values()) / g if g else 0}
    if rows:
        avg = sum(r["allowed_pg"] for r in rows.values()) / len(rows)
        order = sorted(rows, key=lambda t: rows[t]["allowed_pg"])
        for i, t in enumerate(order):
            r = rows[t]
            raw = r["allowed_pg"] / avg if avg else 1.0
            weight = r["games"] / float(r["games"] + shrink_games)
            r["rank"] = i + 1
            r["of"] = len(order)
            r["mult"] = round(1 + weight * (raw - 1), 3)
            r["vs_avg_pct"] = round((raw - 1) * 100, 1)
    out["DEF"] = rows  # keyed by OFFENSE team: rank 1 = offense that's toughest for defenses
    out["_def_detail"] = {t: dict(v, games=def_games[t]) for t, v in def_detail.items()}
    return out


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


def matchup_text(pos, row):
    if not row:
        return ""
    r, of = row["rank"], row["of"]
    if pos == "DEF" or pos in IDP_POS:
        if r <= of / 2:
            return "%s-toughest offense for %ss" % (ordinal(r), pos)
        return "%s-friendliest offense for %ss" % (ordinal(of - r + 1), pos)
    if r <= of / 2:
        return "%s-toughest vs %s" % (ordinal(r), pos)
    return "%s-easiest vs %s" % (ordinal(of - r + 1), pos)


# ---------------------------------------------------------------------------
# Matchup extras: the very easiest defenses, and players who hold up against tough ones

SKILL_POS = ("QB", "RB", "WR", "TE")


def easy_bonus(row, boost=0.30, ranks=3, shrink_games=4):
    """Extra projection share for a smash spot. The matchup multiplier only moves a projection part
    of the way, and players facing a bottom defense tend to beat even that, so the `ranks` easiest
    defenses vs a position add up to `boost` more (the 1st-easiest the most, then less for each
    rank up), scaled down when that defense's numbers rest on only a few games."""
    if not row or not boost or ranks < 1:
        return 0.0
    easiest = row["of"] - row["rank"] + 1
    if easiest > ranks:
        return 0.0
    sample = row["games"] / float(row["games"] + shrink_games)
    return round(boost * (ranks - easiest + 1) / ranks * sample, 3)


def tough_profile(log_sets, meta, min_games=2, shrink_games=4, weights=None):
    """{pid: row} for skill players who score about as well against the toughest third of
    defenses as against the rest. log_sets: build_player_logs() logs for one or more seasons
    (each season's toughness ranks come from that season). weights: how much each season's games
    count (default 1 each), so older seasons can count less. row["hold"] (0 to 1) is how much of a
    tough-matchup penalty to waive: 1 = he's done at least as well against tough defenses as
    against everyone else, 0 = he drops off as much as a typical player at his position (or
    more), and small samples are pulled toward 0."""
    weights = weights or [1.0] * len(log_sets)
    split = {}  # pid -> (pos, [(pts, weight) vs tough], [(pts, weight) vs the rest])
    for pid in set().union(*log_sets):
        pos = player_pos(meta.get(pid))
        if pos not in SKILL_POS:
            continue
        tough, other = [], []
        for logs, wt in zip(log_sets, weights):
            for e in logs.get(pid, []):
                if e["opp_rank"]:
                    (tough if e["opp_rank"] <= e["opp_of"] / 3.0 else other).append((e["pts_half"], wt))
        if tough and other:
            split[pid] = (pos, tough, other)

    def avg(games):
        w = sum(wt for _, wt in games)
        return sum(x * wt for x, wt in games) / w if w else 0.0

    # how much a typical fantasy-relevant player drops off against tough defenses, by position
    base = {}
    for pos in SKILL_POS:
        t = [g for p, tl, ol in split.values() if p == pos and avg(tl + ol) >= 8 for g in tl]
        o = [g for p, tl, ol in split.values() if p == pos and avg(tl + ol) >= 8 for g in ol]
        typical = avg(t) / avg(o) if t and o and avg(o) else 0.8
        base[pos] = min(max(typical, 0.5), 0.95)

    out = {}
    for pid, (pos, tough, other) in split.items():
        if len(tough) < min_games or len(other) < min_games:
            continue
        at, ao = avg(tough), avg(other)
        if ao < 5:  # a few points a game is too noisy to read anything into
            continue
        lift = min(max((at / ao - base[pos]) / (1 - base[pos]), 0.0), 1.0)
        n = sum(wt for _, wt in tough)  # older games count as part of a game toward the sample
        hold = round(lift * n / float(n + shrink_games), 3)
        if hold > 0:
            out[pid] = {"hold": hold, "avg_tough": round(at, 1), "avg_other": round(ao, 1),
                        "g_tough": len(tough), "g_other": len(other)}
    return out


def matchup_mult(row, hold=0.0):
    """The defense multiplier, with a tough-matchup penalty partly waived for players who hold up."""
    mult = row["mult"] if row else 1.0
    if mult < 1 and hold:
        mult = round(1 - (1 - mult) * (1 - hold), 3)
    return mult


# ---------------------------------------------------------------------------
# Team context: injured defensive starters and offensive starters

def team_injuries(players):
    """{team: {'def': [..], 'off': [..]}} for depth-chart starters who are hurt."""
    out = defaultdict(lambda: {"def": [], "off": []})
    for pid, p in players.items():
        team = p.get("team")
        st = p.get("injury_status")
        if not team or not st or st == "Healthy":
            continue
        order = p.get("depth_chart_order")
        pos = p.get("position")
        dpos = p.get("depth_chart_position") or pos
        entry = {"id": pid, "name": player_name(pid, p), "pos": dpos or pos, "status": st}
        if pos in DEF_POSITIONS and order == 1:
            out[team]["def"].append(entry)
        elif pos in ("QB", "RB", "WR", "TE") and order in (1, 2) and (pos != "QB" or order == 1):
            out[team]["off"].append(entry)
    return out


# ---------------------------------------------------------------------------
# Player season sheets

SHEET_STATS = [
    ("pass_att", "pass_att"), ("pass_cmp", "pass_cmp"), ("pass_yd", "pass_yd"), ("pass_td", "pass_td"),
    ("pass_int", "int"), ("rush_att", "rush_att"), ("rush_yd", "rush_yd"), ("rush_td", "rush_td"),
    ("rec_tgt", "targets"), ("rec", "rec"), ("rec_yd", "rec_yd"), ("rec_td", "rec_td"),
    ("fum_lost", "fum_lost"),
]
K_STATS = [("fgm", "fgm"), ("fga", "fga"), ("fgm_lng", "fg_long"), ("xpm", "xpm"), ("xpa", "xpa")]
IDP_STATS = [
    ("idp_tkl", "tackles"), ("idp_tkl_solo", "solo"), ("idp_tkl_ast", "assists"), ("idp_tkl_loss", "tfl"),
    ("idp_sack", "sacks"), ("idp_qb_hit", "qb_hits"), ("idp_int", "ints"), ("idp_pass_def", "pass_def"),
    ("idp_ff", "forced_fum"), ("idp_fum_rec", "fum_rec"), ("idp_def_td", "def_td"),
]


def build_player_logs(weekly, dvp):
    """{pid: [ {week, team, opp, pts_half, pts_ppr, stats, opp_rank, opp_of} ]}"""
    logs = defaultdict(list)
    meta = {}
    for w in sorted(weekly):
        for rec in weekly[w]:
            pid = rec.get("player_id")
            pos = player_pos(rec.get("player"))
            if pos not in ALL_POS or not played(rec):
                continue
            s = rec.get("stats") or {}
            opp = rec.get("opponent")
            if pos == "DEF":
                row = dvp.get("DEF", {}).get(opp)
            else:
                row = dvp.get(pos, {}).get(opp)
            logs[pid].append({
                "week": w, "team": rec.get("team"), "opp": opp,
                "pts_half": week_pts(s, pos), "pts_ppr": week_pts(s, pos) if pos in IDP_POS else num(s.get("pts_ppr")),
                "stats": s, "opp_rank": row["rank"] if row else None, "opp_of": row["of"] if row else None,
            })
            meta[pid] = rec.get("player") or {}
    return logs, meta


def summarize_player(log, pos):
    g = len(log)
    tot = defaultdict(float)
    snaps = []
    side = "def" if pos in IDP_POS else "off"
    for e in log:
        for k, v in e["stats"].items():
            if isinstance(v, (int, float)):
                tot[k] += v
        s = e["stats"]
        if num(s.get("tm_%s_snp" % side)) > 0:
            snaps.append(num(s.get("%s_snp" % side)) / num(s.get("tm_%s_snp" % side)))
    half = [e["pts_half"] for e in log]
    last3 = half[-3:]
    tough = [e["pts_half"] for e in log if e["opp_rank"] and e["opp_rank"] <= 10]
    easy = [e["pts_half"] for e in log if e["opp_rank"] and e["opp_rank"] > 10]
    out = {
        "gp": g,
        "avg_half_ppr": round(sum(half) / g, 2) if g else 0,
        "avg_ppr": round(sum(e["pts_ppr"] for e in log) / g, 2) if g else 0,
        "last3_avg_half": round(sum(last3) / len(last3), 2) if last3 else 0,
        "best": round(max(half), 1) if half else 0,
        "worst": round(min(half), 1) if half else 0,
        "avg_vs_top10_def": round(sum(tough) / len(tough), 2) if tough else "",
        "games_vs_top10_def": len(tough),
        "avg_vs_other_def": round(sum(easy) / len(easy), 2) if easy else "",
        "snap_pct": round(100 * sum(snaps) / len(snaps), 1) if snaps else "",
    }
    stats = K_STATS if pos == "K" else IDP_STATS if pos in IDP_POS else SHEET_STATS
    for key, col in stats:
        if key == "fgm_lng":
            out[col] = int(max([num(e["stats"].get(key)) for e in log] or [0]))
        else:
            out[col] = round(tot.get(key, 0), 1)
    if pos in IDP_POS and not out["tackles"]:  # older stat lines only split solo and assisted
        out["tackles"] = round(tot.get("idp_tkl_solo", 0) + tot.get("idp_tkl_ast", 0), 1)
    if pos in ("WR", "TE", "RB") and g:
        out["tgt_pg"] = round(tot.get("rec_tgt", 0) / g, 1)
    return out


# ---------------------------------------------------------------------------
# Auto-subs: in Sleeper you can pick a bench player from an earlier game to cover a starter
# (a Questionable Monday night player, say). If the starter doesn't play, the auto-sub's
# points count for him.

# Where Sleeper's API keeps a team's auto-subs. Not documented: tools/autosub_probe.py
# prints what a real roster and matchup carry, and this is the one place to adjust.
AUTO_SUB_KEYS = ("auto_subs", "autosubs", "auto_sub", "subs")
_STARTER_KEYS = ("starter", "starter_id", "player_id", "original", "from")
_SUB_KEYS = ("sub", "sub_id", "auto_sub", "substitute", "to")


def auto_subs(*objs):
    """{starter id: auto-sub id} from the first roster or matchup object (or its metadata /
    settings) that has any. Takes a {starter: sub} map or a list of {starter, sub} pairs."""
    for o in objs:
        for where in (o or {}, (o or {}).get("metadata") or {}, (o or {}).get("settings") or {}):
            if not isinstance(where, dict):
                continue
            for k in AUTO_SUB_KEYS:
                v = where.get(k)
                out = {}
                if isinstance(v, dict):
                    out = {str(a): str(b) for a, b in v.items() if a and b and str(b) != "0"}
                elif isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict):
                            a = next((e[x] for x in _STARTER_KEYS if e.get(x)), None)
                            b = next((e[x] for x in _SUB_KEYS if e.get(x)), None)
                        elif isinstance(e, (list, tuple)) and len(e) == 2:
                            a, b = e
                        else:
                            continue
                        if a and b and str(b) != "0":
                            out[str(a)] = str(b)
                if out:
                    return out
    return {}


def sub_state(s):
    """Where a starter's auto-sub stands: 'in' (he isn't playing, so the sub's points count),
    'doubtful' (probably sits), 'backup' (expected to play) or 'unused' (his game started
    and he played)."""
    if s["locked"]:
        return "in" if (not s["available"] or (s["game_state"] == "final" and not s["played"])) else "unused"
    if not s["available"]:
        return "in"
    return "doubtful" if s["status"] == "Doubtful" else "backup"


def sub_can_score(b):
    """Can auto-sub b still put up points: healthy before his game, or on the field once it starts?"""
    return (b["played"] or b["game_state"] == "live") if b["locked"] else b["available"]


def sub_options(slot, s, bench):
    """Bench players who could be an auto-sub for starter s in slot: eligible there, healthy,
    and playing on an earlier day so their game finishes first. Best first."""
    elig = SLOT_ELIG.get(slot) or set()
    return [b for b in bench if b["available"] and not b["locked"] and b["date"] and s["date"]
            and b["date"] < s["date"] and elig.intersection(b.get("fpos") or [b["pos"]])]


# ---------------------------------------------------------------------------
# Lineup optimizer

def fill_lineup(slots, pool, key, preset=None, exclude=()):
    """slots: list of slot names (non-bench, in league order). pool: {pid: info}.
    preset: per-slot player ids that can't move (their game has started); exclude: players
    who can't be moved into the lineup (also locked). Fills the remaining slots, most
    restrictive first, with the best available eligible player."""
    order = sorted(range(len(slots)), key=lambda i: (len(SLOT_ELIG.get(slots[i], ())) or 99, i))
    preset = preset or [None] * len(slots)
    used = set(x for x in preset if x) | set(exclude)
    result = list(preset)
    for i in order:
        elig = SLOT_ELIG.get(slots[i])
        if not elig or result[i]:
            continue
        best = None
        for pid, p in pool.items():
            if pid in used or not elig.intersection(p.get("fpos") or [p["pos"]]) or not p["available"]:
                continue
            if best is None or p[key] > pool[best][key]:
                best = pid
        if best is not None:
            used.add(best)
            result[i] = best
    return result


def league_format(league):
    ss = league.get("scoring_settings") or {}
    rp = league.get("roster_positions") or []
    ppr = num(ss.get("rec"))
    fmt = {1.0: "PPR", 0.5: "Half PPR", 0.0: "Standard"}.get(ppr, "%.2g PPR" % ppr)
    bits = [{0: "Redraft", 1: "Keeper", 2: "Dynasty"}.get((league.get("settings") or {}).get("type"), "League"),
            "%d teams" % league.get("total_rosters", 0), fmt]
    if "SUPER_FLEX" in rp:
        bits.append("Superflex")
    if num(ss.get("bonus_rec_te")):
        bits.append("TE +%.2g" % num(ss.get("bonus_rec_te")))
    if num(ss.get("pass_td")) != 4:
        bits.append("%g pt pass TD" % num(ss.get("pass_td")))
    return " · ".join(bits)
