# Bench Press

[![Release](https://img.shields.io/badge/release-v1.4.1-green)](https://github.com/ecomte/bench-press/releases)

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
| 1.3.0 | Smash spots renamed W Feast with a green note, and tough-defense notes in darker orange (BP-12). |
| 1.4.0 | Week buttons, green/red final scores and bye-only gray rows (BP-15), a 5-season tough-defense check and a notice that Sleeper doesn't share auto-subs (BP-14), and generated output and stats history moved under data/ (BP-16). |
| 1.4.1 | Patch for favicon addition (BP-18). |

Release notes for each version are on the [Releases page](https://github.com/ecomte/bench-press/releases). The original design and trade-offs are in [docs/static-site-plan.md](docs/static-site-plan.md).

## How it's set up

```
Sleeper API ──► GitHub Actions (scheduled) ──► benchpress.py for each user ──► GitHub Pages
                                                                               └─ /<username>/
```

- **Hosting:** GitHub Pages, deployed from GitHub Actions. Each person gets `https://ecomte.github.io/bench-press/<username>/`, and each page keeps one tab per league.
- **Refresh button:** each hosted page has a **Refresh** button that rebuilds the lineup on the phone from live Sleeper data (`web/benchpress.js`). The scheduled build publishes the slow-changing data it needs (player list, defense-vs-position ranks, game logs) to `data/` on the site, so a tap only fetches this week's rosters, projections and live points. If a browser can't reach Sleeper's app endpoints, it uses the build's copies in `data/`.
- **Week buttons:** under Refresh, buttons switch the page between weeks 1–18. They show the picked week with two on each side, and ‹ › slide to earlier or later weeks; the current week has an orange outline. Refresh stays on the picked week, while reloading the page goes back to the current week (only the current week is saved for reloads). A past week shows the roster and lineup you actually had that week with final points (once a week is over, the winner's score is green and the loser's red), and keeps only its notes, since nothing can change. A future week shows Sleeper's early projections and that week's opponent, with today's injuries. The build only copies the current week's projections, so if a browser can't reach Sleeper directly, other weeks show 0 projected points and the page says so. Locally, `python3 benchpress.py -w N` does the same for one week. Only players with no game in the week on screen (bye or no team) are grayed out; Out, IR and Doubtful players keep normal rows with their red tag.
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
python3 test-website.py                 # build the site into data/test-website/ and serve it at http://localhost:8000
```

To check the hosted site before pushing, run `python3 test-website.py`. It runs the same build as Actions into `data/test-website/` (git ignores it), then serves it at http://localhost:8000 until you press Ctrl+C. Extra arguments go to `batchbenchpress.py`, so `python3 test-website.py -w 8` builds week 8.

The first run takes about 20 seconds, because it downloads Sleeper's 5 MB player list, which is then cached for a day. Output goes under `data/`, which git ignores (except `data/history/`):

| Path | What it is |
|---|---|
| `data/lineups/lineups-<username>.html` | The tabbed lineup page, which opens offline. Toggle between **Recommended**, **Sleeper proj only** and **Current in Sleeper**. |
| `data/reports/<season>_weekNN.md` | The same information as text, including alerts, lineup tables, injury context, and the toughest and easiest defenses by position. |
| `data/sheets/*.csv` | Position sheets (QB, RB, WR, TE, K, DEF, and IDP for every DL, LB and DB) and `DEF_vs_POS.csv`, shared by everyone who was run. IDP points in the sheets use a typical IDP scoring (`IDP_SCORING` in `analysis.py`); lineups always use each league's own. |
| `data/sheets/<username>/` | That person's `lineups.csv` and `game_log.csv`. |
| `data/cache/`, `data/*.json` | API cache and roster snapshots. Safe to delete; they rebuild themselves. |

`docs/ANALYZE-PROMPT.md` is a prompt for getting a second opinion from Claude on the weekly report.

## How the recommendation works

1. **Projection.** Sleeper's weekly projection, re-scored with each league's scoring (half or full PPR, 6-point passing TDs, TE premium).
2. **Matchup adjustment.** Each defense's points allowed to the position, compared with the league average and shrunk toward average for small samples. The projection moves 50% of the way toward that, set by `matchup_weight` in `config/config.json`, because Sleeper already accounts for matchups somewhat.
   - **W Feast (smash spots).** Projections tend to undersell a player facing one of the very easiest defenses for his position, so QBs, RBs, WRs and TEs facing the 3 easiest (`easy_matchup_ranks`) get an extra boost on top: up to 30% (`easy_matchup_boost`) against the easiest, two thirds of that against the 2nd-easiest and one third against the 3rd, scaled down early in the season when the defense has played only a few games. A lower-projected player in a smash spot can now win a slot over a higher-projected one, and a smash-spot player left on the bench within 3 points (`smash_alert_gap`) of a starter he could replace gets a **Your call** alert. On the page these are labeled **W Feast** and the player note shows in green.
   - **Players who handle tough defenses.** For each skill player, his points against the toughest third of defenses are compared with his points against everyone else, using this season plus the last five (`history_seasons`), with each older season counting less (`history_decay`). Most players drop off against tough defenses; one who drops off less than is typical for his position, or not at all, gets part of a tough-matchup penalty waived (all of it with enough games and no drop-off). His player note (in darker orange on the page) and the tough-matchup alert say so. Past seasons are read from `data/history/stats/` in the repo, so this is worked out once in the build (about a second) and the page only gets the result per player.
3. **Availability.** Players on BYE or listed Out, IR, PUP or suspended are excluded. Doubtful players count at 25%, and Questionable players count in full but get flagged.
4. **Filling slots.** Fixed positions are filled first, then FLEX, then Superflex, each with the best available player. IDP slots (DL, LB, DB and IDP flex) are filled the same way; a defender Sleeper lists at two spots (DL and LB) can fill either. A defender with no Sleeper projection uses his season average in that league's scoring, and his matchup is how many IDP points the offense he faces gives up to his position. IR and taxi slots are left alone.
5. **Locked games.** Once a player's game kicks off, he stays where he is, and the page shows his real points (LIVE or FINAL).
6. **Auto-subs.** Sleeper's public API shows whether a league allows auto-subs (`max_subs` in the league settings) but not which player anyone picked, and its matchup points leave the sub's score out (checked 2026-10-19 with `tools/autosub_probe.py`). So in those leagues the page shows a note under the scoreboard that auto-subs aren't counted and the Sleeper app's score can be higher. The auto-sub display and scoring code (`auto_subs()` in `analysis.py`, same in `web/benchpress.js`) is in place and kicks in if Sleeper ever adds the picks to the API; `AUTO_SUB_KEYS` is where to point it.

Alerts on the page are **Fix** (empty slot or an unavailable starter), **Swap** (the recommended changes), **Watch** (Questionable starters, with an earlier-game bench player to use as an auto-sub when there is one, or a starter whose QB is out), **Your call** (Sleeper's projections and the matchup data disagree, or a benched smash-spot player came close) and **Note** (tough matchups, early games, open IR spots, roster changes, auto-subs you've set). An auto-sub that is out, didn't play, or plays after its starter is a **Fix**; a Questionable starter with a working auto-sub moves from Watch to a Note.

## Configuration

`config/config.json`:

| Key | Purpose |
|---|---|
| `username`, `user_id` | The owner's Sleeper account, which gets league nicknames and tab order. |
| `matchup_weight` | 0 means pure Sleeper projections, and 1 applies the full defense effect. Default is 0.5. |
| `easy_matchup_boost`, `easy_matchup_ranks` | Smash-spot boost against the easiest defenses for a position (default 0.3, the 3 easiest). 0 turns it off. |
| `smash_alert_gap` | A benched smash-spot player this many points or fewer behind a starter gets a Your call alert. Default is 3. |
| `history_seasons` | Past seasons used to find players who handle tough defenses. Default is 5; 0 uses this season only. |
| `history_decay` | How much each season back counts in that check: 0.7 means last season's games count 0.7, the one before 0.49, and so on. Default is 0.7; 1 counts every season equally. |
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
| `python-subscripts/history.py` | Reads and writes the past seasons' stats in `data/history/stats/`. |
| `web/benchpress.js` | The Refresh button's lineup builder, a JavaScript port of the per-week logic. |
| `tools/autosub_probe.py` | Prints what Sleeper returns for your leagues' auto-subs, to check Bench Press can read them. |
| `tools/stats_backfill.py` | One-time download of past seasons' weekly stats into `data/history/stats/` (default: the 5 before this one). |
| `tools/parity.js` | Replays the build's Sleeper responses through `web/benchpress.js` and checks it picks the same lineups as the Python. |
| `config/lineups_template.html` | The look of the lineup page. Its `<head>` also carries the barbell favicon inline (SVG, plus 32 px and 180 px PNGs), so the landing, live and user pages all get it with no extra site files. |
| `data/history/stats/<season>.json.gz` | Weekly stats for past seasons (every active player-game), kept in the repo for player trends (the one tracked folder under `data/`). `history.load(season)` returns them shaped like Sleeper's weekly stats. |
| `.github/workflows/` | `build.yml` (scheduled build and Pages deploy) and `cascade-merge.yml` (merges `main` back into `develop`). |
| `docs/` | Design notes (the static-site plan), `ANALYZE-PROMPT.md` and `favicon.svg` (the source of the inline favicon). |
| `data/` | Everything a run writes (git ignores it), plus the tracked `data/history/`. |

## Data sources

All data comes from Sleeper, so names, IDs, injury tags and scoring match the app.

- **Documented API** (`api.sleeper.app/v1`): users, leagues, rosters, matchups and players. No key is needed.
- **Undocumented app endpoints** (`api.sleeper.com`): weekly stats, projections and the schedule. These are unofficial, so if they change, `python-subscripts/sleeper.py` is the only file to fix. Past seasons' weekly stats (for the tough-defense check) are saved in the repo under `data/history/stats/` by `python3 tools/stats_backfill.py`, run once on the Mac (Sleeper blocks the cloud); a season not saved there is downloaded from Sleeper instead.
- **Auto-subs:** Sleeper doesn't document where it stores them. Bench Press checks the likely field names, which haven't been confirmed against live data yet; `python3 tools/autosub_probe.py` shows what your leagues return.

The API is read-only, so lineup changes are made in the Sleeper app.

## Roadmap

- An Ohio Fantasy rebuild mode, as a per-league setting that favors young players and long-term value.
- Confirm Sleeper's auto-sub field with `tools/autosub_probe.py` and point `AUTO_SUB_KEYS` at it.
- Count opponents' auto-subs in the matchup score.

## License

Copyright (c) 2026. All rights reserved. See [COPYRIGHT.md](COPYRIGHT.md).
