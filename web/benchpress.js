/* Bench Press live refresh: builds the same lineup data as benchpress.py, in the browser.
 *
 * The scheduled build publishes the slow-changing data to data/ next to this file
 * (player list, defense-vs-position ranks, each player's game log). A refresh then only
 * fetches this week's leagues, rosters, matchups, projections and live points from Sleeper,
 * and runs the same scoring, matchup adjustment, lineup fill and alerts as the Python.
 *
 * Keep this in step with benchpress.py and python-subscripts/analysis.py; the build's
 * parity check (tools/parity.js) compares the two on every run.
 *
 * Works in a browser (window.BenchPress) and in Node (module.exports) for the parity check.
 */
(function (root) {
  "use strict";

  const V1 = "https://api.sleeper.app/v1";
  const APP = "https://api.sleeper.com";
  const IDP_POS = ["DL", "LB", "DB"];
  const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"].concat(IDP_POS);
  const ALL_POS = POSITIONS;

  const SLOT_ELIG = {
    QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"], K: ["K"], DEF: ["DEF"],
    FLEX: ["RB", "WR", "TE"],
    WRRB_FLEX: ["RB", "WR"],
    REC_FLEX: ["WR", "TE"],
    SUPER_FLEX: ["QB", "RB", "WR", "TE"],
    DL: ["DL"], LB: ["LB"], DB: ["DB"],
    IDP_FLEX: ["DL", "LB", "DB"],
  };
  const SLOT_LABEL = { SUPER_FLEX: "SF", WRRB_FLEX: "W/R", REC_FLEX: "W/T", FLEX: "FLEX", IDP_FLEX: "IDP" };
  const OUT_STATUSES = new Set(["Out", "IR", "PUP", "Sus", "NA", "COV", "DNR"]);
  const HURT = new Set(["Out", "IR", "Doubtful", "PUP", "Sus"]);

  // ---- small helpers (Python equivalents in analysis.py) -------------------------

  const num = (x) => { const n = parseFloat(x); return Number.isFinite(n) ? n : 0; };
  // Python's round(): exact decimal value, ties to even (round(500.25, 1) == 500.2)
  function pyRound(x, n) {
    if (!Number.isFinite(x)) return x;
    const [ip, fp] = Math.abs(x).toFixed(80).split(".");
    const digits = ip + fp.slice(0, n), rest = fp.slice(n);
    const up = rest[0] > "5" || (rest[0] === "5" && (/[1-9]/.test(rest.slice(1)) || +digits[digits.length - 1] % 2 === 1));
    const v = Number(BigInt(digits) + (up ? 1n : 0n)) / Math.pow(10, n);
    return x < 0 ? -v : v;
  }
  const r1 = (x) => pyRound(x, 1);
  const r2 = (x) => pyRound(x, 2);
  const f1 = (x) => pyRound(x, 1).toFixed(1);  // Python "%.1f"
  const isAlpha = (s) => /^[A-Za-z]+$/.test(s || "");

  function score(stats, scoring) {
    let total = 0;
    for (const k in stats || {}) {
      const w = scoring[k], v = stats[k];
      if (w && typeof v === "number") total += v * w;
    }
    return r2(total);
  }

  function playerPos(pl) {
    if (!pl) return null;
    if (ALL_POS.includes(pl.position)) return pl.position;
    for (const p of pl.fantasy_positions || []) if (ALL_POS.includes(p)) return p;
    return pl.position || null;
  }

  // player_fpos() in analysis.py: some defenders can fill two IDP spots (DL and LB)
  function playerFpos(pl, pos) {
    if (!IDP_POS.includes(pos)) return [pos];
    return [pos].concat(((pl || {}).fantasy_positions || []).filter(p => IDP_POS.includes(p) && p !== pos));
  }

  function playerName(pid, pl) {
    if (!pl) return pid;
    return ((pl.first_name || "") + " " + (pl.last_name || "")).trim() || pid;
  }

  function ordinal(n) {
    const suf = (n % 100 >= 10 && n % 100 <= 20) ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
    return n + suf;
  }

  function matchupText(pos, row) {
    if (!row) return "";
    const r = row.rank, of = row.of;
    if (pos === "DEF" || IDP_POS.includes(pos)) {
      return r <= of / 2 ? ordinal(r) + "-toughest offense for " + pos + "s" : ordinal(of - r + 1) + "-friendliest offense for " + pos + "s";
    }
    return r <= of / 2 ? ordinal(r) + "-toughest vs " + pos : ordinal(of - r + 1) + "-easiest vs " + pos;
  }

  function parseDate(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  function dayLabel(s) {
    const d = parseDate(s);
    return d ? ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()] : "";
  }

  // today: "YYYY-MM-DD"
  function gameState(game, today) {
    if (!game) return null;
    const status = String(game.status || "").toLowerCase();
    const playedBefore = !!game.date && parseDate(game.date) && game.date < today;
    if (status === "complete" || ((status === "pre_game" || status === "") && playedBefore)) return "final";
    if (status !== "pre_game" && status !== "") return "live";
    return "pre";
  }

  // US Eastern date and minutes past midnight for a moment in time
  function easternClock(now) {
    try {
      const p = {};
      new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now).forEach(x => { p[x.type] = x.value; });
      return { date: p.year + "-" + p.month + "-" + p.day, min: (+p.hour % 24) * 60 + (+p.minute) };
    } catch (e) {
      return { date: localISODate(now), min: now.getHours() * 60 + now.getMinutes() };
    }
  }

  // game_left() in analysis.py: rough share of a game still to play, from the usual kickoff slots
  function gameLeft(game, gstate, clock) {
    if (gstate === "final") return 0;
    if (gstate !== "live") return 1;
    const gd = parseDate(game.date), cd = parseDate(clock.date);
    if (!gd || !cd) return 0.5;
    const mins = Math.round((Date.UTC(cd.getFullYear(), cd.getMonth(), cd.getDate()) - Date.UTC(gd.getFullYear(), gd.getMonth(), gd.getDate())) / 86400000) * 1440 + clock.min;
    let kick;
    if (gd.getDay() === 1 || gd.getDay() === 4) kick = 20 * 60 + 15;
    else if (mins - 13 * 60 < 210) kick = 13 * 60;
    else if (mins < 20 * 60 + 20) kick = 16 * 60 + 15;
    else kick = 20 * 60 + 20;
    return Math.min(1, Math.max(0.05, 1 - (mins - kick) / 195));
  }

  function fmtG(x) { return String(Number(Number(x).toPrecision(2))); }

  function leagueFormat(lg) {
    const ss = lg.scoring_settings || {};
    const rp = lg.roster_positions || [];
    const ppr = num(ss.rec);
    const fmt = { 1: "PPR", 0.5: "Half PPR", 0: "Standard" }[ppr] || fmtG(ppr) + " PPR";
    const bits = [{ 0: "Redraft", 1: "Keeper", 2: "Dynasty" }[(lg.settings || {}).type] || "League",
      (lg.total_rosters || 0) + " teams", fmt];
    if (rp.includes("SUPER_FLEX")) bits.push("Superflex");
    if (num(ss.bonus_rec_te)) bits.push("TE +" + fmtG(num(ss.bonus_rec_te)));
    if (num(ss.pass_td) !== 4) bits.push(String(num(ss.pass_td)) + " pt pass TD");
    return bits.join(" · ");
  }

  // ---- schedule ---------------------------------------------------------------------

  function Schedule(games) {
    this.games = games || [];
    this.byWeek = {};
    for (const g of this.games) {
      const w = g.week;
      const wk = this.byWeek[w] || (this.byWeek[w] = {});
      wk[g.home] = { opp: g.away, home: true, date: g.date, status: g.status };
      wk[g.away] = { opp: g.home, home: false, date: g.date, status: g.status };
    }
  }
  Schedule.prototype.weeks = function () { return Object.keys(this.byWeek).map(Number).sort((a, b) => a - b); };
  Schedule.prototype.weekComplete = function (w) {
    const gs = this.games.filter(g => g.week === w);
    return gs.length > 0 && gs.every(g => g.status === "complete");
  };
  Schedule.prototype.targetWeek = function () {
    const ws = this.weeks();
    for (const w of ws) if (!this.weekComplete(w)) return w;
    return ws.length ? ws[ws.length - 1] : 1;
  };
  Schedule.prototype.game = function (w, t) { return (this.byWeek[w] || {})[t] || null; };
  Schedule.prototype.teams = function () {
    const s = new Set();
    for (const w in this.byWeek) for (const t in this.byWeek[w]) s.add(t);
    return s;
  };
  Schedule.prototype.byes = function (w) {
    const playing = this.byWeek[w] || {};
    return [...this.teams()].filter(t => !(t in playing)).sort();
  };

  // ---- auto-subs (auto_subs, sub_state, sub_can_score, sub_options in analysis.py) -------------

  const AUTO_SUB_KEYS = ["auto_subs", "autosubs", "auto_sub", "subs"];
  const STARTER_KEYS = ["starter", "starter_id", "player_id", "original", "from"];
  const SUB_KEYS = ["sub", "sub_id", "auto_sub", "substitute", "to"];
  const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);

  function autoSubs(...objs) {
    for (const o of objs) {
      for (const where of [o || {}, (o || {}).metadata || {}, (o || {}).settings || {}]) {
        if (!isObj(where)) continue;
        for (const k of AUTO_SUB_KEYS) {
          const v = where[k];
          const out = {};
          if (isObj(v)) {
            for (const a in v) if (a && v[a] && String(v[a]) !== "0") out[String(a)] = String(v[a]);
          } else if (Array.isArray(v)) {
            for (const e of v) {
              let a, b;
              if (isObj(e)) {
                a = (STARTER_KEYS.find(x => e[x]) || null); a = a && e[a];
                b = (SUB_KEYS.find(x => e[x]) || null); b = b && e[b];
              } else if (Array.isArray(e) && e.length === 2) [a, b] = e;
              else continue;
              if (a && b && String(b) !== "0") out[String(a)] = String(b);
            }
          }
          if (Object.keys(out).length) return out;
        }
      }
    }
    return {};
  }

  function subState(s) {
    if (s.locked) return (!s.available || (s.game_state === "final" && !s.played)) ? "in" : "unused";
    if (!s.available) return "in";
    return s.status === "Doubtful" ? "doubtful" : "backup";
  }

  const subCanScore = (b) => (b.locked ? (b.played || b.game_state === "live") : b.available);

  function subOptions(slot, s, bench) {
    const elig = SLOT_ELIG[slot] || [];
    return bench.filter(b => b.available && !b.locked && b.date && s.date && b.date < s.date &&
      (b.fpos || [b.pos]).some(x => elig.includes(x)));
  }

  // played() in analysis.py, plus Sleeper's game-day actives flag
  function playedWeek(stats, pid) {
    const s = stats || {};
    return num(s.gp) > 0 || num(s.off_snp) > 0 || num(s.def_snp) > 0 || isAlpha(pid) || num(s.gms_active) > 0;
  }

  // ---- lineup optimizer (fill_lineup in analysis.py) ------------------------------------
  // pool is an array of [pid, info] in roster order, so ties break the same way as Python.

  function fillLineup(slots, pool, key, preset, exclude) {
    const order = slots.map((s, i) => i)
      .sort((a, b) => ((SLOT_ELIG[slots[a]] || []).length || 99) - ((SLOT_ELIG[slots[b]] || []).length || 99) || a - b);
    preset = preset || slots.map(() => null);
    const used = new Set([...preset.filter(Boolean), ...(exclude || [])]);
    const result = preset.slice();
    for (const i of order) {
      const elig = SLOT_ELIG[slots[i]];
      if (!elig || result[i]) continue;
      let best = null, bestVal = null;
      for (const [pid, p] of pool) {
        if (used.has(pid) || !(p.fpos || [p.pos]).some(x => elig.includes(x)) || !p.available) continue;
        if (best === null || p[key] > bestVal) { best = pid; bestVal = p[key]; }
      }
      if (best !== null) { used.add(best); result[i] = best; }
    }
    return result;
  }

  // ---- time stamp ("Sat Oct 17, 3:22 PM EDT") --------------------------------------------

  function easternStamp(now) {
    try {
      const parts = {};
      new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit", timeZoneName: "short",
      }).formatToParts(now).forEach(p => { parts[p.type] = p.value; });
      return parts.weekday + " " + parts.month + " " + parts.day + ", " + parts.hour + ":" + parts.minute + " " +
        parts.dayPeriod + " " + parts.timeZoneName;
    } catch (e) {
      return now.toString();
    }
  }

  function localISODate(d) {
    const p = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  // ---- data access ------------------------------------------------------------------------

  // opts.fetchJSON(url) -> parsed JSON or null (404). opts.base: URL of the site root (data/ lives there).
  function makeSource(opts) {
    const fetchJSON = opts.fetchJSON || (async (url) => {
      const r = await fetch(url, { cache: "no-store" });
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(url + " returned " + r.status);
      return r.json();
    });
    const site = (name) => fetchJSON(opts.base.replace(/\/?$/, "/") + "data/" + name);
    // Sleeper's app endpoints first; the build's copy if the browser can't reach them.
    async function app(url, mirror) {
      try {
        const d = await fetchJSON(url);
        if (d) return d;
      } catch (e) { /* fall through to the copy */ }
      if (!mirror) return null;
      try { return await site(mirror); } catch (e) { return null; }
    }
    return { v1: (path) => fetchJSON(V1 + path), app, site };
  }

  const posQuery = () => POSITIONS.map(p => "position[]=" + p).join("&");

  // ---- the build (main() in benchpress.py) ---------------------------------------------------

  async function build(opts) {
    const src = makeSource(opts);
    const now = opts.now || new Date();
    const today = opts.today || localISODate(now);
    const clock = easternClock(now);
    const [stat, players] = await Promise.all([src.site("static.json"), src.site("players.json")]);
    if (!stat || !players) throw new Error("The site's data files are missing. Wait for the next scheduled build.");

    const W = num(stat.matchup_weight === undefined ? 0.5 : stat.matchup_weight);
    const ownerName = String((stat.owner || {}).username || "").toLowerCase();
    const uname = String(opts.username || "").replace(/^@/, "");
    if (!uname) throw new Error("No Sleeper username given.");
    const other = uname.toLowerCase() !== ownerName;
    const nick = other ? {} : (stat.league_nicknames || {});

    const me = await src.v1("/user/" + encodeURIComponent(other ? uname : ((stat.owner || {}).user_id || uname)));
    if (!me) throw new Error("Couldn't find Sleeper user \"" + uname + "\".");
    const tag = String(me.username || uname).toLowerCase();
    const userId = me.user_id;
    const state = (await src.v1("/state/nfl")) || {};
    const season = String(stat.season || state.league_season || state.season);

    const sched = new Schedule(await src.app(APP + "/schedule/nfl/regular/" + season, "schedule.json") || []);
    const week = opts.week || sched.targetWeek();
    const wk2 = String(week).padStart(2, "0");
    const q = "?season_type=regular&" + posQuery();

    const projList = await src.app(APP + "/projections/nfl/" + season + "/" + week + q, "projections_w" + wk2 + ".json") || [];
    const proj = {};
    for (const r of projList) if (r.player_id) proj[r.player_id] = r;
    const started = Object.keys(sched.byWeek[week] || {}).filter(t => gameState(sched.game(week, t), today) !== "pre");
    const liveStats = {};
    if (started.length) {
      const live = await src.app(APP + "/stats/nfl/" + season + "/" + week + q, "live_w" + wk2 + ".json") || [];
      for (const r of live) if (r.player_id) liveStats[r.player_id] = r.stats || {};
    }

    const dvp = stat.dvp || {};
    const logs = stat.logs || {};
    const inj = stat.injuries || {};
    const byesNow = sched.byes(week);

    function injuryOf(pid) {
      const pr = proj[pid];
      if (pr && pr.player != null) return pr.player.injury_status || "";
      return (players[pid] || {}).injury_status || "";
    }

    let leagues = ((await src.v1("/user/" + userId + "/leagues/nfl/" + season)) || [])
      .filter(l => l.status !== "pre_draft")
      .filter(l => !(stat.ignore_leagues || []).includes(l.league_id));
    const order = stat.league_order || [];
    const rankOf = (l) => (order.includes(l.league_id) ? order.indexOf(l.league_id) : 99);
    leagues.sort((a, b) => rankOf(a) - rankOf(b) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));

    const snapKey = "benchpress.snapshot." + tag;
    let oldSnap = {};
    try { oldSnap = JSON.parse((opts.storage && opts.storage.getItem(snapKey)) || "{}"); } catch (e) { oldSnap = {}; }
    const newSnap = {};
    const outLeagues = [];

    for (const lg of leagues) {
      const lid = lg.league_id;
      const short = nick[lid] || nick[lg.name] || lg.name;
      const ss = lg.scoring_settings || {};
      const rp = lg.roster_positions || [];
      const slots = rp.filter(s => s !== "BN" && s !== "IR" && s !== "TAXI");
      const [rosters, lusers, mu] = await Promise.all([
        src.v1("/league/" + lid + "/rosters"), src.v1("/league/" + lid + "/users"), src.v1("/league/" + lid + "/matchups/" + week)]);
      const users = {};
      for (const u of lusers || []) users[u.user_id] = u;
      const mine = (rosters || []).find(r => r.owner_id === userId || (r.co_owners || []).includes(userId));
      if (!mine) continue;
      const rosterIds = {};
      for (const r of rosters) rosterIds[r.roster_id] = r;

      const allPids = (mine.players || []).filter(Boolean);
      const reserve = new Set(mine.reserve || []);
      const taxi = new Set(mine.taxi || []);

      const prev = new Set(oldSnap[lid] || []);
      const added = prev.size ? allPids.filter(p => !prev.has(p)) : [];
      const dropped = [...prev].filter(p => !allPids.includes(p));
      newSnap[lid] = allPids;

      function info(pid) {
        const pl = players[pid] || {};
        const pos = playerPos(pl) || (isAlpha(pid) ? "DEF" : "?");
        const team = pos === "DEF" ? pid : (pl.team || "");
        const pr = proj[pid];
        const status = injuryOf(pid);
        const game = team ? sched.game(week, team) : null;
        const gstate = gameState(game, today);
        const locked = gstate === "live" || gstate === "final";
        const actual = (locked && pid in liveStats) ? score(liveStats[pid], ss) : (locked ? 0 : null);
        let sleeperPts = score((pr || {}).stats, ss);
        if (IDP_POS.includes(pos) && !sleeperPts) {
          // no Sleeper projection for this defender: use his season average in this league's scoring
          const past = (logs[pid] || []).map(s => score(s, ss));
          sleeperPts = past.length ? past.reduce((a, b) => a + b, 0) / past.length : 0;
        }
        const opp = game ? game.opp : null;
        const row = opp ? ((dvp[pos] || {})[opp] || null) : null;
        const mult = row ? row.mult : 1.0;
        const adj = sleeperPts * (1 + W * (mult - 1));
        let why = "";
        if (!team) why = "Free agent / no team";
        else if (!game) why = "BYE";
        else if (OUT_STATUSES.has(status)) why = status;
        const factor = status === "Doubtful" ? 0.25 : 1.0;
        const pts = (logs[pid] || []).map(s => score(s, ss));
        const notes = [];
        if (opp && ["QB", "RB", "WR", "TE"].includes(pos)) {
          const hurt = ((inj[opp] || {}).def || []).filter(x => HURT.has(x.status));
          if (hurt.length) notes.push("Opp D banged up: " + hurt.slice(0, 4).map(x => x.pos + " " + x.name + " (" + x.status + ")").join(", "));
        }
        if (team && ["RB", "WR", "TE"].includes(pos)) {
          for (const x of (inj[team] || {}).off || []) {
            if (x.pos === "QB" && HURT.has(x.status)) notes.push("His QB " + x.name + " is " + x.status);
          }
        }
        const last3 = pts.slice(-3);
        return {
          id: pid,
          name: pos !== "DEF" ? playerName(pid, players[pid]) : ((pl.first_name || pid) + " " + (pl.last_name || "")).trim(),
          pos, fpos: playerFpos(pl, pos), team, status,
          opp, home: game ? game.home : null, day: game ? dayLabel(game.date) : "",
          date: game ? game.date : null,
          sleeper: r2(sleeperPts * factor), adj: r2(adj * factor),
          raw_sleeper: r2(sleeperPts),
          mult, rank: row ? row.rank : null, of: row ? row.of : null,
          matchup: matchupText(pos, row), available: why === "",
          why, notes,
          gp: pts.length, avg: pts.length ? r1(pts.reduce((a, b) => a + b, 0) / pts.length) : null,
          last3: pts.length ? r1(last3.reduce((a, b) => a + b, 0) / last3.length) : null,
          reserve: reserve.has(pid), taxi: taxi.has(pid),
          locked, game_state: gstate, actual,
          // took the field this week (Sleeper marks game-day actives with gms_active)
          played: locked && playedWeek(liveStats[pid], pid),
          left: gameLeft(game, gstate, clock),
        };
      }

      const pool = new Map(allPids.map(pid => [pid, info(pid)]));
      const startable = [...pool].filter(([, p]) => !p.reserve && !p.taxi);
      for (const [, p] of startable) {
        p.value_adj = p.available ? p.adj : -1;
        p.value_sleeper = p.available ? p.sleeper : -1;
      }
      const cur = (mine.starters || []).slice();
      while (cur.length < slots.length) cur.push(null);
      const preset = cur.map(c => (c && c !== "0" && pool.has(c) && pool.get(c).locked) ? c : null);
      const frozen = startable.filter(([, p]) => p.locked).map(([pid]) => pid);
      const rec = fillLineup(slots, startable, "value_adj", preset, frozen);
      const recSleeper = fillLineup(slots, startable, "value_sleeper", preset, frozen);

      const P = (pid) => (!pid || pid === "0") ? null : (pool.get(pid) || info(pid));

      const recSet = new Set(rec.filter(Boolean));
      const curSet = new Set(cur.filter(x => x && x !== "0"));

      // ---- auto-subs: {starter: bench player whose points count if the starter doesn't play} ----
      const mineMu = (mu || []).find(m => m.roster_id === mine.roster_id);
      const subs = {};
      for (const [a, b] of Object.entries(autoSubs(mineMu, mine))) if (curSet.has(a) && pool.has(b) && !curSet.has(b)) subs[a] = b;
      // projected final: real points so far plus the projection for what's left of the game
      const ptsOf = (p, key) => (p.locked ? (p.actual || 0) + p[key] * p.left : p[key]);
      // slot_pts() in benchpress.py: a starter's points, counting his auto-sub when the sub isn't also starting
      function slotPts(x, key, ids) {
        const b = subs[x];
        if (!b || ids.has(b)) return ptsOf(P(x), key);
        const p = P(x), q = P(b);
        const st = subState(p);
        const sub = subCanScore(q) ? ptsOf(q, key) : 0;
        if (st === "in") return sub;
        if (st === "doubtful") return ptsOf(p, key) + 0.75 * sub;  // a Doubtful starter counts 25%; the sub covers the rest
        return ptsOf(p, key);
      }
      function slotLive(x) {
        const p = P(x), b = subs[x];
        if (b && subState(p) === "in") return P(b).locked ? (P(b).actual || 0) : 0;
        return p.locked ? (p.actual || 0) : 0;
      }

      const lineup = slots.map((s, i) => {
        const rId = SLOT_ELIG[s] ? rec[i] : (cur[i] !== "0" ? cur[i] : null);
        const entry = { slot: s, label: SLOT_LABEL[s] || s, rec: P(rId), cur: P(cur[i]), sleeper: P(recSleeper[i]) };
        if (cur[i] in subs) {
          entry.autosub = { player: P(subs[cur[i]]), state: subState(P(cur[i])),
            adj: r2(slotPts(cur[i], "adj", new Set())), sleeper: r2(slotPts(cur[i], "sleeper", new Set())) };
        }
        return entry;
      });
      const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
      const bench = [...pool].filter(([pid, p]) => !recSet.has(pid) && !p.reserve && !p.taxi).map(([, p]) => p)
        .sort((a, b) => (b.adj - a.adj) || byName(a, b));
      const stash = [...pool.values()].filter(p => p.reserve || p.taxi).sort(byName);

      // ---- alerts ----
      const alerts = [];
      slots.forEach((s, i) => {
        const c = P(cur[i]);
        const lbl = SLOT_LABEL[s] || s;
        if (c && c.locked) return;
        const b = P(subs[cur[i]]);
        let ok = false;
        if (b) {
          // this starter has an auto-sub: say who covers him, and flag a sub that can't
          ok = subCanScore(b);
          if (!ok) {
            alerts.push({ level: "bad", text: c.name + "'s auto-sub " + b.name + " " + (b.locked ? "didn't play" : "is " + (b.why !== "BYE" ? b.why : "on a bye")) + ". Pick a different auto-sub." });
          } else if (!b.locked && b.date && c.date && b.date > c.date) {
            alerts.push({ level: "bad", text: c.name + "'s auto-sub " + b.name + " plays after him (" + b.day + " vs " + c.day + "), so the sub can't kick in." });
          } else if (!c.available) {
            alerts.push({ level: "warn", text: c.name + " is " + (c.why !== "BYE" ? c.why : "on a bye") + " at " + lbl + "; his auto-sub " + b.name + " scores for him (" + f1(ptsOf(b, "sleeper")) + ")." });
            return;
          } else if (c.status === "Doubtful") {
            alerts.push({ level: "warn", text: c.name + " is Doubtful (" + (c.day || "?") + " game); auto-sub " + b.name + " (" + (b.day || "?") + ") covers him if he sits." });
            return;
          }
          if (ok && c.available) {
            alerts.push({ level: "info", text: "Auto-sub set: " + b.name + " (" + (b.day || "?") + ", " + f1(ptsOf(b, "sleeper")) + ") covers " + c.name + " (" + (c.day || "?") + ")" +
              (c.status === "Questionable" ? " if he's ruled out" : "") + "." });
          }
          if (c.status === "Questionable" && ok) return;  // covered: no need to watch the inactives
        }
        if (!c) alerts.push({ level: "bad", text: "Empty " + lbl + " slot in your Sleeper lineup." });
        else if (!c.available) alerts.push({ level: "bad", text: c.name + " is starting at " + lbl + " but is " + (c.why !== "BYE" ? c.why : "on a bye") + "." });
        else if (c.status === "Doubtful") alerts.push({ level: "bad", text: c.name + " is Doubtful and in your lineup." });
        else if (c.status === "Questionable") {
          const opts = b ? [] : subOptions(s, c, bench.filter(p => !curSet.has(p.id)));
          alerts.push({ level: "warn", text: c.name + " is Questionable (" + (c.day || "?") + " game). Check the inactives before kickoff" +
            (opts.length ? ", or set an auto-sub: " + opts[0].name + " (" + opts[0].day + ", " + f1(opts[0].sleeper) + ") plays earlier" : "") + "." });
        }
        else if (c.raw_sleeper === 0 && c.pos !== "DEF") alerts.push({ level: "warn", text: c.name + " is starting with a 0.0 Sleeper projection." });
      });
      const ins = rec.filter(x => x && !curSet.has(x)).map(P);
      const outs = cur.filter(x => x && x !== "0" && !recSet.has(x)).map(P);
      if (ins.length || outs.length) {
        // a benched starter with an auto-sub was worth his sub's points, not nothing
        const gain = ins.reduce((a, p) => a + p.adj, 0) -
          outs.filter(p => p.available || p.id in subs).reduce((a, p) => a + (p.id in subs ? slotPts(p.id, "adj", curSet) : p.adj), 0);
        alerts.push({ level: "change", text: "Lineup change: start " + (ins.map(p => p.name + " (" + f1(p.adj) + ")").join(", ") || "-") +
          "; sit " + (outs.map(p => p.name + " (" + (p.available ? f1(p.adj) : p.why) + ")").join(", ") || "-") +
          " (about " + (gain >= 0 ? "+" : "") + f1(gain) + " pts)." });
      }
      const recSleeperSet = new Set(recSleeper);
      const aOnly = rec.filter(x => x && !recSleeperSet.has(x));
      const sOnly = recSleeper.filter(x => x && !recSet.has(x));
      if (aOnly.length || sOnly.length) {
        const d = (x) => P(x).name + " (" + f1(P(x).sleeper) + ", " + (P(x).matchup || "no data") + ")";
        alerts.push({ level: "call", text: "Matchup call: Sleeper's projections alone would start " + sOnly.map(d).join(", ") +
          "; the matchup data prefers " + aOnly.map(d).join(", ") + ". Close one, your call." });
      }
      for (const x of rec) {
        const p = P(x);
        if (p && p.locked) continue;
        if (p && p.rank && p.rank <= 3 && p.pos !== "DEF") alerts.push({ level: "info", text: p.name + " faces " + p.opp + " (" + p.matchup + ")." });
        if (p) {
          const qb = p.notes.find(n => n.startsWith("His QB"));
          if (qb) alerts.push({ level: "warn", text: p.name + ": " + qb });
        }
      }
      const early = rec.filter(x => x && !P(x).locked && ["Thu", "Fri", "Wed"].includes(P(x).day)).map(P);
      const done = cur.filter(x => x && x !== "0" && P(x).locked).map(P);
      if (done.length) alerts.push({ level: "info", text: "Already played (locked): " + done.map(p => p.name + " " + f1(p.actual || 0) + (p.game_state === "live" ? " live" : "")).join(", ") });
      if (early.length) alerts.push({ level: "info", text: "Plays before Sunday (lock early): " + early.map(p => p.name + " (" + p.day + ")").join(", ") });
      for (const [a, b] of Object.entries(subs)) {
        if (recSet.has(b) && !P(b).locked) alerts.push({ level: "info", text: "The recommendation starts " + P(b).name + ", your auto-sub for " + P(a).name + ". Pick a new auto-sub after the swap." });
      }
      const irSlots = parseInt((lg.settings || {}).reserve_slots || 0, 10) || 0;
      if (irSlots && reserve.size < irSlots) {
        const canIr = bench.filter(p => ["IR", "Out", "PUP", "Doubtful", "Sus"].includes(p.status));
        if (canIr.length) alerts.push({ level: "info", text: "Open IR spot (" + reserve.size + "/" + irSlots + " used). Eligible: " + canIr.map(p => p.name + " (" + p.status + ")").join(", ") + "." });
      }
      if (added.length || dropped.length) {
        alerts.push({ level: "info", text: "Roster changes since last refresh: " +
          (added.length ? "added " + added.map(p => playerName(p, players[p])).join(", ") : "") +
          (dropped.length ? "; dropped " + dropped.map(p => playerName(p, players[p])).join(", ") : "") });
      }

      // ---- fantasy opponent ----
      let oppInfo = null;
      if (mineMu && mineMu.matchup_id != null) {
        const o = mu.find(m => m.matchup_id === mineMu.matchup_id && m.roster_id !== mine.roster_id);
        if (o) {
          const oro = rosterIds[o.roster_id] || {};
          const ou = users[oro.owner_id] || {};
          let oProj = 0, oLive = 0, oStarted = false;
          for (const pid of o.starters || []) {
            if (!pid || pid === "0") continue;
            const opl = players[pid] || {};
            const oteam = isAlpha(pid) ? pid : opl.team;
            const og = sched.game(week, oteam);
            const st = gameState(og, today);
            if (st === "live" || st === "final") {
              const a = score(liveStats[pid] || {}, ss);
              oProj += a + score((proj[pid] || {}).stats, ss) * gameLeft(og, st, clock);
              oLive += a; oStarted = true;
            } else {
              oProj += score((proj[pid] || {}).stats, ss);
            }
          }
          const ost = oro.settings || {};
          oppInfo = {
            team: (ou.metadata || {}).team_name || ou.display_name || "Opponent",
            owner: ou.display_name || "",
            proj: r1(oProj),
            live: r1(oLive), started: oStarted,
            record: (ost.wins || 0) + "-" + (ost.losses || 0),
          };
        }
      }
      const st = mine.settings || {};
      const meU = users[userId] || {};
      const sum = (xs) => xs.reduce((a, b) => a + b, 0);
      outLeagues.push({
        id: lid, name: lg.name, short, format: leagueFormat(lg),
        team_name: (meU.metadata || {}).team_name || meU.display_name || "",
        record: (st.wins || 0) + "-" + (st.losses || 0) + (st.ties ? "-" + st.ties : ""),
        pf: r1(num(st.fpts) + num(st.fpts_decimal) / 100),
        lineup, bench, stash, alerts, opponent: oppInfo,
        // an auto-sub counts for its starter wherever that starter is still in the lineup
        proj_rec: r1(sum(rec.filter(Boolean).map(x => slotPts(x, "adj", recSet)))),
        proj_rec_sleeper: r1(sum(rec.filter(Boolean).map(x => slotPts(x, "sleeper", recSet)))),
        proj_cur: r1(sum(cur.filter(x => x && x !== "0").map(x => slotPts(x, "sleeper", curSet)))),
        any_locked: cur.some(x => x && x !== "0" && P(x).locked),
        live_pts: r1(sum(cur.filter(x => x && x !== "0").map(slotLive))),
        scoring: Object.fromEntries(["rec", "pass_td", "bonus_rec_te", "pass_int", "fum_lost"].map(k => [k, ss[k] === undefined ? null : ss[k]])),
      });
    }

    try { if (opts.storage) opts.storage.setItem(snapKey, JSON.stringify(newSnap)); } catch (e) { /* private mode */ }

    return {
      generated: easternStamp(now),
      owner: me.display_name || uname, is_me: !other,
      sample: false,
      user_sheets: "sheets/" + tag + "/",
      season, week, byes: byesNow, matchup_weight: W,
      stats_weeks: stat.stats_weeks || [], leagues: outLeagues,
      username: tag, live: true, built_at: now.getTime() / 1000,
    };
  }

  const api = { build, score, fillLineup, gameState, leagueFormat, matchupText, Schedule, easternStamp };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BenchPress = api;
})(typeof window !== "undefined" ? window : this);
