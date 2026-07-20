"""Backfill data/history.jsonl — the "over tid" timeline for the post-tournament analysis.

For each snapshot date (pre-tournament baseline + every distinct group/knockout match date),
we reconstruct the tournament state AS OF that date purely from the dated data we already have
(no git-replay needed): group results with Y/M/D <= date, and knockout.csv rows with date <= date.
One Monte Carlo run per snapshot (N_HIST sims, default 100k for stable odds) yields, per
participant, that day's win% + expected points; realized_points gives banked points. The first
(baseline) line is the model's day-0 seed (empty results + empty knockout) — its win% is where the
"Vinderchance over tid" curve starts, and its xpts is the pre-tournament projection the Konkurrence
"Forventet" column swaps to once the final is played.

Run:  N_HIST=100000 /usr/local/bin/python3.9 build_history.py   (writes data/history.jsonl)
Smoke: N_HIST=500 build_history.py
Frozen once the tournament is over; regenerate only if a result/pick changes.
"""
import json
import os
import sys

import server as S
import wc_simulation as wc

GROUPS, TPP, ELO, TD, FX, RESULTS = S.DATA
N = int(os.environ.get("N_HIST", "100000"))
BASELINE = "2026-06-10"  # before the first group game (2026-06-11) = day-0 seed, empty state
COMPS = ("Trap", "Andreas")


def _iso(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


# Dated copy of the results df so we can slice "games played on/before date D".
RES = RESULTS.copy()
RES["date"] = [_iso(y, m, d) for y, m, d in zip(RES["Y"], RES["M"], RES["D"])]


def snapshot(date):
    """Return {comp: {date, comp, title_top, part:{name:{win,xpts,real}}}} for state as of `date`."""
    if date == BASELINE:
        res_d = RESULTS.iloc[0:0]        # empty -> base Elo, everything simulated
        ko_d = []
    else:
        res_d = RES[RES["date"] <= date].drop(columns=["date"])
        ko_d = [k for k in S.KNOCKOUT if k["date"] and k["date"] <= date]

    winners, andreas, trap, _, extra = wc.simulate_tournament(
        GROUPS, TPP, ELO, TD, FX, res_d, nsim=N, collect_paths=True,
        pools=S.POOLS, n_samples=0, knockout=ko_d)
    ra, rt, _gf, _ga, _info = wc.realized_points(GROUPS, ELO, TD, FX, res_d, knockout=ko_d)
    real = {"Trap": rt, "Andreas": ra}
    team_xpts = {"Trap": {str(t): v / N for t, v in trap.items()},
                 "Andreas": {str(t): v / N for t, v in andreas.items()}}

    top_team, top_w = max(winners.items(), key=lambda kv: kv[1]) if winners else ("", 0)
    out = {}
    for pn in COMPS:
        parts = extra["pools"][pn]
        realsrc = real[pn]
        pdata = {}
        for name, st in parts.items():
            picks = S.POOLS[pn]["participants"][name]
            pdata[name] = {
                "win": round(st["pos"][0] / N * 100, 2),
                "xpts": round(st["pts"] / N, 2),
                "real": round(sum(realsrc.get(t, 0) for t in picks), 2),
            }
        out[pn] = {
            "date": date, "comp": pn,
            "title_top": {"team": str(top_team), "pct": round(top_w / N * 100, 2)},
            "part": pdata,
        }
    return out, team_xpts, extra


def _fmt_opt(o, is_price):
    """Shape an optimizer result (from server.optimal_*) for baseline.json, incl. pot/price so the
    frontend's tag() renders it exactly like the live optimal card."""
    if not o:
        return None
    teams = [{"team": t, **({"price": S.PRICES.get(t)} if is_price else {"pot": S.POTS.get(t)})}
             for t in o["teams"]]
    d = {"xpts": round(o["xpts"], 2), "teams": teams}
    if is_price:
        d["cost"] = o["cost"]
    return d


# Stage-reach rounds (as named by simulate_tournament) -> short payload keys.
STAGE_KEYS = [("Round of 32", "r32"), ("Round of 16", "r16"), ("Quarterfinals", "qf"),
              ("Semifinals", "sf"), ("Final", "final"), ("Champion", "champ")]


def write_baseline(snap, team_xpts, extra):
    """The rich day-0 (pre-tournament) snapshot the post-final views read: per-team xPoints, the
    optimal squad by those xPoints, each participant's pre-tournament win% + xPoints, and — for the
    Modellen tab — every team's pre-tournament probability of reaching each knockout stage."""
    sr = extra.get("stage_reach", {})
    stage_reach = {str(t): {key: round(d.get(rname, 0) / N * 100, 2) for rname, key in STAGE_KEYS}
                   for t, d in sr.items()}
    baseline = {
        "team_xpts": {c: {t: round(v, 3) for t, v in team_xpts[c].items()} for c in COMPS},
        "optimal": {"Trap": _fmt_opt(S.optimal_trap(team_xpts["Trap"]), False),
                    "Andreas": _fmt_opt(S.optimal_andreas(team_xpts["Andreas"]), True)},
        "part": {c: {nm: {"win": p["win"], "xpts": p["xpts"]} for nm, p in snap[c]["part"].items()}
                 for c in COMPS},
        "stage_reach": stage_reach,   # {team: {r32,r16,qf,sf,final,champ} pre-tournament %}
    }
    path = os.path.join(S.HERE, "data", "baseline.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=0)
    print(f"Wrote {path} (pre-tournament baseline)", flush=True)


def main():
    # BASELINE_ONLY: regenerate just data/baseline.json (one sim) without touching history.jsonl —
    # used when only the day-0 artifact's shape changed (e.g. adding stage_reach for the Modellen tab).
    if os.environ.get("BASELINE_ONLY"):
        print(f"Baseline-only: 1 snapshot x {N} sims -> data/baseline.json", flush=True)
        snap, team_xpts, extra = snapshot(BASELINE)
        write_baseline(snap, team_xpts, extra)
        return

    group_dates = set(RES["date"])
    ko_dates = {k["date"] for k in S.KNOCKOUT if k["date"]}
    dates = [BASELINE] + sorted(group_dates | ko_dates)
    print(f"Building history: {len(dates)} snapshots x {N} sims -> data/history.jsonl", flush=True)

    lines = []
    for i, d in enumerate(dates, 1):
        snap, team_xpts, extra = snapshot(d)
        if d == BASELINE:
            write_baseline(snap, team_xpts, extra)   # the rich day-0 artifact for the post-final views
        for pn in COMPS:
            lines.append(json.dumps(snap[pn], ensure_ascii=False))
        top = snap["Trap"]["title_top"]
        print(f"  [{i}/{len(dates)}] {d}  leader={top['team']} {top['pct']}%", flush=True)

    out_path = os.path.join(S.HERE, "data", "history.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {len(lines)} lines to {out_path}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
