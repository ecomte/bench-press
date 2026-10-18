# Bench Press as a free static site: plan

Written 2026-10-18. Phase 1 shipped in 0.1.0. Phase 2 (the Refresh button) is being built in BP-3: `web/benchpress.js`, `python-subscripts/sitedata.py`, `tools/parity.js`. The browser-call fallback below is built in, and Sleeper's CORS behavior is still unverified on a real phone.

## The goal

Friends open one link on their phone, tap **Refresh**, and get a current lineup page. No step uses E's Mac or E's Claude usage. Today every update needs E to run `batchbenchpress.py` and then ask Claude to republish five artifacts.

## Recommendation: a hybrid, built in two phases

**Phase 1: GitHub Actions runs the Python and publishes to GitHub Pages.** The Python stays almost exactly as it is. A scheduled workflow runs the batch on GitHub's machines and publishes each person's page to one site. That alone removes E's Mac and Claude from the loop. "Refresh" in this phase reloads the newest build, which is at most an hour old (every 15 to 30 minutes on game days).

**Phase 2: a live Refresh button in the browser.** Port only the per-person, per-tap part of the logic to JavaScript (look up the user, leagues, rosters, matchups, this week's projections and live points, then score and fill the lineup). The heavy, slow-changing part (the 5 MB player list, season stats, defense-vs-position ranks) stays in Python and is rebuilt by the scheduled workflow into small JSON files on the site. A tap then takes a few seconds and is fully current.

Why not one route alone:

- **Python only (route b)** can't truly refresh on a tap. A page on GitHub Pages can't start a workflow without a GitHub token, and a token can't safely sit in a public page. So it's always "as of the last scheduled run."
- **JavaScript only (route a)** would make every phone download Sleeper's 5 MB player list and up to 7 weeks of full-league stats on every tap, then redo the defense rankings. It also means porting all ~1,000 lines, including CSV sheets and reports nobody reads on a phone.
- **The hybrid** keeps Phase 1 almost free to build, and Phase 2 ports only about 300 lines of logic. If the browser calls ever break, the page still shows the latest scheduled build.

## Can a browser call Sleeper directly?

| Endpoint (what `python-subscripts/sleeper.py` uses) | Browser calls from another site |
|---|---|
| `api.sleeper.app/v1/...` user, leagues, rosters, users, matchups, state, players | Allowed. Sleeper's documented API sends `Access-Control-Allow-Origin: *`; many public browser-only Sleeper tools depend on it. |
| `api.sleeper.com/projections/...`, `/stats/...`, `/schedule/...` (undocumented) | Not verified. Believed to also allow any origin, since the Sleeper web app calls it, but treat it as unconfirmed. |
| `sleepercdn.com` headshots and team logos | Images load fine with a plain `<img>` tag. CORS doesn't apply to image tags. |

These are not tested. Both Claude's cloud container and the Mac sandbox blocked outbound calls to Sleeper during this check. First task of Phase 2 is a one-minute test in Safari or Chrome on any `https://` page: open the developer console and run

```js
fetch("https://api.sleeper.com/projections/nfl/2026/7?season_type=regular&position[]=QB").then(r => r.json()).then(d => console.log("OK", d.length)).catch(e => console.log("BLOCKED", e))
```

**If it's blocked**, the scheduled workflow also copies projections, the schedule and live stats into the site's `data/` folder (every 15 minutes on Sundays), and the browser reads those instead. The per-person refresh stays live, because rosters and matchups come from the documented API. Only projections and live points would trail by up to 15 minutes.

## How today's pieces carry over

| Today | On the static site |
|---|---|
| `benchpress.py`, `python-subscripts/*.py` | Same code, run by the workflow. Two small changes: an output folder option (`--site site/`) and a "no headshot embedding" switch. GitHub Pages can load `sleepercdn.com` images directly, so pages drop from 4 to 10 MB to roughly 300 KB. |
| `config/lineups_template.html` | Reused as-is for rendering. It already draws everything from one `DATA` object, so Phase 2 only has to build that same object in the browser, and the look doesn't change. |
| `data/artifact*.html` + five claude.ai links | Replaced by `https://<github-username>.github.io/bench-press/<username>/`, one per person, e.g. `.../bench-press/calebjones23/`. Friends add it to their home screen once. The claude.ai links can stay as a backup or get a one-line "moved" note. |
| Tabs per league | Unchanged. Each person's page keeps one tab per team, and the remembered tab still works. |
| `config/config.json` (batch users, matchup weight, E's league nicknames and order) | Copied into the repo. Adding a friend means editing `batch_users` there, from the GitHub website or the phone. In Phase 2, any Sleeper username works with `?u=<name>`, no config edit needed. |
| Ohio Fantasy rebuild preference | Not in the code today (README open item). Add it once as a per-league setting, e.g. `"league_modes": {"1326592273378480128": "rebuild"}`, which raises young players and dynasty rank in that league's lineup choices. Write it in Python first (Phase 1), then mirror it in the JS port, with a shared test case so both give the same lineup. The Ohio age and rank snapshot in `data/ohio_players.json` would need a refresh source; Sleeper's player list has age and experience, but not a dynasty rank. |
| Ignore IDP, defense-vs-TE matchups, locked games | Carry over unchanged. They live in `SLOT_ELIG`, `defense_vs_position` and the lock logic, which the port copies one-to-one. |
| `sheets/*.csv`, `reports/*.md`, `ANALYZE-PROMPT.md` | Stay on the Mac. Running locally still works exactly as now. Optionally the workflow could publish the report too. |
| Roster add/drop alerts (`rosters_snapshot*.json`) | Phase 1: the workflow saves the snapshot as a build cache. Phase 2: the browser remembers the last roster it saw on that phone. |

## What the JavaScript port involves (Phase 2)

About 300 lines of Python become about 400 lines of plain JavaScript in one file, with no build step or libraries:

- `score()`, `fill_lineup()`, `SLOT_ELIG`, `game_state()`, `league_format()`: short and direct to port.
- The per-player `info()` block and the alert rules from `benchpress.py`: the bulk of the work.
- The opponent projection and matchup totals.
- Read from the site: `players-slim.json` (only fantasy positions, with name, team, position, injury, depth chart and age, around 400 KB instead of 5 MB), `dvp.json`, `logs-summary.json` (season and last-3 averages), `schedule.json`.

To check it, the workflow runs the Python and the JS on the same saved data (the `FF_FIXTURES` mode already exists) and fails if any recommended lineup differs.

## Repo layout

```
bench-press/                      new public GitHub repo
  benchpress.py, batchbenchpress.py, python-subscripts/, config/   copied from the Mac folder
  web/app.js                      Phase 2 port
  .github/workflows/build.yml     scheduled build + deploy to Pages
```

Schedule (US Eastern): hourly Tue to Sat, every 15 minutes Sunday 12 PM to midnight, and Monday and Thursday nights. That's well inside the free allowance, since public repos get unlimited Actions minutes. GitHub can start scheduled runs a few minutes late, and it pauses schedules after 60 days without a commit to the repo. The page should show "Built ..." prominently (it already does), and a manual **Run workflow** button exists in the Actions tab.

## What E needs to do on GitHub

1. Create a new **public** repository, e.g. `bench-press`. GitHub Pages is free only for public repos on a free account. Everything in it is already public on Sleeper (usernames, league IDs, rosters), and there are no keys or passwords.
2. In the repo, go to **Settings → Pages → Build and deployment → Source** and pick **GitHub Actions**.
3. Let Claude push to it: connect GitHub to Claude at https://claude.ai/connect-github and install the Claude GitHub app on that one repo. Alternatively, E pushes the folder from the Mac with GitHub Desktop.
4. After the first build, send friends their link and have them add it to their home screen.

No secrets, tokens, or paid plan are needed.

## Order of work once E says go

1. Repo, workflow, and Pages deploy for the current Python (Phase 1). Five links working, with the claude.ai artifacts kept as backup.
2. Ohio rebuild setting in Python.
3. CORS test, then the JS port with the parity check (Phase 2), plus `?u=` for any username.
4. Update the READMEs and retire the "publish everyone's lineups" step.
