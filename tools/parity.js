#!/usr/bin/env node
/* Parity check: does web/benchpress.js recommend the same lineups as benchpress.py?
 *
 * Replays the Sleeper responses the Python build recorded (FF_RECORD=<fixtures>) through
 * the JavaScript builder and compares every league's lineup with data/latest*.json.
 *
 *   node tools/parity.js <site dir> <fixtures dir> <data dir>
 *
 * Exits 1 and lists the differences if any lineup, total or alert count disagrees.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const BenchPress = require("../web/benchpress.js");

const [siteDir, fixDir, dataDir] = process.argv.slice(2);
if (!siteDir || !fixDir || !dataDir) {
  console.error("usage: node tools/parity.js <site dir> <fixtures dir> <data dir>");
  process.exit(2);
}

// same naming as _fixture_name() in python-subscripts/sleeper.py
const fixtureName = (url) => url.split("://")[1].replace(/\//g, "_").replace(/\?/g, "_").replace(/&/g, "_").replace(/\[\]/g, "") + ".json";

async function fetchJSON(url) {
  const file = url.startsWith("site:")
    ? path.join(siteDir, url.slice("site:".length))
    : path.join(fixDir, fixtureName(url));
  if (!fs.existsSync(file)) {
    if (url.startsWith("site:")) return null;
    throw new Error("no recorded response for " + url);
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const ids = (xs) => xs.map(p => (p ? p.id : "-")).join(",");
const close = (a, b) => Math.abs((a || 0) - (b || 0)) <= 0.11;
const alertCounts = (L) => {
  const c = {};
  // roster-change notes depend on each side's own snapshot, so they're left out
  for (const a of L.alerts) if (!/^Roster changes/.test(a.text)) c[a.level] = (c[a.level] || 0) + 1;
  return JSON.stringify(Object.keys(c).sort().map(k => [k, c[k]]));
};

(async () => {
  const files = fs.readdirSync(dataDir).filter(f => /^latest(_.+)?\.json$/.test(f));
  const today = new Date().toISOString().slice(0, 10);  // the runner's date, same as Python's date.today() in UTC
  let problems = 0, leagues = 0;
  for (const f of files) {
    // data/ is cached between runs; only compare people built in this run
    if (Date.now() - fs.statSync(path.join(dataDir, f)).mtimeMs > 6 * 3600 * 1000) { console.log("skip " + f + " (not built this run)"); continue; }
    const py = JSON.parse(fs.readFileSync(path.join(dataDir, f), "utf8"));
    if (!py.username) { console.log("skip " + f + " (built before parity support)"); continue; }
    let js;
    try {
      const now = py.built_at ? new Date(py.built_at * 1000) : new Date();  // same clock as the Python run
      js = await BenchPress.build({ username: py.username, base: "site:", fetchJSON, today, week: py.week, now });
    } catch (e) {
      console.log("FAIL " + py.username + ": " + e.message);
      problems++;
      continue;
    }
    const jsById = Object.fromEntries(js.leagues.map(L => [L.id, L]));
    for (const L of py.leagues) {
      leagues++;
      const J = jsById[L.id];
      const where = py.username + " / " + L.short;
      if (!J) { console.log("FAIL " + where + ": league missing from JavaScript"); problems++; continue; }
      const diffs = [];
      for (const k of ["rec", "sleeper", "cur"]) {
        const a = ids(L.lineup.map(s => s[k])), b = ids(J.lineup.map(s => s[k]));
        if (a !== b) diffs.push(k + " lineup\n      py " + a + "\n      js " + b);
      }
      for (const k of ["proj_rec", "proj_rec_sleeper", "proj_cur", "live_pts"]) if (!close(L[k], J[k])) diffs.push(k + " py " + L[k] + " js " + J[k]);
      if (!!L.opponent !== !!J.opponent || (L.opponent && (!close(L.opponent.proj, J.opponent.proj) || !close(L.opponent.live, J.opponent.live)))) {
        diffs.push("opponent py " + JSON.stringify(L.opponent) + " js " + JSON.stringify(J.opponent));
      }
      if (alertCounts(L) !== alertCounts(J)) diffs.push("alerts py " + alertCounts(L) + " js " + alertCounts(J));
      if (diffs.length) {
        problems++;
        console.log("FAIL " + where + "\n    " + diffs.join("\n    "));
      } else {
        console.log("ok   " + where);
      }
    }
  }
  console.log("\n" + leagues + " leagues compared, " + problems + " with differences");
  process.exit(problems ? 1 : 0);
})();
