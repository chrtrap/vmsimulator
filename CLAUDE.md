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
  - `simulate_tournament` also returns (in `extra`, when `pools`) `andreas_sq`/`trap_sq` = Σ of each
    team's per-sim points² — used only to derive per-team std dev for the boom/bust view.
- `match_simulator.py` — single match: Elo→Poisson goals, knockout ET/penalties, `update_elo` (K=22).
- `server.py` — stdlib HTTP server. `run_simulation(n, n_samples)`, `build_payload(n_stats, n_samples)`,
  cached `/data.json`. Loads `PRICES`, `POTS`, `KNOCKOUT`, realized points, **`HISTORY`** (data/history.jsonl),
  **`BASELINE`** (data/baseline.json), and **`TOURNAMENT_OVER`** at import; also computes **`actual_reach`**
  (per-team furthest stage index) in the payload. The pure-Python `optimal_andreas` / `optimal_trap` replace
  the old CPLEX solver.
- `build.py` — writes `site/data.json` + `site/index.html`. Env: `N_STATS` (default 10000;
  **CI sets 100000** in `deploy.yml` for stable odds — build step takes ~2–3 min), `N_SAMPLES` (default **200**).
- `build_history.py` — **post-tournament backfill.** Writes `data/history.jsonl` (one 100k Monte-Carlo
  snapshot per match date, reconstructed by *date-filtering* results.tsv + knockout.csv — no git replay) and
  `data/baseline.json` (the rich day-0 snapshot). `N_HIST=100000 build_history.py` for the full run
  (~40 min); `BASELINE_ONLY=1 N_HIST=100000 build_history.py` regenerates just baseline.json (~2.5 min).
  Frozen once the tournament is over; rerun only if a result or pick changes. See "Post-tournament analysis".
- `index.html` — single-page UI (inline CSS/JS), fetches `data.json`.
- `data/` — `groups.txt`, `prisliste.txt` (Andreas prices), `trap_seeding.txt` (Trap pots, Danish names),
  `knockout.csv` (hand-maintained KO results), `parsed_wc2026_combinations.txt` (3rd-place bracket pairings),
  **`history.jsonl`** + **`baseline.json`** (built by `build_history.py`; committed, powers the retrospective).
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
    *Internally the pot is `pot` (1–5); the **UI displays it in Danish as "Lag" / L1–L5** ("seedningslag"
    spelled out in the Regler/notes prose) — Trap-only, since Andreas is priced not seeded.*
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
`stage_reach`, `groups`, `group_results`/`knockout_results` (played games, dated — `knockout_results`
per game: {round (full phase name), home, away, gh, ga (final score incl. ET), decider, winner, date}),
`final_date` (date of the not-yet-played final, read from the commented `# FINAL,…,date` placeholder
by `scheduled_final_date()` — powers the predicted-final row in the Knockout list),
`pools` {Trap, Andreas} (each: rows with xpts/real/win/last/exp_rank/pos/teams/real_rank/cost-or-pot,
`optimal` (by xPts), `optimal_real` (by realized pts)), `samples` (≈200 scenarios: {bracket, scores:{pool:{participant:pts}}, order:{pool:[participants in finishing order, winner first — incl. tiebreakers, since `scores` is points-only]}, team:{andreas:{},trap:{}}}),
`win_scenarios` {pool: {participant: one sample-shaped scenario — the first sim that participant finished 1st;
uncapped, so any participant who wins ≥1 of the N sims has one. Powers the "Scenarie hvor X vinder" button}}.
Post-tournament additions: **`tournament_over`** (bool; true once a FINAL row is pinned — gates all the
retrospective UI), **`history`** {comp: [dated snapshots {date, comp, title_top, part:{name:{win,xpts,real}}}]}
(from history.jsonl, powers "Udvikling"), **`baseline`** (from baseline.json: `team_xpts`, `team_std`,
`optimal`, `part:{comp:{name:{win,xpts}}}`, `stage_reach:{team:{r32,r16,qf,sf,final,champ}%}` — powers the
pre-tournament swaps + the Modellen tab), **`actual_reach`** {team: furthest stage index 0 group…6 champion}.

## Frontend (index.html)
- Mode toggle: **📊 Forventet** (10k aggregate) vs **🎲 Ny tilfældig turnering** (one random scenario from
  `samples`; clicking re-rolls). No N input / no Kør button.
- **Scenario-mode theming:** single mode adds `body.scenario`, which recolours the whole UI green→**violet**
  ("what-if", not the expected outcome) and shows a sticky banner (`.scenbar`, with a "← Vis forventet"
  shortcut). Driven by CSS vars overridden on `body.scenario` (`--accent/--accent2/--accentink/--tint/
  --accentrgb/--champg*`) — so any new accent-coloured element should use these tokens, not hardcoded
  greens, to flip automatically. Played (`.match.real` ✓ Spillet) games intentionally stay green in both
  modes (real result vs simulated).
