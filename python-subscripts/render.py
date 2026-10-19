"""Builds the weekly markdown report and the tabbed lineups-<user>.html page."""

import json
import os

import analysis as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the fantasy-football folder


def _p(p):
    if not p:
        return "(empty)"
    tag = (" **%s**" % p["status"]) if p["status"] else ""
    return "%s (%s %s)%s" % (p["name"], p["pos"], p["team"] or "FA", tag)


def report_md(d, dvp):
    L = []
    L.append("# Fantasy lineups: %s week %d" % (d["season"], d["week"]))
    L.append("")
    L.append("Generated %s. Stats from weeks %s. Byes this week: %s." % (
        d["generated"], ", ".join(map(str, d["stats_weeks"])) or "none", ", ".join(d["byes"]) or "none"))
    L.append("")
    L.append("**How to read this:** *Sleeper* is Sleeper's projection scored with that league's rules. "
             "*Adj* nudges it by the opponent's points allowed to that position (matchup weight %.2f; "
             "1.0 would apply the full defense effect). Toughness rank 1 = defense that allows the fewest points." % d["matchup_weight"])
    L.append("")
    for lg in d["leagues"]:
        L.append("## %s" % lg["name"])
        L.append("")
        L.append("%s. Record %s, %s pts for." % (lg["format"], lg["record"], lg["pf"]))
        if lg["opponent"]:
            o = lg["opponent"]
            L.append("This week vs **%s** (%s, %s): their current lineup projects %.1f; "
                     "recommended lineup projects %.1f adj / %.1f Sleeper; your current lineup %.1f." % (
                         o["team"], o["owner"], o["record"], o["proj"], lg["proj_rec"], lg["proj_rec_sleeper"], lg["proj_cur"]))
        L.append("")
        if lg["alerts"]:
            for a in lg["alerts"]:
                icon = {"bad": "🔴", "change": "🔁", "warn": "🟡", "call": "⚖️", "info": "ℹ️"}.get(a["level"], "-")
                L.append("- %s %s" % (icon, a["text"]))
            L.append("")
        L.append("| Slot | Recommended | Opp | Matchup | Adj | Sleeper | Season avg | Currently in Sleeper |")
        L.append("|---|---|---|---|---|---|---|---|")
        for s in lg["lineup"]:
            r, c = s["rec"], s["cur"]
            same = r and c and r["id"] == c["id"]
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                s["label"], _p(r), (("vs " if r["home"] else "@ ") + r["opp"] + " " + r["day"]) if r and r["opp"] else "-",
                r["matchup"] if r else "",
                (("%s %.1f" % ("FINAL" if r["game_state"] == "final" else "LIVE", r["actual"] or 0)) if r["locked"] else ("%.1f" % r["adj"])) if r else "",
                ("%.1f" % r["sleeper"]) if r else "",
                r["avg"] if r and r["avg"] is not None else "-", "same" if same else "**" + _p(c) + "**"))
        subs = [s for s in lg["lineup"] if s.get("autosub")]
        if subs:
            L.append("")
            L.append("Auto-subs: " + "; ".join("%s covers %s (%s)" % (
                s["autosub"]["player"]["name"], s["cur"]["name"],
                {"in": "his points count", "doubtful": "starter Doubtful", "unused": "not needed",
                 "backup": "backup"}[s["autosub"]["state"]]) for s in subs))
        L.append("")
        L.append("Bench: " + "; ".join("%s %.1f%s" % (p["name"], p["adj"], (" [%s]" % p["why"]) if p["why"] else "") for p in lg["bench"]))
        if lg["stash"]:
            L.append("")
            L.append("IR / taxi: " + "; ".join(p["name"] for p in lg["stash"]))
        notes = []
        for s in lg["lineup"]:
            if s["rec"] and s["rec"]["notes"]:
                notes.append("- %s: %s" % (s["rec"]["name"], " / ".join(s["rec"]["notes"])))
        if notes:
            L.append("")
            L.append("Injury context:")
            L.extend(notes)
        L.append("")

    L.append("## Defense vs position (half PPR points allowed per game)")
    L.append("")
    for pos in A.OFF_POS:
        rows = dvp.get(pos) or {}
        if not rows:
            continue
        order = sorted(rows, key=lambda t: rows[t]["rank"])
        L.append("- **%s** toughest: %s. Easiest: %s." % (
            pos, ", ".join("%s %.1f" % (t, rows[t]["allowed_pg"]) for t in order[:5]),
            ", ".join("%s %.1f" % (t, rows[t]["allowed_pg"]) for t in order[::-1][:5])))
    L.append("")
    mine = d.get("user_sheets") or "sheets/"
    L.append("Full tables: position sheets and DEF_vs_POS.csv in `sheets/` (shared by everyone), "
             "this person's lineups.csv and game_log.csv in `%s`. Ask Claude to read this report plus those "
             "for a deeper pass." % mine)
    L.append("")
    return "\n".join(L)


