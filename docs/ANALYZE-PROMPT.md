# Paste this into Claude after running `python3 benchpress.py`

Connect `~/ClaudeVille/fantasy-football` to the chat (or attach the newest `data/reports/*.md`, the `data/sheets/` position CSVs, and `data/sheets/ecomte/`), then paste:

```
I just ran my fantasy football Bench Press (ClaudeVille/fantasy-football, see README.md).
Read the newest file in data/reports/ first, then use the CSVs to dig deeper: position sheets and
DEF_vs_POS.csv in data/sheets/ (filter rostered_by for EComte), my lineups.csv and game_log.csv in data/sheets/ecomte/.

For each of my 4 leagues:
1. Confirm the "Fix" and "Swap" items, and tell me plainly what to change in Sleeper.
2. Make a call on every "Your call" item: who to start, and why, in a sentence.
3. Look for anything the script can't see:
   - target share / snap % trending up or down over the last 3 weeks (data/sheets/ecomte/game_log.csv)
   - a player who has struggled against defenses ranked top-10 at his position
     (avg_vs_top10_def vs avg_vs_other_def) and is facing one now
   - a starter whose own QB is out, or whose opponent's defense is missing starters
   - Questionable players in late games (Sun night / Mon) where I'd have no fallback
4. Name one bench player or free-agent-type pickup worth watching, if the sheets show one.

Keep it short: a checklist per league that I can act on in the Sleeper app.
If anything looks surprising (injury status, bye), check the news before telling me to act on it.
```