- Competition switcher Trap/Andreas. URL `?comp=trap` or `?comp=andreas` locks it (hides the switcher) —
  used to share a fixed view per group. The proper names **Trap/Andreas only appear on this switcher**
  (owner-only, hidden on locked links); they were stripped from all standings/points/notes so a viewer
  who only knows one comp never sees the other's name.
- Tabs: **Knockout** (was "Vejen til finalen"; a **Turneringstræ/Resultater** sub-toggle (`.kview`,
  state `KO_VIEW`, default `tree`) — the bracket tree vs a dated list of played KO games grouped by
  round, rendered from the `knockout_results` payload by `renderKnockoutResults()` in the same row
  format as the group Resultater (fixed-width `.kdec` slot per row keeps columns aligned whether or
  not a Forl./Straffe decider tag shows). Until the final is played, the list appends a **predicted
  final** row (finalists + win% from the consensus Final slot's `winners`, shown as a split
  probability bar `.probbar`, dated by `final_date`; the right slot shows the matchup probability
  `matchup_pct` only when the pairing isn't yet certain (<99.5%, e.g. before the semis) — nothing for
  a locked final). Tree heading is "Den mest sandsynlige vej til finalen" in Forventet,
  "En mulig vej til finalen" in single. Connectors only (re)draw while the tree sub-view is visible),
  **Konkurrence** (pool standings, with Nuværende/Forventet
  sub-toggle; each standings row has a **"🏆 Scenarie hvor X vinder"** button that loads that participant's
  saved `win_scenarios` scenario into the single view and jumps to the bracket — `WIN_FOR` holds the name
  while shown and restyles the path title ("Et scenarie hvor X vinder") / note; the single-scenario standing
  is ordered by the sample's `order` (engine finishing order incl. tiebreakers), not raw points, so a
  points tie is broken the same way the winner was; participants who never topped their pool show no
  win button at all — its absence is the signal they can't win),
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
Header `round,home,away,reg,et,decider,winner,date` must stay first; `#` lines ignored.
`round`: R32/R16/QF/SF/FINAL/BRONZE. `home,away`: English names exactly as in `groups.txt`.
`reg`: 90′ score "h-a". `et`: extra-time goals "h-a" (blank if none). `decider`: FT/ET/P.
`winner`: required (for P the reg+et score is a draw). eloratings logs penalty games as draws and
omits ET/P — that's why this file exists alongside the group `results.tsv`.
`date`: `YYYY-MM-DD` the match was played. `load_knockout` now keeps it on each pin dict (sim logic
ignores it); it powers the `knockout_results` payload list (Knockout → Resultater view) and the
planned "over tid" timeline. Filled with **official eloratings match dates** taken from
`data/2026_World_Cup_latest.tsv` (a dated results dump — used for DATES ONLY, since eloratings omits
ET/P and logs penalties as draws; scores/deciders stay hand-written here). The FINAL (2026-07-19)
sits as a commented placeholder until it's played.
**Keep `date` LAST (or at least not first):** the comment-skip tests the *first* column for a
leading `#`, so putting `date` first makes the `#   R32,Mexico,…,<date>` example rows parse as real
pins (33 instead of 30).

## Conventions
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Verify JS changes with `node --check` on the extracted `<script>` (awk the lines between the
  `<script>`/`</script>` tags out to a temp file); rebuild/verify Python with `/usr/local/bin/python3.9`.
- Keep code pandas-3 safe (use `.itertuples`, `dict(zip(...))`, label-based access — no positional Series `[0]`).

## Current state / open items
- **TOURNAMENT COMPLETE (2026-07-19). Spain beat Argentina in the final (0-0, ET 1-0); England beat
  France 6-4 in the bronze (2026-07-18).** `knockout.csv` holds all 32 KO games incl. bronze + final.
  The site is now a **frozen post-tournament retrospective** — no more per-game updates. If a result or
  pick ever changes, re-run the full `build_history.py` to regenerate history.jsonl + baseline.json, then push.
- **Known model characteristic (kept):** the goal model is a bit overconfident vs its own Elo basis —
  single-match favourite win% runs ~3–4 pts above the Elo expectation. Root cause: `match_simulator.py`
  maps Elo→goals linearly (`λ = 1.35 ± Δ/400`, underdog floored at 0.1). Lever = the **`/400` divisor**
  (≈`/500` tracks Elo closely). The Modellen tab's **calibration plot bore this out but only mildly** (a
  small sag at the top), so the divisor probably does NOT need changing for the Euros.
- CI shows a harmless "Node 20 → 24" deprecation warning; bump action versions in `deploy.yml` eventually.

