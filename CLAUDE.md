# vmsimulator — project context

World Cup 2026 Monte Carlo simulator + fantasy-pool tracker for two friend competitions
("Trap" and "Andreas"). Static site, deployed free to GitHub Pages. UI is in **Danish**;
team names are stored internally in **English** and translated for display.

## Deploy & run
- **Repo:** github.com/chrtrap/vmsimulator (branch `main`). **Live:** https://chrtrap.github.io/vmsimulator/
- **CI/CD:** `.github/workflows/deploy.yml` runs on every push to `main` → installs `pandas numpy`
  → runs `build.py` → deploys `site/` to GitHub Pages. Free (public repo). No secrets.
- **Update loop:** edit `data/knockout.csv` (and/or refresh `Elo files/`), commit, push → ~1 min → live.
- **Local dev:** needs pandas+numpy (any Python ≥3.11; code is pandas-3 compatible).
  - `python3 server.py` → http://localhost:8000 (serves `index.html` + a live, cached `/data.json`).
  - or `python3 build.py` then `cd site && python3 -m http.server 8080`.
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
- `build.py` — writes `site/data.json` + `site/index.html`. Env: `N_STATS` (default 10000),
  `N_SAMPLES` (default **200**).
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
- **Scoring:** `trap_points` = win 3 / draw 1 / +0.5 for ≥4-goal blowout / +0.5 for a 9-pt group win;
  KO: FT winner +3, ET both +1 & winner +1, P both +1 & winner +0.5. `andreas_points` = group win/draw 3/1,
  1st/2nd/3rd-that-qualifies 5/3/1, KO round bonuses 4/5/6/7/10 (bronze = 0).
- **`realized_points`** = banked-so-far (deterministic). Group-placement bonuses only for *completed*
  groups; 3rd-place qualifier bonus only once all 12 groups are done.

## `data.json` shape (the payload `build.py`/`/data.json` produce)
`n`, `realized_info` {played, groups_complete, groups_total, knockout_scored}, `champion`,
`title_odds`, `andreas_xpts`, `trap_xpts`, `teams` (per team: pot, price, andreas, trap,
andreas_real, trap_real), `rounds` (consensus bracket; each match may have `realized` {a,b,ga,gb,w,decider}),
`stage_reach`, `groups`, `pools` {Trap, Andreas} (each: rows with xpts/real/win/last/exp_rank/pos/teams/real_rank/cost-or-pot,
`optimal` (by xPts), `optimal_real` (by realized pts)), `samples` (≈200 scenarios: {bracket, scores:{pool:{participant:pts}}, team:{andreas:{},trap:{}}}).

## Frontend (index.html)
- Mode toggle: **📊 Forventet** (10k aggregate) vs **🎲 Ny tilfældig turnering** (one random scenario from
  `samples`; clicking re-rolls). No N input / no Kør button.
- Competition switcher Trap/Andreas. URL `?comp=trap` or `?comp=andreas` locks it (hides the switcher) —
  used to share a fixed view per group.
- Tabs: **Mest sandsynlige vej** (bracket), **Konkurrence** (pool standings, with Nuværende/Forventet
  sub-toggle), **Hold-xPoint** (per-team; shows scenario points in single mode), **Runde-odds** (stage reach),
  **Grupper** (group standings).
- Realized (played) KO games are highlighted **✓ Spillet** with the real score (no %) in both the
  consensus path and single scenarios.
- `TEAM_DA` maps English→Danish names; `FLAG` maps team→emoji; round names → Danish (`ROUND_DA`);
  deciders → Danish (`DECIDER_DA`: ET→"Forl.", Penalties→"Straffe").

## `knockout.csv` format
Header `round,home,away,reg,et,decider,winner` must stay first; `#` lines ignored.
`round`: R32/R16/QF/SF/FINAL/BRONZE. `home,away`: English names exactly as in `groups.txt`.
`reg`: 90′ score "h-a". `et`: extra-time goals "h-a" (blank if none). `decider`: FT/ET/P.
`winner`: required (for P the reg+et score is a draw). eloratings logs penalty games as draws and
omits ET/P — that's why this file exists alongside the group `results.tsv`.

## Conventions
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Verify JS changes with `node --check` on the extracted `<script>`; rebuild with `build.py` to confirm.
- Keep code pandas-3 safe (use `.itertuples`, `dict(zip(...))`, label-based access — no positional Series `[0]`).

## Current state / open items
- Group stage complete (72/72). `knockout.csv` is empty (the Mexico–Ecuador row was a removed test).
- CI shows a harmless "Node 20 → 24" deprecation warning; bump action versions in `deploy.yml` eventually.
- **Euro reuse:** UI wording is tournament-agnostic, but the engine is hardcoded to WC2026's shape
  (12 groups, R32, best-8 thirds, host trio). Reusing for the Euros (24 teams, 6 groups, R16, best-4 thirds)
  is a real refactor — parameterize format + new fixtures/Elo/pot data.
