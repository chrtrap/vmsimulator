"""Tiny stdlib HTTP server for the World Cup simulator front-end.

No third-party web deps (only pandas/numpy, already needed by the sim).
Run:  python3 server.py   ->  open http://localhost:8000
"""
import itertools
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import wc_simulation as wc

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))
MAX_N = 50000  # hard cap so the browser request can't hang forever

# Rounds in display order (Third Place shown last/aside).
ROUND_ORDER = ["Round of 32", "Round of 16", "Quarterfinals",
               "Semifinals", "Final", "Third Place Match"]

# Stage-reach columns: round name -> short key for the API.
STAGE_KEYS = [("Round of 32", "ko"), ("Round of 16", "r16"), ("Quarterfinals", "qf"),
              ("Semifinals", "sf"), ("Final", "final"), ("Champion", "champ")]

# Bracket wiring: each knockout slot -> the two slots whose winners meet there
# (mirrors r16_matches/qf_matches/... in wc_simulation.py). R32 slots (73-88) are
# roots with fixed matchups; the consensus bracket propagates winners up this tree.
SLOT_FEEDERS = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100),
    104: (101, 102),
}

# The two fantasy competitions and how each is scored.
POOLS = {
    "Trap":    {"metric": "trap",    "participants": wc.TRAP_OPTIONS},
    "Andreas": {"metric": "andreas", "participants": wc.ANDREAS_OPTIONS},
}

print("Loading data...")
DATA = wc.load_data()  # (groups, third_place_pairings, elo_dict, team_dict, fixtures, results)

# --- Fantasy pool data: price list (Andreas) and pot seeding (Trap) ---
# Map the Danish team names in trap_seeding.txt to the sim's English names.
DANISH_TO_ENGLISH = {
    "Spanien": "Spain", "Frankrig": "France", "England": "England", "Brasilien": "Brazil",
    "Argentina": "Argentina", "Portugal": "Portugal", "Tyskland": "Germany", "Holland": "Netherlands",
    "Norge": "Norway", "Belgien": "Belgium", "Colombia": "Colombia", "Japan": "Japan",
    "Marokko": "Morocco", "USA": "United States", "Uruguay": "Uruguay", "Kroatien": "Croatia",
    "Mexico": "Mexico", "Schweiz": "Switzerland", "Tyrkiet": "Turkey", "Senegal": "Senegal",
    "Ecuador": "Ecuador", "Sverige": "Sweden", "Canada": "Canada", "Østrig": "Austria",
    "Paraguay": "Paraguay", "Skotland": "Scotland", "Bosnien-Hercegovina": "Bosnia and Herzegovina",
    "Egypten": "Egypt", "Elfenbenskysten": "Ivory Coast", "Tjekkiet": "Czechia", "Ghana": "Ghana",
    "Algeriet": "Algeria", "Australien": "Australia", "Sydkorea": "South Korea", "Iran": "Iran",
    "Tunesien": "Tunisia", "DR Congo": "DR Congo", "Qatar": "Qatar", "Saudi-Arabien": "Saudi Arabia",
    "Sydafrika": "South Africa", "Panama": "Panama", "New Zealand": "New Zealand", "Irak": "Iraq",
    "Usbekistan": "Uzbekistan", "Kap Verde": "Cape Verde", "Curacao": "Curaçao", "Curaçao": "Curaçao",
    "Jordan": "Jordan", "Haiti": "Haiti",
}
PRICE_NAME_FIX = {"USA": "United States", "Curacao": "Curaçao", "The Netherlands": "Netherlands"}
TRAP_REQ = {1: 2, 2: 1, 3: 1, 4: 1, 5: 1}   # Trap: pick 6 = 2 from pot1, 1 each pots 2-5
ANDREAS_BUDGET, ANDREAS_K = 1300, 4          # Andreas: pick 4, total price <= 1300


def load_prices(path):
    prices = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2 or not parts[-1].isdigit():
                continue
            name = " ".join(parts[:-1])
            prices[PRICE_NAME_FIX.get(name, name)] = int(parts[-1])
    return prices


def load_pots(path):
    pots, cur = {}, None
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                cur = int(s)
            else:
                pots[DANISH_TO_ENGLISH.get(s, s)] = cur
    return pots


PRICES = load_prices(os.path.join(HERE, "data", "prisliste.txt"))
POTS = load_pots(os.path.join(HERE, "data", "trap_seeding.txt"))
POOLS["Trap"]["pots"] = POTS   # enables the official Trap tiebreakers in the simulation
_all_teams = [str(t) for g in DATA[0] for t in g]
_miss_p = [t for t in _all_teams if t not in PRICES]
_miss_q = [t for t in _all_teams if t not in POTS]
if _miss_p:
    print("WARN: no price for:", _miss_p)
