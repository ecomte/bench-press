"""Small Sleeper API client with on-disk caching (standard library only).

Documented API:   https://api.sleeper.app/v1/...  (users, leagues, rosters, matchups, players)
Undocumented API: https://api.sleeper.com/...     (weekly stats, projections, schedule)
The undocumented endpoints are what the Sleeper app itself uses. They are not
officially supported, so if Sleeper changes them this file is the one to fix.
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

V1 = "https://api.sleeper.app/v1"
APP = "https://api.sleeper.com"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the fantasy-football folder
CACHE = os.path.join(ROOT, "data", "cache")

# Set FF_FIXTURES=/path/to/dir to read canned responses instead of the network (testing).
FIXTURES = os.environ.get("FF_FIXTURES")


def _fixture_name(url):
    return url.split("://", 1)[1].replace("/", "_").replace("?", "_").replace("&", "_").replace("[]", "") + ".json"


def _fetch(url, tries=3):
    if FIXTURES:
        path = os.path.join(FIXTURES, _fixture_name(url))
        if not os.path.exists(path):
            raise RuntimeError("missing fixture " + path)
        with open(path) as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": "ecomte-fantasy-tools/1.0"})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(5 * (i + 1))
                continue
            if e.code == 404:
                return None
            time.sleep(1 + i)
        except urllib.error.URLError as e:
            last = e
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                sys.exit(
                    "SSL certificate error talking to Sleeper. Run this script with /usr/bin/python3, "
                    "or run 'Install Certificates.command' from your Python folder in Applications."
                )
            time.sleep(1 + i)
    raise RuntimeError("Could not reach %s (%s)" % (url, last))


def get(url, cache_file=None, max_age_hours=None):
    """GET JSON. With cache_file, reuse the saved copy if it's younger than max_age_hours
    (None = keep forever). Falls back to a stale cached copy if the network fails."""
    path = os.path.join(CACHE, cache_file) if cache_file else None
    if path and os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if max_age_hours is None or age_h < max_age_hours:
            with open(path) as f:
                return json.load(f)
    try:
        data = _fetch(url)
    except Exception:
        if path and os.path.exists(path):
            print("  ! network failed for %s, using cached copy" % url)
            with open(path) as f:
                return json.load(f)
        raise
    if path and data is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    return data


def headshots(items, max_age_days=30):
    """items: [(id, pos, team)]. Downloads each player's Sleeper headshot (or team logo for a DEF)
    once into data/cache/headshots/ and returns {id: data-URI} for embedding in the phone page."""
    import base64
    from concurrent.futures import ThreadPoolExecutor
    folder = os.path.join(CACHE, "headshots")
    os.makedirs(folder, exist_ok=True)

    def one(item):
        pid, pos, team = item
        if pos == "DEF":
            url, ext, mime = "https://sleepercdn.com/images/team_logos/nfl/%s.png" % str(team).lower(), "png", "image/png"
        else:
            url, ext, mime = "https://sleepercdn.com/content/nfl/players/thumb/%s.jpg" % pid, "jpg", "image/jpeg"
        path = os.path.join(folder, "%s.%s" % (pid, ext))
        fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_days * 86400
        if not fresh and not FIXTURES:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ecomte-fantasy-tools/1.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if data:
                    with open(path, "wb") as f:
                        f.write(data)
            except Exception:
                pass  # no photo for this player; the page shows initials
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                return pid, "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))
        return pid, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        return {pid: uri for pid, uri in ex.map(one, items) if uri}


# ---- documented endpoints -------------------------------------------------

def user(name_or_id):
    return get("%s/user/%s" % (V1, name_or_id))


def nfl_state():
    return get("%s/state/nfl" % V1)


def leagues(user_id, season):
    return get("%s/user/%s/leagues/nfl/%s" % (V1, user_id, season)) or []


def rosters(league_id):
    return get("%s/league/%s/rosters" % (V1, league_id)) or []


def league_users(league_id):
    return get("%s/league/%s/users" % (V1, league_id)) or []


def matchups(league_id, week):
    return get("%s/league/%s/matchups/%s" % (V1, league_id, week)) or []


def players():
    """~5MB map of every player. Sleeper asks that this be pulled at most once a day."""
    return get("%s/players/nfl" % V1, "players.json", max_age_hours=20)


# ---- undocumented app endpoints ---------------------------------------------

def _pos_query():
    return "&".join("position[]=%s" % p for p in POSITIONS)


def week_stats(season, week, final=True, max_age_hours=6):
    """Actual stats for every player-game in a week. Finished weeks are cached for good;
    the most recent week is refreshed every few hours (stat corrections land Tue/Wed), and the
    week in progress is refreshed on almost every run (max_age_hours=0.1) for live/final points."""
    url = "%s/stats/nfl/%s/%s?season_type=regular&%s" % (APP, season, week, _pos_query())
    return get(url, "stats_%s_w%02d.json" % (season, week), max_age_hours=None if final else max_age_hours) or []


def week_projections(season, week):
    url = "%s/projections/nfl/%s/%s?season_type=regular&%s" % (APP, season, week, _pos_query())
    return get(url, "proj_%s_w%02d.json" % (season, week), max_age_hours=1) or []


def schedule(season):
    return get("%s/schedule/nfl/regular/%s" % (APP, season), "schedule_%s.json" % season, max_age_hours=1) or []
