# Bench Press

[![Release](https://img.shields.io/badge/release-v1.2.0-green)](https://github.com/ecomte/bench-press/releases)

**Open Bench Press: [ecomte.github.io/bench-press](https://ecomte.github.io/bench-press/)**. Search your Sleeper username to see your lineups.

> Let's eat a W.

Fantasy football lineup suggestions for Sleeper leagues. Bench Press pulls your rosters from the Sleeper API, re-scores Sleeper's projections with each league's rules, adjusts them for the opposing defense, and recommends a starting lineup for every team you own. It flags byes, injuries, empty slots and close calls, then renders a tabbed, Sleeper-style lineup page.

This repository is the GitHub version of Bench Press. It began as a set of scripts run by hand on a Mac, with the pages shared by hand afterward. Here the same code is built and published automatically to a free GitHub Pages site, so anyone on the list can open their link and see a current lineup without the owner running anything.

## Releases

| Version | What it added |
|---|---|
| 0.1.0 (beta) | Scheduled GitHub Actions builds that deploy one lineup page per person to GitHub Pages (BP-1). |
| 1.0.0 | Live Refresh button, live scoreboard and win-probability bar, the landing-page username search and `live/?u=<name>` pages for anyone (BP-3). |
| 1.0.1 | Refreshed lineups survive a page reload; version and copyright in the footer (BP-5). |
| 1.1.0 | IDP support, phone alerts for new users, and a changelog link in the footer (BP-7). |
| 1.2.0 | Sleeper auto-subs (BP-9), case-insensitive usernames for live links and alerts (BP-9), and smash-spot and tough-defense matchup weighting (BP-10). |

Release notes for each version are on the [Releases page](https://github.com/ecomte/bench-press/releases). The original design and trade-offs are in [docs/static-site-plan.md](docs/static-site-plan.md).

## How it's set up

```
Sleeper API ──► GitHub Actions (scheduled) ──► benchpress.py for each user ──► GitHub Pages
                                                                               └─ /<username>/
```

- **Hosting:** GitHub Pages, deployed from GitHub Actions. Each person gets `https://ecomte.github.io/bench-press/<username>/`, and each page keeps one tab per league.
- **Refresh button:** each hosted page has a **Refresh** button that rebuilds the lineup on the phone from live Sleeper data (`web/benchpress.js`). The scheduled build publishes the slow-changing data it needs (player list, defense-vs-position ranks, game logs) to `data/` on the site, so a tap only fetches this week's rosters, projections and live points. If a browser can't reach Sleeper's app endpoints, it uses the build's copies in `data/`.
- **Landing page:** a Sleeper username search. A name with a built page links straight to it; any other name gets a link to `live/?u=<username>`, which builds that person's page on the spot.
- **New-user alerts:** the first time a device opens a live page from the search for a name with no saved page, the landing page quietly sends a phone notification through the free [ntfy](https://ntfy.sh) app (topic `ntfy_topic` in `config/config.json`; leave it empty to turn this off). The visitor sees no difference. Usernames ignore letter case (Natibuck and natibuck share one live link and one alert), and before pinging, the page checks ntfy's recent messages (kept about 12 hours) so looking a new user up on another device doesn't send a second alert. Anyone who knows the topic can post to it, so change it if it ever gets spammed.
- **Schedule (US Eastern):** hourly from 7 AM to midnight with one overnight build at 4 AM, and every 15 minutes during games: Sunday from noon to midnight, plus Monday and Thursday nights. A build can also be started by hand from the Actions tab.
- **Secrets:** none. Sleeper's API is public and read-only, and everything in this repo is already public on Sleeper.
- **Users:** the people built on each run are listed in `batch_users` in `config/config.json`. Adding a friend is a one-line change.
- **Parity check:** every build replays its Sleeper responses through the JavaScript and compares lineups, totals and alerts with the Python. It's non-blocking, so a mismatch shows as a warning on the run without stopping the pages from updating.
- **Workflow:** `.github/workflows/build.yml`. Builds run on any branch so a feature branch can be checked from the Actions tab; only `main` deploys.
- **Branches:** `main` is what's deployed. Work happens on `feature/BP-<n>-...` branches and merges through `develop`.

## Run it locally

Python 3 with the standard library only. No installs needed.

```
python3 benchpress.py --open            # my leagues, next week with games left
python3 benchpress.py -w 8              # look ahead to week 8
python3 benchpress.py -u SomeFriend     # someone else's Sleeper username
python3 batchbenchpress.py              # everyone in batch_users
python3 batchbenchpress.py --no-open    # same, without opening browser tabs
python3 batchbenchpress.py --no-open --site site   # build the hosted site into site/ (what Actions runs)
```

The first run takes about 20 seconds, because it downloads Sleeper's 5 MB player list, which is then cached for a day. Output goes to folders that git ignores:

| Path | What it is |
|---|---|
| `lineups/lineups-<username>.html` | The tabbed lineup page, which opens offline. Toggle between **Recommended**, **Sleeper proj only** and **Current in Sleeper**. |
| `reports/<season>_weekNN.md` | The same information as text, including alerts, lineup tables, injury context, and the toughest and easiest defenses by position. |
| `sheets/*.csv` | Position sheets (QB, RB, WR, TE, K, DEF, and IDP for every DL, LB and DB) and `DEF_vs_POS.csv`, shared by everyone who was run. IDP points in the sheets use a typical IDP scoring (`IDP_SCORING` in `analysis.py`); lineups always use each league's own. |
| `sheets/<username>/` | That person's `lineups.csv` and `game_log.csv`. |
| `data/` | API cache, roster snapshots and headshots. It's safe to delete and rebuilds itself. |

`ANALYZE-PROMPT.md` is a prompt for getting a second opinion from Claude on the weekly report.

## How the recommendation works

1. **Projection.** Sleeper's weekly projection, re-scored with each league's scoring (half or full PPR, 6-point passing TDs, TE premium).
2. **Matchup adjustment.** Each defense's points allowed to the position, compared with the league average and shrunk toward average for small samples. The projection moves 50% of the way toward that, set by `matchup_weight` in `config/config.json`, because Sleeper already accounts for matchups somewhat.
   - **W Feast (smash spots).** Projections tend to undersell a player facing one of the very easiest defenses for his position, so QBs, RBs, WRs and TEs facing the 3 easiest (`easy_matchup_ranks`) get an extra boost on top: up to 30% (`easy_matchup_boost`) against the easiest, two thirds of that against the 2nd-easiest and one third against the 3rd, scaled down early in the season when the defense has played only a few games. A lower-projected player in a smash spot can now win a slot over a higher-projected one, and a smash-spot player left on the bench within 3 points (`smash_alert_gap`) of a starter he could replace gets a **Your call** alert. On the page these are labeled **W Feast** and the player note shows in green.
   - **Players who handle tough defenses.** For each skill player, his points against the toughest third of defenses are compared with his points against everyone else, using this season plus last season (`history_seasons`). Most players drop off against tough defenses; one who drops off less than is typical for his position, or not at all, gets part of a tough-matchup penalty waived (all of it with enough games and no drop-off). His player note (in darker orange on the page) and the tough-matchup alert say so. Last season's weekly stats are downloaded once and cached for good.
3. **Availability.** Players on BYE or listed Out, IR, PUP or suspended are excluded. Doubtful players count at 25%, and Questionable players count in full but get flagged.
4. **Filling slots.** Fixed positions are filled first, then FLEX, then Superflex, each with the best available player. IDP slots (DL, LB, DB and IDP flex) are filled the same way; a defender Sleeper lists at two spots (DL and LB) can fill either. A defender with no Sleeper projection uses his season average in that league's scoring, and his matchup is how many IDP points the offense he faces gives up to his position. IR and taxi slots are left alone.
5. **Locked games.** Once a player's game kicks off, he stays where he is, and the page shows his real points (LIVE or FINAL).
6. **Auto-subs.** If you've picked a Sleeper auto-sub for a starter (a bench player from an earlier game whose points count if the starter doesn't play), the page shows it under the starter (⇄ Auto-sub) and on the bench player. Totals count it: an Out starter's slot is worth his sub's points, a Doubtful one 25% of his own plus 75% of the sub's, and once games start the sub's real points replace a starter who didn't play. A Questionable starter still counts in full, with the sub as his backup. Where Sleeper's API keeps auto-subs isn't documented: `python3 tools/autosub_probe.py` shows what your leagues return, and `AUTO_SUB_KEYS` in `analysis.py` (same list in `web/benchpress.js`) is the place to adjust.

Alerts on the page are **Fix** (empty slot or an unavailable starter), **Swap** (the recommended changes), **Watch** (Questionable starters, with an earlier-game bench player to use as an auto-sub when there is one, or a starter whose QB is out), **Your call** (Sleeper's projections and the matchup data disagree, or a benched smash-spot player came close) and **Note** (tough matchups, early games, open IR spots, roster changes, auto-subs you've set). An auto-sub that is out, didn't play, or plays after its starter is a **Fix**; a Questionable starter with a working auto-sub moves from Watch to a Note.

## Configuration

`config/config.json`:

| Key | Purpose |
|---|---|
| `username`, `user_id` | The owner's Sleeper account, which gets league nicknames and tab order. |
| `matchup_weight` | 0 means pure Sleeper projections, and 1 applies the full defense effect. Default is 0.5. |
| `easy_matchup_boost`, `easy_matchup_ranks` | Smash-spot boost against the easiest defenses for a position (default 0.3, the 3 easiest). 0 turns it off. |
| `smash_alert_gap` | A benched smash-spot player this many points or fewer behind a starter gets a Your call alert. Default is 3. |
| `history_seasons` | Past seasons used to find players who handle tough defenses. Default is 1; 0 uses this season only. |
| `league_nicknames`, `league_order` | Tab names and order for the owner's leagues. |
| `ignore_leagues` | League IDs to skip. |
| `ntfy_topic` | ntfy topic that gets a notification when someone new opens a live page. Empty turns it off. |
| `batch_users` | Sleeper usernames built by `batchbenchpress.py` and the scheduled job. |

## Repository layout

| Path | What it is |
|---|---|
| `benchpress.py` | Entry point for one user. |
| `batchbenchpress.py` | Runs `benchpress.py` for every name in `batch_users`. |
| `python-subscripts/sleeper.py` | Sleeper API client with on-disk caching. |
| `python-subscripts/analysis.py` | Scoring, defense-vs-position ranks and the lineup optimizer. |
| `python-subscripts/render.py` | The weekly report and the lineup page. |
| `python-subscripts/sitedata.py` | Writes the shared data files the Refresh button reads. |
| `web/benchpress.js` | The Refresh button's lineup builder, a JavaScript port of the per-week logic. |
| `tools/autosub_probe.py` | Prints what Sleeper returns for your leagues' auto-subs, to check Bench Press can read them. |
| `tools/parity.js` | Replays the build's Sleeper responses through `web/benchpress.js` and checks it picks the same lineups as the Python. |
| `config/lineups_template.html` | The look of the lineup page. |
| `.github/workflows/` | `build.yml` (scheduled build and Pages deploy) and `cascade-merge.yml` (merges `main` back into `develop`). |
| `docs/` | Design notes, starting with the static-site plan. |

## Data sources

All data comes from Sleeper, so names, IDs, injury tags and scoring match the app.

- **Documented API** (`api.sleeper.app/v1`): users, leagues, rosters, matchups and players. No key is needed.
- **Undocumented app endpoints** (`api.sleeper.com`): weekly stats, projections and the schedule. These are unofficial, so if they change, `python-subscripts/sleeper.py` is the only file to fix. Last season's weekly stats (for the tough-defense check) are downloaded once and kept.
- **Auto-subs:** Sleeper doesn't document where it stores them. Bench Press checks the likely field names, which haven't been confirmed against live data yet; `python3 tools/autosub_probe.py` shows what your leagues return.

The API is read-only, so lineup changes are made in the Sleeper app.

## Roadmap

- An Ohio Fantasy rebuild mode, as a per-league setting that favors young players and long-term value.
- Confirm Sleeper's auto-sub field with `tools/autosub_probe.py` and point `AUTO_SUB_KEYS` at it.
- Count opponents' auto-subs in the matchup score.

## License

Copyright (c) 2026. All rights reserved. See [COPYRIGHT.md](COPYRIGHT.md).