if _miss_q:
    print("WARN: no pot for:", _miss_q)
print(f"Loaded {len(PRICES)} prices, {len(POTS)} pots.")

# Realized points: deterministic, banked from matches actually played so far.
KNOCKOUT = wc.load_knockout(os.path.join(HERE, "data", "knockout.csv"))
REAL_A, REAL_T, REAL_GF, REAL_GA, REAL_INFO = wc.realized_points(
    DATA[0], DATA[2], DATA[3], DATA[4], DATA[5], knockout=KNOCKOUT)
print(f"Realized points so far: {REAL_INFO}. Ready.")


def optimal_andreas(xpts):
    """Best 4 teams maximising xPts with total price <= budget (brute force)."""
    teams = [t for t in PRICES if t in xpts]
    best = None
    for combo in itertools.combinations(teams, ANDREAS_K):
        cost = sum(PRICES[t] for t in combo)
        if cost <= ANDREAS_BUDGET:
            val = sum(xpts[t] for t in combo)
            if best is None or val > best["xpts"]:
                best = {"teams": list(combo), "xpts": val, "cost": cost}
    return best


def optimal_trap(xpts):
    """No budget, only pot quotas -> just take the highest-xPts team(s) per pot."""
    by_pot = {p: [] for p in TRAP_REQ}
    for t, p in POTS.items():
        if t in xpts and p in by_pot:
            by_pot[p].append(t)
    for p in by_pot:
        by_pot[p].sort(key=lambda t: xpts[t], reverse=True)
    pick = by_pot[1][:2] + [by_pot[2][0], by_pot[3][0], by_pot[4][0], by_pot[5][0]]
    return {"teams": pick, "xpts": sum(xpts[t] for t in pick)}


