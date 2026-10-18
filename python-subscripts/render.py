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


def page_html(d, live=False):
    """live=True: the hosted copy, which loads ../benchpress.js and gets a Refresh button."""
    with open(os.path.join(ROOT, "config", "lineups_template.html")) as f:
        tpl = f.read()
    blob = json.dumps(d).replace("</", "<\\/")
    if live:
        tpl = tpl.replace("<!--__LIVE__-->", '<script src="../benchpress.js"></script>')
    return tpl.replace("/*__DATA__*/null", blob)


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