## Post-tournament analysis (built 2026-07-20 — the retrospective)
Once `tournament_over`, the UI flips from live prediction to retrospective. `body.finished` (toggled in
`render()`) hides the Vinderodds side panel, the 🎲 random-scenario mode, the Slutspilsodds tab, the
sim-count control bar and the "Scenarie hvor X vinder" buttons; the champion banner shows just "Vinder"
(no %), the header `#subtitle` reframes as a retrospective, elim-strikethrough is off.
- **Data pipeline:** `build_history.py` reconstructs each match-date's state by date-filtering results.tsv
  + knockout.csv (NO git replay — both are self-dating), runs one 100k sim/snapshot → `data/history.jsonl`
  (35 daily snapshots, per-participant win%/xpts/realized) + `data/baseline.json` (the day-0 snapshot:
  per-team `team_xpts` + `team_std` + `optimal` squad, per-participant `part` win/xpts, per-team
  `stage_reach`). `server.py` loads both and adds `actual_reach`. Terminology: UI says **"konkurrence"**
  never "pulje".
- **Konkurrence sub-views (finished): Stilling · Udvikling · Analyse · Holdpoint · Regler.**
  - *Stilling* "Point" toggle → **Slutstilling** (final realized) / **Forventninger før turneringen**
    (baseline xPoints; each row shows faktisk slutplacering + pre-tour win%; ★ optimal = the pre-tour
    optimal squad, with its real points + would-be rank). `renderPools`, `baseMode`.
  - *Udvikling* (`renderTrend`/`drawLineChart`) = two hand-rolled inline-SVG line charts (Vinderchance /
    Point over tid) with a group|KO phase divider + a participant filter (legend click, Vis alle/Ryd → head-to-head).
  - *Analyse* (`renderCompAnalysis`) = comp-specific, reacts to Trap/Andreas: "Hvor forudsigelig var
    konkurrencen?" (winner's pre-tour odds · did the favourite win · gap to the realized-optimal) + "Boom
    eller bust" (per-team std-dev risk/reward scatter, **flags as marks**, `varScatter`).
  - *Holdpoint* (`renderTeams`) xPoint column → pre-tournament per-team value (labelled `xPoint*`).
- **Modellen tab (top-level, finished-only, comp-AGNOSTIC, `renderModel`):** how well the Elo model
  predicted the *tournament*. Panels: headline (champion's pre-tour title rank/odds · favourite hit-rate ·
  champion **Brier** score vs a random guess) · Titelfavoritter vs virkeligheden · Træfsikkerhed pr. stadie
  · **Kalibrering** reliability diagram (`calSvg`; all 48 teams × 6 stages binned, predicted vs actual).
  Verdict: **strong** — Spain the #1 favourite won, top-4 favourites all reached the SF, Brier 0.56 vs 0.98
  random, and well-calibrated (mild top-end overconfidence only).

## Reusing for the Euros (~2028) — the roadmap
The retrospective machinery above is driven by payload fields, so it **lights up automatically** once the
data has the right shape. The real work is the ENGINE, which is hardcoded to WC2026's format:
- **Format params (the actual refactor):** WC = 48 teams / 12 groups / R32 / best-8 thirds / host trio
  (US+MX+CA boosts). Euro = **24 teams / 6 groups / R16 / best-4-of-6 thirds / host boost for the host
  nation(s)** — note Euro 2028 = UK & Ireland, i.e. up to 5 host nations, not one. `simulate_tournament`,
  the bracket wiring (`SLOT_FEEDERS` + `_bracket_rows` in server.py) and the 3rd-place pairings table
  (`data/parsed_wc2026_combinations.txt`) all bake in the WC shape. Parameterize group count / advance
  rules / KO round set / host boost.
- **Stage keys** are listed in THREE places for the Modellen/boom-bust views — keep in sync when the KO
  structure changes: `build_history.STAGE_KEYS`, server `_RIDX` + payload actual_reach indices, frontend
  `M_STAGES`. Euro starts at R16 (drop `r32`) and the slot counts change (16/16→16/8/4/2/1).
- **New data to supply:** fresh `Elo files/` (base Elo + fixtures + group results), `groups.txt`,
  `prisliste.txt` + `trap_seeding.txt`, a new 3rd-place pairings table, and the rosters
  (`TRAP_OPTIONS`/`ANDREAS_OPTIONS`). Revisit `trap_points`/`andreas_points` scoring if desired — the
  boom/bust view showed Andreas's advance/eliminate bonuses make it much higher-variance than Trap.
- **Live "over tid" during the Euro (nice-to-have):** have CI append one history.jsonl line per deploy in
  the group stage (not just backfill at the end) → live daily granularity, then the same frozen
  retrospective at the finish. `build_history.py`'s date-filtering already supports this.
- **Decisional takeaways from WC2026 (for picking strategy):** the model was well-calibrated → trust its
  team favourites as the backbone of picks. Andreas is far higher-variance than Trap (avg swing ±6.1 vs
  ±3.5) → in Andreas the "optimal xPoints" squad is a weaker guide and calculated high-ceiling bets pay;
  in Trap the model's projection is a tighter guide.
