# Bench Press

[![Release](https://img.shields.io/badge/release-v1.0.1-green)](https://github.com/ecomte/bench-press/releases)

**Open Bench Press: [ecomte.github.io/bench-press](https://ecomte.github.io/bench-press/)**. Search your Sleeper username to see your lineups.

> Let's eat a W.

Fantasy football lineup suggestions for Sleeper leagues. Bench Press pulls your rosters from the Sleeper API, re-scores Sleeper's projections with each league's rules, adjusts them for the opposing defense, and recommends a starting lineup for every team you own. It flags byes, injuries, empty slots and close calls, then renders a tabbed, Sleeper-style lineup page.

This repository is the GitHub version of Bench Press. It began as a set of scripts run by hand on a Mac, with the pages shared by hand afterward. Here the same code is built and published automatically to a free GitHub Pages site, so anyone on the list can open their link and see a current lineup without the owner running anything.

## Status

| Phase | What it delivers | State |
|---|---|---|
| 1. Scheduled builds | GitHub Actions runs the Python on a schedule and deploys one page per person to GitHub Pages. | Released in 0.1.0 (beta) |
| 2. Live refresh | A Refresh button that rebuilds the lineup in the browser from live Sleeper data, for any username (`?u=<name>`). | In progress (BP-3) |

The design, the trade-offs, and the open questions (such as whether Sleeper's projections endpoint allows browser calls) are in [docs/static-site-plan.md](docs/static-site-plan.md).

## How it will be set up

```
Sleeper API ──► GitHub Actions (scheduled) ──► benchpress.py for each user ──► GitHub Pages
                                                                               └─ /<username>/
```

- **Hosting:** GitHub Pages, deployed from GitHub Actions. Each person gets `https://ecomte.github.io/bench-press/<username>/`, and each page keeps one tab per league.
- **Refresh button:** each hosted page has a **Refresh** button that rebuilds the lineup on the phone from live Sleeper data (`web/benchpress.js`). The scheduled build publishes the slow-changing data it needs (player list, defense-vs-position ranks, game logs) to `data/` on the site, so a tap only fetches this week's rosters, projections and live points. If a browser can't reach Sleeper's app endpoints, it uses the build's copies in `data/`.
- **Landing page:** a Sleeper username search. A name with a built page links straight to it; any other name gets a link to `live/?u=<username>`, which builds that person's page on the spot.
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
3. **Availability.** Players on BYE or listed Out, IR, PUP or suspended are excluded. Doubtful players count at 25%, and Questionable players count in full but get flagged.
4. **Filling slots.** Fixed positions are filled first, then FLEX, then Superflex, each with the best available player. IDP slots (DL, LB, DB and IDP flex) are filled the same way; a defender Sleeper lists at two spots (DL and LB) can fill either. A defender with no Sleeper projection uses his season average in that league's scoring, and his matchup is how many IDP points the offense he faces gives up to his position. IR and taxi slots are left alone.
5. **Locked games.** Once a player's game kicks off, he stays where he is, and the page shows his real points (LIVE or FINAL).

Alerts on the page are **Fix** (empty slot or an unavailable starter), **Swap** (the recommended changes), **Watch** (Questionable starters, or a starter whose QB is out), **Your call** (Sleeper's projections and the matchup data disagree) and **Note** (tough matchups, early games, open IR spots, roster changes).

## Configuration

`config/config.json`:

| Key | Purpose |
|---|---|
| `username`, `user_id` | The owner's Sleeper account, which gets league nicknames and tab order. |
| `matchup_weight` | 0 means pure Sleeper projections, and 1 applies the full defense effect. Default is 0.5. |
| `league_nicknames`, `league_order` | Tab names and order for the owner's leagues. |
| `ignore_leagues` | League IDs to skip. |
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
| `tools/parity.js` | Replays the build's Sleeper responses through `web/benchpress.js` and checks it picks the same lineups as the Python. |
| `config/lineups_template.html` | The look of the lineup page. |
| `docs/` | Design notes, starting with the static-site plan. |

## Data sources

All data comes from Sleeper, so names, IDs, injury tags and scoring match the app.

- **Documented API** (`api.sleeper.app/v1`): users, leagues, rosters, matchups and players. No key is needed.
- **Undocumented app endpoints** (`api.sleeper.com`): weekly stats, projections and the schedule. These are unofficial, so if they change, `python-subscripts/sleeper.py` is the only file to fix.

The API is read-only, so lineup changes are made in the Sleeper app.

## Roadmap

- Phase 1: Actions workflow, a `--site` output option, and Pages deploy (BP-1).
- An Ohio Fantasy rebuild mode, as a per-league setting that favors young players and long-term value.
- Phase 2: the live Refresh button, checked against the Python output (BP-3, in progress).

## License

Copyright (c) 2026. All rights reserved. See [COPYRIGHT.md](COPYRIGHT.md).