def version_html():
    """Version and copyright line under the footer. The version is read from the release badge
    at the top of README.md, which is bumped by hand on each release branch."""
    import re
    try:
        with open(os.path.join(ROOT, "README.md")) as f:
            m = re.search(r"img\.shields\.io/badge/release-v([0-9][^-)]*)", f.read())
    except OSError:
        m = None
    # tags are the bare number (1.0.1), so the release page is releases/tag/<version>
    ver = ('Bench Press Version: %s. Changelog: <a href="https://github.com/ecomte/bench-press/releases/tag/%s" '
           'target="_blank" rel="noopener">GitHub</a><br>' % (m.group(1), m.group(1))) if m else ""
    return ver + "Copyright &copy; 2026 E Comte"


def page_html(d, live=False):
    """live=True: the hosted copy, which loads ../benchpress.js and gets a Refresh button."""
    with open(os.path.join(ROOT, "config", "lineups_template.html")) as f:
        tpl = f.read()
    blob = json.dumps(d).replace("</", "<\\/")
    if live:
        tpl = tpl.replace("<!--__LIVE__-->", '<script src="../benchpress.js"></script>')
        # hosted pages live at <site>/<user>/ and <site>/live/, so ../ is the landing page
        tpl = tpl.replace("<h1>Bench <span>Press</span></h1>", '<h1><a href="../" title="Back to search">Bench <span>Press</span></a></h1>')
    tpl = tpl.replace("<!--__VERSION__-->", version_html())
    return tpl.replace("/*__DATA__*/null", blob)