def run_simulation(n, n_samples=0):
    groups, tpp, elo, td, fx, res = DATA
    t0 = time.time()
    winners, andreas, trap, _, extra = wc.simulate_tournament(
        groups, tpp, elo, td, fx, res, nsim=n, collect_paths=True, pools=POOLS,
        n_samples=n_samples, knockout=KNOCKOUT)
    elapsed = time.time() - t0
    paths = extra["paths"]

    def odds(d, key):
        rows = [{"team": str(k),
                 key: round(float(v) / n, 3) if key == "xpts" else round(float(v) / n * 100, 2)}
                for k, v in d.items()]
        return sorted(rows, key=lambda r: r[key], reverse=True)

    # Title odds over every team STILL IN the competition — not just those that won a
    # sim, but excluding teams already eliminated. "Alive" = reachable in the knockout
    # stage at all (present in stage_reach; group-eliminated teams never are) and not the
    # loser of an already-played knockout game. This keeps long-shot survivors such as
    # Cape Verde on the list (pct 0.0, i.e. "<1/n") while dropping knocked-out teams.
    ko_losers = {ko["home"] if ko["winner"] == ko["away"] else ko["away"] for ko in KNOCKOUT}
    alive = [t for t in extra["stage_reach"] if t not in ko_losers]
    title_odds = sorted(
        ({"team": str(t), "pct": round(winners.get(t, 0) / n * 100, 2)} for t in alive),
        key=lambda r: (-r["pct"], r["team"]),
    )
    andreas_xpts = odds(andreas, "xpts")
    trap_xpts = odds(trap, "xpts")

    # Most likely path: per knockout slot, the favourite + win%.
    slot_meta, slot_winner, slot_matchup = paths["slot_meta"], paths["slot_winner"], paths["slot_matchup"]
    # Played knockout games keyed by (team-pair, round) -> real result, to mark them
    # as realized (shown with the actual score, no percentage) in the most-likely path.
    _PHASE = {"R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinals",
              "SF": "Semifinals", "FINAL": "Final", "BRONZE": "Third Place Match"}
    _DEC = {"P": "Penalties", "ET": "ET", "FT": "FT"}
    ko_real = {}
    for ko in KNOCKOUT:
        ph = _PHASE.get(ko["round"])
        if ph and ko["home"] in PRICES and ko["away"] in PRICES:
            ko_real[(frozenset((ko["home"], ko["away"])), ph)] = {
                "a": ko["home"], "b": ko["away"],
                "ga": ko["reg"][0] + ko["et"][0], "gb": ko["reg"][1] + ko["et"][1],
                "w": ko["winner"], "decider": _DEC.get(ko["decider"], "FT"),
            }

    # Build ONE internally-consistent consensus bracket by propagating each slot's
    # most-likely winner forward. Aggregating every slot independently (the old way)
    # produced incoherent brackets: a slot's header matchup could differ from its own
    # two rows, the same pair could appear in two rounds it can't span (e.g. Spain vs
    # Portugal in both R16 and QF), and a slot's favourite need not be who shows up in
    # the next round. Here each round's matchup is the previous round's consensus winners.
    def _mc_pair(num):  # most-common (a, b) matchup recorded at a slot
        mu = slot_matchup.get(num, {})
        if not mu:
            return ("", "")
        parts = max(mu.items(), key=lambda kv: kv[1])[0].split(" vs ")
        return (parts[0], parts[1]) if len(parts) == 2 else ("", "")

    cons_pair = {}   # slot num -> (a, b) the consensus bracket shows there
    cons_win = {}    # slot num -> winner carried forward to the next round
    for num in sorted(slot_meta):           # ascending => R32 roots first, then each round
        if num in SLOT_FEEDERS:             # matchup = winners of the two feeding slots
            f1, f2 = SLOT_FEEDERS[num]
            a, b = cons_win.get(f1, ""), cons_win.get(f2, "")
        else:                               # R32 root / consolation: real (fixed) matchup
            a, b = _mc_pair(num)
        cons_pair[num] = (a, b)
        wins = slot_winner.get(num, {})
        cons_win[num] = a if wins.get(a, 0) >= wins.get(b, 0) else b

    rounds = []
    for rname in ROUND_ORDER:
        matches = []
        for num in sorted(k for k, r in slot_meta.items() if r == rname):
            wins = slot_winner.get(num, {})
            total = sum(wins.values()) or 1
            a, b = cons_pair[num]
            first, second = (a, b) if cons_win[num] == a else (b, a)  # favourite first
            mu = slot_matchup.get(num, {})
            mu_total = sum(mu.values()) or 1
            pair = {a, b}                   # probability THIS exact pairing actually occurs
            mu_count = sum(c for k, c in mu.items() if set(k.split(" vs ")) == pair)
            realized = ko_real.get((frozenset((a, b)), rname)) if a and b else None
            matches.append({
                "num": num,
                "fav": first,
                "fav_pct": round(wins.get(first, 0) / total * 100, 1),
                "matchup": f"{first} vs {second}" if first and second else "",
                "matchup_pct": round(mu_count / mu_total * 100, 1),
                "winners": [{"team": t, "pct": round(wins.get(t, 0) / total * 100, 1)}
                            for t in (first, second) if t],
                "realized": realized,
            })
        if matches:
            rounds.append({"name": rname, "matches": matches})

    # Stage-reach: how far each team goes.
    sr = extra["stage_reach"]
    stage_reach = []
    for team, d in sr.items():
        row = {"team": team}
        for rname, key in STAGE_KEYS:
            row[key] = round(d.get(rname, 0) / n * 100, 1)
        stage_reach.append(row)
    stage_reach.sort(key=lambda r: (r["champ"], r["final"], r["sf"], r["qf"]), reverse=True)

    # Group standings (mostly fixed now; only Group J still varies).
    gp, ga = extra["group_pos"], extra["group_adv"]
    group_tables = []
    for gi, group in enumerate(groups):
        teams = []
        for team in group:
            team = str(team)
            pos = gp.get(team, [0, 0, 0, 0])
            teams.append({
                "team": team,
                "adv": round(ga.get(team, 0) / n * 100, 1),
                "pos": [round(c / n * 100, 1) for c in pos],
            })
        teams.sort(key=lambda t: (t["adv"], t["pos"][0]), reverse=True)
        group_tables.append({"letter": chr(65 + gi), "teams": teams})

    # Per-competition standings (+ prices/pots, squad validity, optimal squad).
    ax = {r["team"]: r["xpts"] for r in andreas_xpts}
    tx = {r["team"]: r["xpts"] for r in trap_xpts}
    team_rows = [{"team": t, "pot": POTS.get(t), "price": PRICES.get(t),
                  "andreas": round(ax[t], 2), "trap": round(tx[t], 2),
                  "andreas_real": round(REAL_A.get(t, 0), 2), "trap_real": round(REAL_T.get(t, 0), 2)}
                 for t in ax]
    pools_out = {}
    for pn, parts in extra["pools"].items():
        is_price = POOLS[pn]["metric"] == "andreas"
        xp = ax if is_price else tx
        real_src = REAL_A if is_price else REAL_T
        rows = []
        for name, st in parts.items():
            tot = sum(st["pos"]) or 1
            exp_rank = sum((i + 1) * c for i, c in enumerate(st["pos"])) / tot
            picks = POOLS[pn]["participants"][name]
            row = {
                "name": name,
                "xpts": round(st["pts"] / n, 2),
                "real": round(sum(real_src.get(t, 0) for t in picks), 2),
                "win": round(st["pos"][0] / n * 100, 1),
                "last": round(st["pos"][-1] / n * 100, 1),
                "exp_rank": round(exp_rank, 2),
                "pos": [round(c / n * 100, 1) for c in st["pos"]],
            }
            if is_price:
                row["teams"] = [{"team": t, "price": PRICES.get(t)} for t in picks]
                row["cost"] = sum(PRICES.get(t, 0) for t in picks)
                row["valid"] = len(picks) == ANDREAS_K and row["cost"] <= ANDREAS_BUDGET
            else:
                row["teams"] = [{"team": t, "pot": POTS.get(t)} for t in picks]
                mix = {}
                for t in picks:
                    mix[POTS.get(t)] = mix.get(POTS.get(t), 0) + 1
                row["valid"] = len(picks) == 6 and all(mix.get(p, 0) == c for p, c in TRAP_REQ.items())
            rows.append(row)
        rows.sort(key=lambda r: r["xpts"], reverse=True)

        # Current (realized) standing order, using the official tiebreakers (Trap only; Andreas by points).
        pots_for = None if is_price else POTS
        rkey = lambda nm: wc._pool_sort_key(POOLS[pn]["participants"][nm], real_src, pots_for, REAL_GF, REAL_GA)
        order_names = sorted([r["name"] for r in rows], key=rkey, reverse=True)
        rank_of = {nm: i + 1 for i, nm in enumerate(order_names)}
        for r in rows:
            r["real_rank"] = rank_of[r["name"]]

        opt_fn = optimal_andreas if is_price else optimal_trap

        def fmt(o):  # shape an optimizer result for the API (None-safe)
            if not o:
                return None
            teams = [{"team": t, **({"price": PRICES.get(t)} if is_price else {"pot": POTS.get(t)})}
                     for t in o["teams"]]
            d = {"xpts": round(o["xpts"], 2), "teams": teams}
            if is_price:
                d["cost"] = o["cost"]
            return d

        pools_out[pn] = {
            "size": len(rows),
            "type": "price" if is_price else "pot",
            "budget": ANDREAS_BUDGET if is_price else None,
            "optimal": fmt(opt_fn(xp)),            # best squad by expected points
            "optimal_real": fmt(opt_fn(real_src)), # best squad by realized points so far
            "rows": rows,
        }

    # Head-to-head: per pool, P(row participant finishes above column participant), over all sims.
    h2h = {}
    for pn, hd in (extra.get("h2h") or {}).items():
        names, mat = hd["names"], hd["mat"]
        h2h[pn] = {
            "names": names,
            "pct": [[round(mat[i][j] / n * 100, 1) for j in range(len(names))]
                    for i in range(len(names))],
        }

    return {
        "n": n,
        "elapsed": round(elapsed, 2),
        "realized_info": REAL_INFO,
        "champion": title_odds[0] if title_odds else None,
        "title_odds": title_odds,
        "andreas_xpts": andreas_xpts,
        "trap_xpts": trap_xpts,
        "teams": team_rows,
        "rounds": rounds,
        "stage_reach": stage_reach,
        "groups": group_tables,
        "pools": pools_out,
        "h2h": h2h,
        # Scenarios drawn from THIS run: {bracket, scores:{pool:{participant:pts}}}.
        "samples": extra.get("samples", []),
    }


