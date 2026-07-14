# vmsimulator — project context

World Cup 2026 Monte Carlo simulator + fantasy-pool tracker for two friend competitions
("Trap" and "Andreas"). Static site, deployed free to GitHub Pages. UI is in **Danish**;
team names are stored internally in **English** and translated for display.

## Deploy & run
- **Repo:** github.com/chrtrap/vmsimulator (branch `main`). **Live:** https://chrtrap.github.io/vmsimulator/
- **CI/CD:** `.github/workflows/deploy.yml` runs on every push to `main` → installs `pandas numpy`
  → runs `build.py` → uploads `site/` as a Pages artifact → `actions/deploy-pages`. **Pages source =
  "GitHub Actions"** (`build_type: workflow`, set via the API — not in the repo). Live in ~1 min. Free
  (public repo). No secrets.
  - **The deploy is retried up to 5× with backoff** (`deploy1`..`deploy5` steps, each gated on the
    previous attempt's `outcome == 'failure'`; first success short-circuits the rest). GitHub's Pages
    deploy backend intermittently (~half the time) rejects a deployment on the first status poll with
    **"Deployment failed, try again later."** — instant, unrelated to the build, ~50%. Each attempt is a
    fresh deployment, so retrying reaches success. **Do not** re-add `cancel-in-progress: true` and do not
    go back to a `gh-pages` branch: branch-based Pages runs GitHub's *managed* "pages build and
    deployment" workflow, which uses the same flaky `deploy-pages` internally and **can't be given
    retries** — that's why the branch approach (tried 2026-07-05) was reverted.
  - The workflow writes `site/version.txt` = `<commit SHA> <UTC timestamp>`. Verify a deploy landed:
    `curl -s https://chrtrap.github.io/vmsimulator/version.txt` should show HEAD's SHA.
  - If ALL 5 attempts ever fail (job red), just re-run the job or push again — the next run's retries
    almost always clear it. Nothing to fix in the code.
- **Update loop:** edit `data/knockout.csv` (and/or refresh `Elo files/`), commit, push → ~1 min → live.
- **Local dev:** needs pandas+numpy (any Python ≥3.11; code is pandas-3 compatible).
  - `python3 server.py` → http://localhost:8000 (serves `index.html` + a live, cached `/data.json`).
  - or `python3 build.py` then `cd site && python3 -m http.server 8080`.
  - ⚠️ **Interpreter gotcha (maintainer's Mac):** `python3` resolves to a Python 3.6 framework
    build the OS **kills on startup** (exit 137). Use **`/usr/local/bin/python3.9`** (has pandas
    1.3 / numpy 1.26) for every local run/verify. No 3.11+ is installed locally.
  - **Quick UI preview** (faster than a 10k build): run `server.py` but pre-warm the cache with a
    small sim, e.g. set `server._PAYLOAD_CACHE = server.build_payload(1500, 150)` before
    `serve_forever()`. `Handler.do_GET` re-reads `index.html` per request, so HTML/JS edits show on
    refresh; only **data** changes (e.g. a new `knockout.csv` row) need a restart to rebuild the cache.
- `site/` is git-ignored (built by CI). `data.json` is ~1 MB (gzips to ~250 KB).

## Files
- `wc_simulation.py` — **core engine.**
  - `simulate_tournament(...)` — the Monte Carlo loop. Key kwargs: `collect_paths`, `pools`,
    `n_samples`, `knockout`. Returns `(winners, andreas_points, trap_points, timestart[, extra])`.
  - `realized_points(groups, elo, team_dict, fixtures, results, knockout=...)` — deterministic
    points already banked from played games (group + `knockout.csv`). Returns `(andreas, trap, gf, ga, info)`.
  - `load_data()`, `load_knockout(path)`, `_pool_sort_key(...)` (tiebreak key),
    `_order_group(...)` (deterministic group order).
  - `TRAP_OPTIONS` / `ANDREAS_OPTIONS` — participant rosters (edit here to change picks).
- `match_simulator.py` — single match: Elo→Poisson goals, knockout ET/penalties, `update_elo` (K=22).
- `server.py` — stdlib HTTP server. `run_simulation(n, n_samples)`, `build_payload(n_stats, n_samples)`,
  cached `/data.json`. Loads `PRICES`, `POTS`, `KNOCKOUT`, and realized points at import.
  The pure-Python `optimal_andreas` / `optimal_trap` replace the old CPLEX solver.
- `build.py` — writes `site/data.json` + `site/index.html`. Env: `N_STATS` (default 10000;
  **CI sets 100000** in `deploy.yml` for stable odds — build step takes ~2–3 min), `N_SAMPLES` (default **200**).
- `index.html` — single-page UI (inline CSS/JS), fetches `data.json`.
- `data/` — `groups.txt`, `prisliste.txt` (Andreas prices), `trap_seeding.txt` (Trap pots, Danish names),
  `knockout.csv` (hand-maintained KO results), `parsed_wc2026_combinations.txt` (3rd-place bracket pairings).
- `Elo files/` — eloratings TSVs: `2026_World_Cup.tsv` (base Elo), `_fixtures`, `_results` (group stage).
- `solve_point_competitions.py` — **dead code** (needs commercial CPLEX `docplex`); superseded by `server.py`.

## Model
- **Elo seed** per sim = base `2026_World_Cup.tsv` overridden by `current_elo` = each team's latest
  Elo recorded in `results.tsv`. Played group games do NOT call `update_elo` (Elo already from data);
  simulated games do.
- **Host boost:** group stage US/MX/CA +100; **knockout US +75, MX/CA +25** — applied consistently in
  both `simulate_match` and `update_elo` (knockout passes `group_stage=False`).
- **Knockout pinning:** rows in `knockout.csv` are pinned into the sim — the bracket carries the real
  winner forward instead of re-simulating. Matched by unordered team-pair + round. `update_elo` (K=22)
  still runs on pinned games using the real winner. Group stage is complete, so R32 matchups are fixed.
- **Two competitions:**
  - **Trap:** pick 6 teams (2 from pot 1, 1 each pots 2–5), scored with `trap_points`.
    Tiebreakers (official): total → points from pot 5 → pot 4→3→2→1 → goals scored → fewest conceded → lots.
  - **Andreas:** pick 4 teams, total price ≤ 1300, scored with `andreas_points`.
    Tiebreaker: total → **lower total budget** (unofficial, maintainer's own rule — do NOT surface it in
    the UI). Wired via `POOLS["Andreas"]["prices"] = PRICES` → the `prices` arg of `_pool_sort_key`.
- **Scoring:** `trap_points` = win 3 / draw 1 / +0.5 for ≥4-goal blowout / +0.5 for a 9-pt group win;
  KO: FT winner +3, ET both +1 & winner +1, P both +1 & winner +0.5. `andreas_points` = group win/draw 3/1,
  1st/2nd/3rd-that-qualifies 5/3/1, KO round bonuses 4/5/6/7/10 (bronze = 0).
- **`realized_points`** = banked-so-far (deterministic). Group-placement bonuses only for *completed*
  groups; 3rd-place qualifier bonus only once all 12 groups are done.

## `data.json` shape (the payload `build.py`/`/data.json` produce)
`n`, `realized_info` {played (group games only), groups_complete, groups_total, knockout_scored
(KO games that award points, excl. bronze), ko_played (all played KO games incl. bronze — the
header shows `played + ko_played` as "kampe spillet")}, `champion`,
`title_odds`, `andreas_xpts`, `trap_xpts`, `teams` (per team: pot, price, andreas, trap,
andreas_real, trap_real), `rounds` (consensus bracket; each match may have `realized` {a,b,ga,gb,w,decider}),
`stage_reach`, `groups`, `pools` {Trap, Andreas} (each: rows with xpts/real/win/last/exp_rank/pos/teams/real_rank/cost-or-pot,
`optimal` (by xPts), `optimal_real` (by realized pts)), `samples` (≈200 scenarios: {bracket, scores:{pool:{participant:pts}}, order:{pool:[participants in finishing order, winner first — incl. tiebreakers, since `scores` is points-only]}, team:{andreas:{},trap:{}}}),
`win_scenarios` {pool: {participant: one sample-shaped scenario — the first sim that participant finished 1st;
uncapped, so any participant who wins ≥1 of the N sims has one. Powers the "Scenarie hvor X vinder" button}}.

## Frontend (index.html)
- Mode toggle: **📊 Forventet** (10k aggregate) vs **🎲 Ny tilfældig turnering** (one random scenario from
  `samples`; clicking re-rolls). No N input / no Kør button.
- Competition switcher Trap/Andreas. URL `?comp=trap` or `?comp=andreas` locks it (hides the switcher) —
  used to share a fixed view per group. The proper names **Trap/Andreas only appear on this switcher**
  (owner-only, hidden on locked links); they were stripped from all standings/points/notes so a viewer
  who only knows one comp never sees the other's name.
- Tabs: **Vejen til titlen** (bracket; heading is "Den mest sandsynlige vej til titlen" in Forventet,
  "En mulig vej til titlen" in single), **Konkurrence** (pool standings, with Nuværende/Forventet
  sub-toggle; each standings row has a **"🏆 Scenarie hvor X vinder"** button that loads that participant's
  saved `win_scenarios` scenario into the single view and jumps to the bracket — `WIN_FOR` holds the name
  while shown and restyles the path title ("Et scenarie hvor X vinder") / note; the single-scenario standing
  is ordered by the sample's `order` (engine finishing order incl. tiebreakers), not raw points, so a
  points tie is broken the same way the winner was; rows for anyone who never won show a muted note),
  **Forventede holdpoint** (per-team; shows scenario points in single mode), **Runde-odds**
  (stage reach), **Grupper** (group standings), **Regler** (per-comp scoring; `renderRules()` mirrors
  `trap_points`/`andreas_points` exactly — keep the two in sync if scoring ever changes).
- **Eliminated-team muting:** in the pool standings, picked teams that are out of the tournament are
  faded + struck (`.chip.elim`). "Alive" = membership in `d.title_odds` (which server-side already
  excludes group- and KO-eliminated teams). Only applied in aggregate mode, not single scenarios.
- **Numbers are formatted Danish:** `dk()` / `dkf(x,n)` (→ `toLocaleString("da-DK")`) give "," decimals
  and "." thousands (28,0% · 12,50 · 10.000). Use them for any new displayed number; **never** on CSS
  values (bar `width`, rgba alpha keep ".").
- Realized (played) KO games are highlighted **✓ Spillet** with the real score (no %) in both the
  consensus path and single scenarios.
- `TEAM_DA` maps English→Danish names; round names → Danish (`ROUND_DA`);
  deciders → Danish (`DECIDER_DA`: ET→"Forl.", Penalties→"Straffe").
- **Flags** are bundled local SVGs in `flags/` (lipis/flag-icons 4x3, MIT), **not** emoji —
  Windows/Chrome has no country-flag glyph in Segoe UI Emoji and renders emoji flags as raw
  letters ("AR"). `FLAG` still holds the emoji, but only as the source `fl()`/`flagCode()` decode
  to an ISO code (`🇦🇷`→`ar`) → `<img class="flag" src="flags/ar.svg">`. England/Scotland use
  emoji tag-sequences (no ISO code) so `FLAG_SUB` maps them to `gb-eng`/`gb-sct`. `build.py`
  `shutil.copytree`s `flags/`→`site/flags/`; `server.py` serves `/flags/*.svg` for local dev.
  Adding a team: add its `FLAG` emoji **and** drop the matching `flags/<cc>.svg` in.

## `knockout.csv` format
Header `round,home,away,reg,et,decider,winner` must stay first; `#` lines ignored.
`round`: R32/R16/QF/SF/FINAL/BRONZE. `home,away`: English names exactly as in `groups.txt`.
`reg`: 90′ score "h-a". `et`: extra-time goals "h-a" (blank if none). `decider`: FT/ET/P.
`winner`: required (for P the reg+et score is a draw). eloratings logs penalty games as draws and
omits ET/P — that's why this file exists alongside the group `results.tsv`.

## Conventions
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Verify JS changes with `node --check` on the extracted `<script>` (awk the lines between the
  `<script>`/`</script>` tags out to a temp file); rebuild/verify Python with `/usr/local/bin/python3.9`.
- Keep code pandas-3 safe (use `.itertuples`, `dict(zip(...))`, label-based access — no positional Series `[0]`).

## Current state / open items
- Group stage complete (72/72). **Knockout underway** (R16 as of 2026-07-06): `knockout.csv` holds the
  played KO games (16× R32 + R16 rows). Add a row per game as it's played (that's the whole update
  loop), commit, push.
- **Known model characteristic (decided to leave):** the goal model is a bit overconfident vs its own
  Elo basis — single-match favourite win% runs ~3–4 pts above the Elo expectation, worst at large gaps
  (e.g. Argentina ~98% vs Cape Verde in R32; Elo says ~95%). Root cause: `match_simulator.py` maps Elo→
  goals linearly and symmetrically (`λ = 1.35 ± Δ/400`, underdog floored at 0.1), so the goal margin is
  too steep. The single lever is the **`/400` divisor** (≈`/500` would track Elo closely). Maintainer
  chose to keep it — the high numbers are mostly the genuinely large Elo gaps, not a bug.
- CI shows a harmless "Node 20 → 24" deprecation warning (checkout@v4 / setup-python@v5); bump action
  versions in `deploy.yml` eventually. Harmless — does not affect the build or deploy.
- **Euro reuse:** UI wording is tournament-agnostic, but the engine is hardcoded to WC2026's shape
  (12 groups, R32, best-8 thirds, host trio). Reusing for the Euros (24 teams, 6 groups, R16, best-4 thirds)
  is a real refactor — parameterize format + new fixtures/Elo/pot data.