def landing_html(users, ntfy_topic=None):
    """The hosted site's front page: same look as the lineup pages, with a Sleeper username
    search. A name with a built page links to it; any other name gets a live/?u= link.
    ntfy_topic: when set, opening a live page from here sends the owner a phone notification."""
    import html as H
    import re
    with open(os.path.join(ROOT, "config", "lineups_template.html")) as f:
        tpl = f.read()
    head = re.search(r"<head>(.*?)</head>", tpl, re.S).group(1)
    tip = re.search(r'<section class="tip">.*?</section>', tpl, re.S).group(0)  # same Venmo block as the lineup pages
    people = json.dumps([{"tag": u.lstrip("@").lower(), "name": u.lstrip("@")} for u in users]).replace("</", "<\\/")
    return """<!doctype html>
<html lang="en">
<head>%s
<style>
.pitch{color:var(--ink);margin:0 0 10px;font-size:15px;max-width:620px}
.find{display:flex;gap:8px;flex-wrap:wrap}
.find input{flex:1 1 200px;min-width:0;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:10px 16px;font:500 15px var(--body)}
.find input:focus{outline:2px solid var(--accent);outline-offset:1px}
.btn,.find button{display:inline-block;background:var(--accent);color:var(--accent-ink);border:0;border-radius:999px;padding:10px 20px;font:700 15px var(--body);cursor:pointer;text-decoration:none}
.btn:hover,.find button:hover{filter:brightness(1.08)}
.result{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.result p{margin:0 0 6px}
.result .who{display:flex;gap:14px;align-items:center;margin-bottom:12px}
.result .av{width:52px;height:52px;border-radius:50%%;flex:none;background:var(--row2);border:2px solid var(--accent);object-fit:cover;display:grid;place-items:center;font:800 24px var(--display);color:var(--accent);text-transform:uppercase}
.result .name{font:800 28px/1 var(--display);text-transform:uppercase;letter-spacing:.01em}
.result .name span{color:var(--accent)}
.result .count{font:500 12px var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.result .leagues{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px}
.result .msg{color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="eyebrow">Sleeper lineup helper</div>
    <h1><a href="./" title="Bench Press home">Bench <span>Press</span></a></h1>
    <p class="tag">Let's eat a W.</p>
    <p class="pitch">In a pile of Sleeper leagues? Tired of spending hours fixing every lineup? Bench Press checks each of your teams and flags the swaps that matter, based on recent performance, injuries and how tough each opposing defense is.</p>
    <p class="sub">Search your Sleeper username to open your lineups.</p>
  </header>
  <form class="find" id="find" role="search">
    <input id="q" name="u" placeholder="Sleeper username" aria-label="Sleeper username" required autocapitalize="off" autocorrect="off" spellcheck="false" autocomplete="username">
    <button type="submit">Search</button>
  </form>
  <div class="result" id="result" hidden aria-live="polite"></div>
  %s
  <footer>Read-only: Sleeper's API can't change lineups, so make swaps in the app and refresh Bench Press to view updated lineups.</footer>
  <div class="ver">%s</div>
</div>
<script>
const PEOPLE = %s;
const NTFY = %s;  // ntfy_topic in config/config.json; "" turns the new-user notification off
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const getJSON = async (url) => { const r = await fetch(url); return r.ok ? r.json() : null; };
let STATIC;  // season and ignored leagues, from the site's own data
async function season() {
  if (STATIC === undefined) STATIC = await getJSON("data/static.json").catch(() => null);
  if (STATIC && STATIC.season) return String(STATIC.season);
  const st = await getJSON("https://api.sleeper.app/v1/state/nfl");
  return String(st.league_season || st.season);
}
function card(user, leagues, href, label) {
  const name = (user && (user.display_name || user.username)) || label;
  const av = user && user.avatar
    ? '<img class="av" alt="" src="https://sleepercdn.com/avatars/thumbs/' + encodeURIComponent(user.avatar) + '">'
    : '<div class="av" aria-hidden="true">' + esc(name.slice(0, 1)) + '</div>';
  let count = "", chips = "";
  if (leagues) {
    count = leagues.length + " current Sleeper league" + (leagues.length === 1 ? "" : "s");
    chips = '<div class="leagues">' + leagues.map(l => '<span class="chip">' + esc(l.name) + '</span>').join("") + '</div>';
  }
  return '<div class="who">' + av + '<div><div class="name">Found <span>' + esc(name) + '</span></div>'
    + (count ? '<div class="count">' + esc(count) + '</div>' : '') + '</div></div>' + chips
    + '<a class="btn" href="' + href + '">' + "Open " + esc(name) + ' &rarr;</a>';
}
document.getElementById("find").onsubmit = async (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim().replace(/^@/, "");
  if (!q) return;
  const box = document.getElementById("result");
  box.hidden = false;
  const hit = PEOPLE.find(p => p.tag === q.toLowerCase());
  box.innerHTML = '<p class="msg">Checking Sleeper for ' + esc(q) + '...</p>';
  // Look the account up first, so a name that isn't on Sleeper never gets a page.
  let user, leagues;
  try {
    user = await getJSON("https://api.sleeper.app/v1/user/" + encodeURIComponent(q));
    if (user && user.user_id) {
      const yr = await season();  // also loads STATIC
      const ignore = new Set(((STATIC || {}).ignore_leagues || []).map(String));
      const all = await getJSON("https://api.sleeper.app/v1/user/" + user.user_id + "/leagues/nfl/" + yr);
      if (Array.isArray(all)) leagues = all.filter(l => !ignore.has(String(l.league_id)));
    }
  } catch (err) {
    user = undefined;  // couldn't reach Sleeper; the pages still work, and the live page checks again
  }
  if (user === null || (user && !user.user_id)) {
    box.innerHTML = '<p>No Sleeper account named ' + esc(q) + '. Check the spelling; it&rsquo;s your Sleeper username, not your display name.</p>';
    return;
  }
  if (hit) { box.innerHTML = card(user, leagues, encodeURIComponent(hit.tag) + "/", hit.name); return; }
  box.innerHTML = card(user, leagues, "live/?u=" + encodeURIComponent(q), q)
    + '<p class="msg" style="margin-top:10px">No saved page yet, so this one builds live from Sleeper.</p>';
  box.querySelector(".btn").addEventListener("click", () => notifyOwner(q, leagues));
};
// The first time this device opens a live page for a name with no saved page, tell the owner's
// phone through the free ntfy app. It's fire-and-forget, so the visitor sees no difference.
function notifyOwner(name, leagues) {
  if (!NTFY) return;
  const key = "benchpress.notified." + name.toLowerCase();
  try { if (localStorage.getItem(key)) return; localStorage.setItem(key, "1"); } catch (e) {}
  const n = leagues ? leagues.length : null;
  const msg = "New Bench Press user: " + name + (n === null ? "" : " (" + n + " league" + (n === 1 ? "" : "s") + ")");
  const url = "https://ntfy.sh/" + encodeURIComponent(NTFY) + "?title=" + encodeURIComponent("Bench Press") + "&tags=football";
  try { navigator.sendBeacon(url, msg); } catch (e) {}
}
</script>
</body>
</html>
""" % (head, tip, version_html(), people, json.dumps(ntfy_topic or ""))


def live_page_html():
    """The hosted live/ page: no build data, just the Refresh logic. It loads whoever is named in ?u=."""
    return page_html({"placeholder": True, "leagues": [], "username": None, "matchup_weight": 0.5}, live=True)


def artifact_html(d, photos=None):
    """Same page, shaped for publishing as a claude.ai artifact (Claude publishes this file
    so the lineups can be viewed on a phone). The artifact host adds its own <html>/<head>,
    blocks outside images, and needs a title + gutter meta at the top."""
    import re
    html = page_html(d).replace("/*__NOIMG__*/false", "true")
    # headshots are embedded as data: URIs, since the artifact host can't load sleepercdn.com
    html = html.replace("/*__PHOTOS__*/{}", json.dumps(photos or {}))
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    head = re.sub(r'<meta charset[^>]*>\s*|<meta name="viewport"[^>]*>\s*', "", head)
    title = re.search(r"<title>.*?</title>", head).group(0)
    head = head.replace(title, "")
    title = "<title>Bench Press \u00b7 %s</title>" % (d.get("owner") or "")
    return title + '\n<meta name="claude:viewport-fit-sides" content="cover">\n' + head.strip() + "\n" + body.strip() + "\n"
