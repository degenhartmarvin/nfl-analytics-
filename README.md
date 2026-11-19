# NFL Analytics Dashboard

Mobile-friendly NFL team analytics dashboard with automated 2026 play-by-play data updates.

## Data source
- One consistent provider for team and player play-by-play metrics: nflverse play-by-play.
- Player identity and position mapping: nflverse players registry.
- Download: gzip release asset for the selected season.
- Refresh scheduled daily at 10:15 UTC and can be triggered manually from GitHub Actions.
- Snapshot is published to `public/data/teams_2026.json` only if import and 32-team validation succeed.

## Initial metrics
**Offense:** Yards/play, EPA/play, success rate, explosive pass rate (20+ yards), explosive rush rate (10+ yards), Red Zone TD rate.

**Defense:** Yards/play allowed, EPA/play allowed, success rate allowed, explosive pass/rush allowed, Red Zone TD rate allowed.

**Wide Receivers:** Receiving volume, targets/share, catch rate, YAC, EPA/target, success rate, explosive receptions and drops.

**Quarterbacks:** Passing volume, completion rate, passer rating, ESPN Total QBR, time to throw (NFL Next Gen Stats), YPA/AY/A/ANY/A, EPA/dropback, success rate, CPOE, air yards/aDOT, deep passing, sacks, interceptions, fumbles and rushing production.\n\n**Running Backs:** Carries, rushing yards/TDs, yards per carry, scrimmage yards, first downs, fumbles, RYOE, yards before/after contact, broken tackles, explosive runs, success rate, EPA/rush, stuff rate, red-zone and short-yardage performance, heavy-box rate, and receiving production/efficiency.\n\n**Offensive Line (unit):** Team sack totals/rate and sack yards lost, rushing efficiency/outcomes, stuff and explosive-run rates, short-yardage and goal-line conversion, holding and false-start penalties, plus tackles for loss allowed/rate and rushing yards before contact. Pressure allowed is counted once per dropback when a sack or QB hit is recorded; it is a transparent proxy rather than a charted pressure grade.

## Formulas
- Explosive pass: eligible pass plays gaining 20 or more yards.
- Explosive rush: eligible run plays gaining 10 or more yards.
- Red Zone TD rate: touchdown drives / drives with at least one eligible play at the opponent 20-yard line or closer.
- Team rankings use competition rank (ties share the rank and the next rank is skipped).

## Run tests locally
```bash
python -m unittest discover -s tests -v
```

## GitHub Actions
Run **Actions → NFL Data Refresh and Pages Deploy → Run workflow** to launch the first import. The scheduled workflow runs daily.

## GitHub Pages setup (one-time)
1. Open **Settings → Pages**.
2. Under **Build and deployment → Source**, select **GitHub Actions**.
3. Save if prompted.
4. Open the **Actions** tab and run **NFL Data Refresh and Pages Deploy**.

The dashboard must not be treated as live until the first workflow completes successfully and the snapshot files are published. No demo stats are displayed as live values.
