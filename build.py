#!/usr/bin/env python3
"""Generate the static site for free hosting.

Run this after updating results (group_results / data/knockout.csv):

    python3 build.py

It writes site/data.json (baked N-sim stats + a pool of single-tournament sample
brackets) and site/index.html. Deploy the site/ folder to any static host
(GitHub Pages, Cloudflare Pages, Netlify) — no server, no cost.
"""
import json
import os
import shutil

import server  # importing loads the data and computes realized points

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
N_STATS = int(os.environ.get("N_STATS", "10000"))
N_SAMPLES = int(os.environ.get("N_SAMPLES", "200"))


def main():
    os.makedirs(SITE, exist_ok=True)
    print(f"Simulating {N_STATS:,} tournaments + {N_SAMPLES} sample brackets...")
    payload = server.build_payload(N_STATS, N_SAMPLES)

    out_json = os.path.join(SITE, "data.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(SITE, "index.html"))

    kb = os.path.getsize(out_json) / 1024
    print(f"Wrote site/data.json ({kb:.0f} KB) and site/index.html")
    print(f"Realized so far: {payload['realized_info']}")
    print()
    print("Preview locally:  cd site && python3 -m http.server 8080   ->  http://localhost:8080")
    print("Deploy:           push the site/ folder to GitHub Pages / Cloudflare Pages / Netlify")


if __name__ == "__main__":
    main()