def build_payload(n_stats=10000, n_samples=300):
    """Full static payload: N-sim stats + a pool of scenarios sampled from the same run.
    Served live at /data.json and written to disk by build.py."""
    return run_simulation(n_stats, n_samples)


_PAYLOAD_CACHE = None


def cached_payload():
    global _PAYLOAD_CACHE
    if _PAYLOAD_CACHE is None:
        _PAYLOAD_CACHE = build_payload()
    return _PAYLOAD_CACHE


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if parsed.path == "/data.json":   # same shape build.py writes to disk (cached)
            try:
                return self._send(200, json.dumps(cached_payload()), "application/json")
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._send(500, json.dumps({"error": str(e)}), "application/json")
        if parsed.path == "/api/simulate":
            qs = parse_qs(parsed.query)
            try:
                n = int(qs.get("n", ["1000"])[0])
            except ValueError:
                return self._send(400, json.dumps({"error": "n must be an integer"}), "application/json")
            n = max(1, min(n, MAX_N))
            try:
                result = run_simulation(n)
            except Exception as e:  # surface sim errors to the UI instead of a blank 500
                import traceback
                traceback.print_exc()
                return self._send(500, json.dumps({"error": str(e)}), "application/json")
            return self._send(200, json.dumps(result), "application/json")
        return self._send(404, json.dumps({"error": "not found"}), "application/json")

    def log_message(self, fmt, *args):  # quieter console
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
