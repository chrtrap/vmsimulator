import pandas as pd
import numpy as np
import time
import math
import csv
import match_simulator
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Simulering')))

def load_data():
    script_dir = os.path.dirname(__file__)
    # Function to load and parse the groups from the text file
    def load_groups(filename):
        filename = os.path.join(script_dir, filename)
        with open(filename, 'r') as file:
            lines = file.readlines()

        groups = {}
        current_group = None

        for line in lines:
            line = line.strip()
            if line.startswith("Group"):
                current_group = line.replace(":", "")
                groups[current_group] = []
            elif line:
                position, team = line.split(': ')
                groups[current_group].append(team)

        return groups

    # Load the groups from the file
    groups = load_groups('data/groups.txt')
    
    # np.array of all groups
    groups = np.array(list(groups.values()))

    def load_pairings(filename):
        filename = os.path.join(script_dir, filename)
        pairings = {}
        with open(filename, 'r') as file:
            for line in file:
                groups_str, matchups_str = line.strip().split(": ")
                groups = tuple(map(int, groups_str.strip("()").split(", ")))
                matchups = eval(matchups_str)
                pairings[groups] = matchups
        return pairings

    third_place_pairings = load_pairings(os.path.join(script_dir, "data/parsed_wc2026_combinations.txt"))

    rating = pd.read_table(os.path.join(script_dir, 'Elo files/2026_World_Cup.tsv'), header=None)
    rating = rating[[2,3]]
    rating.columns = ['Name','Elo']
    elo_dict = dict(zip(rating['Name'], rating['Elo']))

    teams = pd.read_table(os.path.join(script_dir, 'Elo files/en.teams.tsv'), header=None,names=['Short','Full'], usecols=[0,1])
    team_dict = dict(zip(teams['Short'], teams['Full']))
    team_dict['Draw'] = 'Draw'


    fixtures = pd.read_table(os.path.join(script_dir, 'Elo files/2026_World_Cup_fixtures.tsv'), header=None)
    fixtures = fixtures[[3,4,5]]
    fixtures.columns = ['HT', 'AT','Tour']
    fixtures = fixtures[fixtures['Tour']=="WC"]

    results = pd.read_table(os.path.join(script_dir, 'Elo files/2026_World_Cup_results.tsv'), header=None)
    results = results[[0,1,2,3,4,5,6,7,10,11]]
    results.columns = ['Y','M','D','HT', 'AT','GH','GA','Tour','H_elo','A_elo']
    results = results[results['Tour']=="WC"]

    return groups, third_place_pairings, elo_dict, team_dict, fixtures, results

#check https://www.researchgate.net/publication/309662241_Mathematical_Model_of_Ranking_Accuracy_and_Popularity_Promotion for elo draws

# --- Fantasy pool participants and their squad selections ---
# TRAP competition: pick 6 teams, scored with trap_points.
TRAP_OPTIONS = {
    'Christian': ['Argentina', 'Spain', 'Netherlands', 'Ecuador', 'Paraguay', 'Bosnia and Herzegovina'],
    'Lone':      ['Argentina', 'England', 'Germany', 'Norway', 'Sweden', 'Bosnia and Herzegovina'],
    'Freja':     ['France', 'England', 'Belgium', 'Austria', 'Sweden', 'New Zealand'],
    'Søren':     ['Brazil', 'Spain', 'Netherlands', 'Turkey', 'Sweden', 'South Africa'],
    'Lauritz':   ['France', 'Spain', 'Germany', 'Austria', 'Ivory Coast', 'Ghana'],
    'Louise':    ['Brazil', 'Spain', 'Germany', 'Turkey', 'Sweden', 'South Africa'],
}
# ANDREAS competition: pick 4 teams, scored with andreas_points.
ANDREAS_OPTIONS = {
    'Fred':                          ['Spain', 'Mexico', 'Switzerland', 'Cape Verde'],
    'Emil':                          ['Argentina', 'Norway', 'Sweden', 'Scotland'],
    'SadoTheShadow':                 ['Brazil', 'Germany', 'Ivory Coast', 'South Africa'],
    'Stefan Winston Bligaard Netopil':['Portugal', 'Turkey', 'Mexico', 'Switzerland'],
    'Manni':                         ['Portugal', 'Netherlands', 'Mexico', 'Egypt'],
    'Rasmus Bundgaard':              ['Brazil', 'Germany', 'Algeria', 'South Africa'],
    'Bjørnen i det blå hus':         ['France', 'Norway', 'Egypt', 'Ivory Coast'],
    'Nicolai Lind Mosbjerg':         ['Spain', 'Switzerland', 'Turkey', 'Saudi Arabia'],
    'Kenneth Sadolin Pedersen':      ['France', 'Morocco', 'Japan', 'South Africa'],
    'Andreas "the master" Simonsen': ['Spain', 'Mexico', 'Ecuador', 'Iran'],
}


def _pool_sort_key(teams, pts_map, pots=None, gf=None, ga=None):
    """Ranking key for a fantasy entry (higher tuple = better placement).

    Trap tiebreakers (official): total points, then points from the selected teams in
    pot 5, then pot 4, 3, 2, 1 (bottom-up), then goals scored, then fewest goals conceded.
    Final rule (drawing of lots) is left to stable ordering. With no `pots` (Andreas),
    only the total is used."""
    score = sum(pts_map.get(t, 0) for t in teams)
    if not pots:
        return (score,)
    by_pot = {}
    for t in teams:
        by_pot[pots.get(t)] = by_pot.get(pots.get(t), 0) + pts_map.get(t, 0)
    key = (score,) + tuple(by_pot.get(p, 0) for p in (5, 4, 3, 2, 1))
    if gf is not None and ga is not None:                  # goals tiebreakers (when available)
        key += (sum(gf.get(t, 0) for t in teams), -sum(ga.get(t, 0) for t in teams))
    return key


def simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures, results, nsim=50000, print_results=False, skip_group_stage=False, collect_paths=False, pools=None, n_samples=0, knockout=None):
    timestart = time.time()
    all_teams = [team for group in groups for team in group]
    points_map = {team: (i,j) for i,group in enumerate(groups) for j,team in enumerate(group)}
    inv_team_dict = {v: k for k, v in team_dict.items()}
    winners = {}
    semi_final_stats = {}
    andreas_points = {t:0 for t in all_teams}
    trap_points = {t:0 for t in all_teams}

    # --- Real results from results.tsv ---
    # played:      scorelines of matches already played -> used as-is, not simulated.
    # current_elo: each team's most recent pre-match Elo recorded in the data. We seed
    #              the sim with these and DON'T call update_elo on played matches, so the
    #              Elo comes from the results data rather than the K-factor approximation.
    played = {}
    current_elo = {}
    for _, r in results.sort_values(['Y', 'M', 'D']).iterrows():  # oldest -> newest
        played[(r['HT'], r['AT'])] = (int(r['GH']), int(r['GA']))
        current_elo[r['HT']] = r['H_elo']   # latest match wins -> most recent Elo
        current_elo[r['AT']] = r['A_elo']

    # Played knockout games (data/knockout.csv) pinned into the simulation: the bracket
    # carries the real winner forward instead of re-simulating. Keyed by unordered team
    # pair, matched by round so a pair is only pinned in its actual round.
    _ko_phase = {'R32': 'Round of 32', 'R16': 'Round of 16', 'QF': 'Quarterfinals',
                 'SF': 'Semifinals', 'FINAL': 'Final', 'BRONZE': 'Third Place Match'}
    _ko_dec = {'P': 'Penalties', 'ET': 'ET', 'FT': 'FT'}
    played_ko = {}
    for ko in (knockout or []):
        h, aw, win = ko['home'], ko['away'], ko['winner']
        if h not in points_map or aw not in points_map or win not in points_map:
            continue
        played_ko[frozenset((h, aw))] = {
            'phase': _ko_phase.get(ko['round']),
            'home': h, 'th': ko['reg'][0] + ko['et'][0], 'ta': ko['reg'][1] + ko['et'][1],
            'winner': win, 'decider': _ko_dec.get(ko['decider'], 'FT'),
        }

    # Aggregators for the "most likely path" view (only filled if collect_paths=True)
    slot_meta = {}       # match_num -> round name
    slot_winner = {}     # match_num -> {team: times_won}
    slot_matchup = {}    # match_num -> {"A vs B": count}
    last_bracket = None  # detailed bracket (with scores) of the final simulation
    stage_reach = {}     # team -> {round/'Champion': count}  (how far a team goes)
    group_pos = {}       # team -> [#1st, #2nd, #3rd, #4th] in its group
    group_adv = {}       # team -> times it advanced to the knockout

    # Per-competition standings: pool -> participant -> {pts, pos:[counts by finish]}
    pool_agg = None
    h2h_agg = None   # pool -> {names, mat}: mat[i][j] = sims where i finished above j
    if pools is not None:
        pool_agg = {pn: {part: {'pts': 0.0, 'pos': [0] * len(pd['participants'])}
                         for part in pd['participants']}
                    for pn, pd in pools.items()}
        h2h_agg = {pn: {'names': list(pd['participants'].keys()),
                        'mat': [[0] * len(pd['participants']) for _ in pd['participants']]}
                   for pn, pd in pools.items()}

    # A subset of full sims kept as "scenarios" for the single-simulation view:
    # each = {bracket: [...matches...], scores: {pool: {participant: points}}}.
    samples = []

    for _ in range (nsim):
        temp_elo_dict = elo_dict.copy()
        temp_elo_dict.update(current_elo)   # seed Elo from results data
        if pools is not None:               # snapshot to measure this sim's points
            snap_a = dict(andreas_points)
            snap_t = dict(trap_points)
        points = np.zeros(np.shape(groups))
        goals_diff = np.zeros(np.shape(groups))  # Tracks overall Goal Difference
        goals_scored = np.zeros(np.shape(groups)) # Tracks overall Goals Scored
        group_matches = {}
        #it_timestart = time.time()
        #group stage
        if skip_group_stage == False: 
            if print_results:
                print('Group stage')
            for idx, fix in enumerate(fixtures.itertuples(index=False, name=None)):
                key, rkey = (fix[0], fix[1]), (fix[1], fix[0])
                if key in played:
                    g_a, g_b = played[key]                 # real result
                    is_played = True
                elif rkey in played:
                    g_b, g_a = played[rkey]                # real result (teams listed reversed)
                    is_played = True
                else:
                    g_a, g_b = match_simulator.simulate_match(fix, temp_elo_dict)
                    is_played = False
                outcome = 'Draw' if g_a == g_b else (fix[0] if g_a > g_b else fix[1])
                # Only evolve Elo for simulated matches; played matches already use the
                # real Elo seeded from the results data above.
                if not is_played:
                    match_simulator.update_elo(outcome, fix, temp_elo_dict)

                # Get the matrix indices for both teams
                idx_team_a = points_map[team_dict[fix[0]]]
                idx_team_b = points_map[team_dict[fix[1]]]

                # Log the exact scoreline for H2H (Step One) lookup later
                group_matches[(fix[0], fix[1])] = (g_a, g_b)
                group_matches[(fix[1], fix[0])] = (g_b, g_a)

                # Update Step Two tracking metrics (Overall GS and GD)
                goals_scored[idx_team_a] += g_a
                goals_scored[idx_team_b] += g_b
                goals_diff[idx_team_a] += g_a - g_b
                goals_diff[idx_team_b] += g_b - g_a

                if outcome == 'Draw':
                    points[idx_team_a] += 1
                    points[idx_team_b] += 1

                    trap_points[team_dict[fix[0]]] += 1
                    trap_points[team_dict[fix[1]]] += 1

                    andreas_points[team_dict[fix[0]]] += 1
                    andreas_points[team_dict[fix[1]]] += 1
                else:
                    points[points_map[team_dict[outcome]]] += 3

                    trap_points[team_dict[outcome]] += 3
                    if abs(g_a - g_b) >= 4:  # Winning by 4+ goals bonus
                        trap_points[team_dict[outcome]] += 0.5

                    andreas_points[team_dict[outcome]] += 3
                if print_results:
                    print(f'{idx+1}. {team_dict[fix[0]]} - {team_dict[fix[1]]}')
                    print(f'Result: {g_a} - {g_b}')
                    print(f'Winner: {team_dict[outcome]}')
                    print()

            #calculate group standings
            standings_list = []
            card_noise_dict = {}  # To track the random noise for each team for debugging/analysis
            for gi, group in enumerate(groups):
                team_tuples = []
                for ti, team_name in enumerate(group):
                    # 1. Fetch overall stats from our parallel matrices
                    t_pts = points[gi, ti]
                    t_gd = goals_diff[gi, ti]
                    t_gs = goals_scored[gi, ti]

                    # 2. STEP ONE: Find any rivals in this specific group tied on points
                    tied_rivals = [
                        r_name
                        for r_idx, r_name in enumerate(group)
                        if points[gi, r_idx] == t_pts and r_name != team_name
                    ]

                    h2h_pts, h2h_gs, h2h_conceded = 0, 0, 0
                    if len(tied_rivals) > 0:
                        # We have a tie! Look up our log for ONLY the matches between the tied teams
                        for rival in tied_rivals:
                            # Find the short name key (reversing your team_dict lookup if fix uses codes)
                            # Assuming fix contains codes like 'US', ensure keys align:
                            fix_key_team = inv_team_dict[team_name]
                            fix_key_rival = inv_team_dict[rival]

                            g_sc, g_con = group_matches[(fix_key_team, fix_key_rival)]
                            h2h_gs += g_sc
                            h2h_conceded += g_con
                            if g_sc > g_con:
                                h2h_pts += 3
                            elif g_sc == g_con:
                                h2h_pts += 1
                    h2h_gd = h2h_gs - h2h_conceded

                    # 3. STEP TWO (Cards/Discipline Noise)
                    # Assumption: weaker Elo teams have a slightly higher penalty
                    t_elo = temp_elo_dict[inv_team_dict[team_name]]
                    elo_weakness = 2000 - t_elo
                    card_noise = -abs(np.random.normal(elo_weakness * 0.001, 0.5))
                    card_noise_dict[team_name] = card_noise

                    # 4. THE ABSOLUTE DEFINITIVE FIFA TUPLE
                    # Python handles sorting tuples from left-to-right automatically
                    sorting_tuple = (
                        t_pts,  # Base: Points
                        h2h_pts,  # Step 1a: H2H Points
                        h2h_gd,  # Step 1b: H2H Goal Difference
                        h2h_gs,  # Step 1c: H2H Goals Scored
                        t_gd,  # Step 2a: Overall Goal Difference
                        t_gs,  # Step 2b: Overall Goals Scored
                        card_noise,  # Step 2c: Team Conduct Score (Noise)
                        t_elo,  # Step 3: Global Ranking Anchor
                    )

                    # Append the positional index (ti) and its math signature
                    team_tuples.append((ti, sorting_tuple))

                # Sort the 4 teams in the group (highest performance values first)
                sorted_group = sorted(team_tuples, key=lambda x: x[1], reverse=True)

                # Extract the sorted positional indices [best, second, third, worst]
                sorted_indices = [item[0] for item in sorted_group]
                standings_list.append(sorted_indices)

            # Convert back to a NumPy array so your existing knock-out index rules work with zero changes!
            standings = np.array(standings_list)

            # --- CALCULATE 8 BEST THIRD PLACE TEAMS ---
            thirds_pool = []
            for gi, group in enumerate(groups):
                # Grab the index of the team that finished 3rd in this group
                ti_third = standings[gi, 2]
                team_name = group[ti_third]

                # Pull their overall performance numbers for the multi-group comparison
                t_pts = points[gi, ti_third]
                t_gd = goals_diff[gi, ti_third]
                t_gs = goals_scored[gi, ti_third]
                card_noise = card_noise_dict[team_name]
                t_elo = temp_elo_dict[inv_team_dict[team_name]]

                # Step One (H2H) is completely blanked out for cross-group comparisons per FIFA rules
                thirds_tuple = (t_pts, t_gd, t_gs, card_noise, t_elo)
                thirds_pool.append((gi, thirds_tuple))

            # Sort the 12 groups based on their 3rd place team's tuple stats (highest first)
            sorted_thirds_ladder = sorted(thirds_pool, key=lambda x: x[1], reverse=True)

            # Extract the group indices of the top 8 advancing teams
            groups_w3q = sorted([item[0] for item in sorted_thirds_ladder[:8]])

            if collect_paths:  # tally group finishing positions + advancement
                for gi, group in enumerate(groups):
                    for pos in range(4):
                        tname = str(group[standings[gi, pos]])
                        group_pos.setdefault(tname, [0, 0, 0, 0])
                        group_pos[tname][pos] += 1
                    adv = [standings[gi, 0], standings[gi, 1]]
                    if gi in groups_w3q:
                        adv.append(standings[gi, 2])
                    for ti in adv:
                        tname = str(group[ti])
                        group_adv[tname] = group_adv.get(tname, 0) + 1

            #give points to first, second and third place
            for gi, ti in enumerate(standings[:,0]): 
                andreas_points[groups[gi,ti]] += 5
                if points[gi,ti] == 9:
                    trap_points[groups[gi,ti]] += 0.5
            for gi, ti in enumerate(standings[:,1]):
                andreas_points[groups[gi,ti]] += 3
            for gi, ti in enumerate(standings[:,2]):
                if gi in groups_w3q:
                    andreas_points[groups[gi,ti]] += 1

            #knockout
            third_place_pairing = third_place_pairings[tuple(groups_w3q)]
            #end of group stage
            if print_results:
                #print group standings inclding GD and 3rd place standings for this simulation
                print('Group Standings:')
                for gi, group in enumerate(groups):
                    print(f'Group {gi+1}:')
                    for pos in range(4):
                        team_name = group[standings[gi, pos]]
                        pts = points[gi, standings[gi, pos]]
                        gd = goals_diff[gi, standings[gi, pos]]
                        gs = goals_scored[gi, standings[gi, pos]]
                        print(f'  {pos+1}. {team_name} - Points: {pts}, GD: {gd}, GS: {gs}')
                    print()
                print('Third Place Rankings:')
                for rank, item in enumerate(sorted_thirds_ladder, start=1):
                    gi = item[0]
                    team_name = groups[gi, standings[gi, 2]]
                    pts = points[gi, standings[gi, 2]]
                    gd = goals_diff[gi, standings[gi, 2]]
                    gs = goals_scored[gi, standings[gi, 2]]
                    print(f'  {rank}. {team_name} (Group {gi+1}) - Points: {pts}, GD: {gd}, GS: {gs}')
                print()



        knockout_results = {}
        sim_bracket = []  # per-simulation log of knockout matches (for collect_paths)
        def run_knockout_round(matches, phase_name, andreas_bonus=5):
            if print_results:
                print(phase_name)
                print()
            losers = []
            for match_num, (team_a, team_b) in matches.items():
                t1 = inv_team_dict[team_a]
                t2 = inv_team_dict[team_b]
                pin = played_ko.get(frozenset((team_a, team_b)))
                if pin and pin['phase'] == phase_name:        # real played result -> pin it
                    outcome = pin['winner']
                    raw_outcome = inv_team_dict[outcome]
                    decider = pin['decider']
                    g_a, g_b = (pin['th'], pin['ta']) if team_a == pin['home'] else (pin['ta'], pin['th'])
                else:
                    raw_outcome, g_a, g_b, decider = match_simulator.simulate_knockout_match((t1, t2), temp_elo_dict)
                    outcome = team_dict[raw_outcome]
                match_simulator.update_elo(raw_outcome, (t1, t2), temp_elo_dict, group_stage=False)
                if print_results:
                    print(f'{match_num}. {team_a} - {team_b}')
                    print(f'Result: {g_a} - {g_b}')
                    print(f'Winner: {outcome} (Decider: {decider})')
                    print()
                if phase_name != "Third Place Match":  # Only award points for the main knockout rounds, not the consolation match
                    if decider == "Penalties":
                        trap_points[team_a] += 1
                        trap_points[team_b] += 1

                        trap_points[outcome] += 0.5
                    elif decider == "ET":
                        trap_points[team_a] += 1
                        trap_points[team_b] += 1

                        trap_points[outcome] += 1
                    else:
                        trap_points[outcome] += 3
                    if abs(g_a - g_b) >= 4:  # Winning by 4+ goals bonus
                        trap_points[outcome] += 0.5

                    if phase_name == "Final":
                        if winners.get(outcome, None) is None:
                            winners[outcome] = 1
                        else:
                            winners[outcome] += 1
                    andreas_points[outcome] += andreas_bonus

                knockout_results[match_num] = outcome
                if collect_paths:
                    sim_bracket.append({
                        'num': match_num, 'round': phase_name,
                        'a': str(team_a), 'b': str(team_b), 'w': str(outcome),
                        'ga': int(g_a), 'gb': int(g_b), 'decider': decider,
                    })
                losers.append(team_b if outcome == team_a else team_a)
            return losers
        
        #FOR WHEN GROUP STAGE IS SKIPPED (hardcoded fallback; normal runs compute these)
        if skip_group_stage:
            third_place_pairing = third_place_pairings[(1,3,4,5,8,9,10,11)]
            standings = np.array([
                # A: Mexico(0) 1st, South Africa(3) 2nd, South Korea(2) 3rd, Czechia(1) 4th
                [0, 3, 2, 1],
                # B: Switzerland(2) 1st, Canada(0) 2nd, Bosnia(1) 3rd, Qatar(3) 4th
                [2, 0, 1, 3],
                # C: Brazil(0) 1st, Morocco(3) 2nd, Scotland(1) 3rd, Haiti(2) 4th
                [0, 3, 1, 2],
                # D: United States(3) 1st, Australia(2) 2nd, Paraguay(0) 3rd, Turkey(1) 4th
                [3, 2, 0, 1],
                # E: Germany(1) 1st, Ivory Coast(2) 2nd, Ecuador(0) 3rd, Curaçao(3) 4th
                [1, 2, 0, 3],
                # F: Netherlands(0) 1st, Japan(2) 2nd, Sweden(1) 3rd, Tunisia(3) 4th
                [0, 2, 1, 3],
                # G: Belgium(0) 1st, Egypt(2) 2nd, Iran(1) 3rd, New Zealand(3) 4th
                [0, 2, 1, 3],
                # H: Spain(0) 1st, Cape Verde(3) 2nd, Uruguay(1) 3rd, Saudi Arabia(2) 4th
                [0, 3, 1, 2],
                # I: France(1) 1st, Norway(0) 2nd, Senegal(2) 3rd, Iraq(3) 4th
                [1, 0, 2, 3],
                # J: Argentina(0) 1st, Austria(1) OR Algeria(2) 2nd — LIVE TODAY
                [0, 1, 2, 3],  # ← provisional: Austria 2nd, Algeria 3rd (Austria had better GD before matchday 3)
                # K: Colombia(0) 1st OR Portugal(1) — LIVE TODAY
                [0, 1, 3, 2],  # ← provisional: Colombia 1st, Portugal 2nd, DR Congo 3rd, Uzbekistan 4th
                # L: England(0) OR Ghana(3) — LIVE TODAY
                [0, 3, 1, 2],  # ← provisional: England 1st, Ghana 2nd, Croatia 3rd, Panama 4th
                ])
        #trap_points = {t:0 for t in all_teams} #load points

        # standings[gi, 0] gives the column index of the winner of group gi
        # groups[gi, standings[gi, 0]] extracts the actual team name string!

        r32_matches = {
            73: (groups[0, standings[0, 1]], groups[1, standings[1, 1]]),     # 2A vs 2B
            74: [groups[4, standings[4, 0]], None],                           # 1E vs 3rd
            75: (groups[5, standings[5, 0]], groups[2, standings[2, 1]]),     # 1F vs 2C
            76: (groups[2, standings[2, 0]], groups[5, standings[5, 1]]),     # 1C vs 2F
            77: [groups[8, standings[8, 0]], None],                           # 1I vs 3rd
            78: (groups[4, standings[4, 1]], groups[8, standings[8, 1]]),     # 2E vs 2I
            79: [groups[0, standings[0, 0]], None],                           # 1A vs 3rd
            80: [groups[11, standings[11, 0]], None],                         # 1L vs 3rd
            81: [groups[3, standings[3, 0]], None],                           # 1D vs 3rd
            82: [groups[6, standings[6, 0]], None],                           # 1G vs 3rd
            83: (groups[10, standings[10, 1]], groups[11, standings[11, 1]]), # 2K vs 2L
            84: (groups[7, standings[7, 0]], groups[9, standings[9, 1]]),     # 1H vs 2J
            85: [groups[1, standings[1, 0]], None],                           # 1B vs 3rd
            86: (groups[9, standings[9, 0]], groups[7, standings[7, 1]]),     # 1J vs 2H
            87: [groups[10, standings[10, 0]], None],                         # 1K vs 3rd
            88: (groups[3, standings[3, 1]], groups[6, standings[6, 1]]),     # 2D vs 2G
        }


        # Fetch the assigned group order for this specific simulation's combination
        assigned_groups = third_place_pairing

        # Assuming assigned_groups is ordered: [1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L]
        # assigned_groups[x][1] gives the group index of the advancing 3rd place team.
        # standings[group_idx, 2] gives their column index within the groups array.
        r32_matches[79][1] = groups[assigned_groups[0][1], standings[assigned_groups[0][1], 2]]  # 1A vs 3rd
        r32_matches[85][1] = groups[assigned_groups[1][1], standings[assigned_groups[1][1], 2]]  # 1B vs 3rd
        r32_matches[81][1] = groups[assigned_groups[2][1], standings[assigned_groups[2][1], 2]]  # 1D vs 3rd
        r32_matches[74][1] = groups[assigned_groups[3][1], standings[assigned_groups[3][1], 2]]  # 1E vs 3rd
        r32_matches[82][1] = groups[assigned_groups[4][1], standings[assigned_groups[4][1], 2]]  # 1G vs 3rd
        r32_matches[77][1] = groups[assigned_groups[5][1], standings[assigned_groups[5][1], 2]]  # 1I vs 3rd
        r32_matches[87][1] = groups[assigned_groups[6][1], standings[assigned_groups[6][1], 2]]  # 1K vs 3rd
        r32_matches[80][1] = groups[assigned_groups[7][1], standings[assigned_groups[7][1], 2]]  # 1L vs 3rd

        _ = run_knockout_round(r32_matches, "Round of 32", andreas_bonus=4)


        r16_matches = {
        89: (knockout_results[74], knockout_results[77]),  # Winner 74 vs Winner 77
        90: (knockout_results[73], knockout_results[75]),  # Winner 73 vs Winner 75
        91: (knockout_results[76], knockout_results[78]),  # Winner 76 vs Winner 78
        92: (knockout_results[79], knockout_results[80]),  # Winner 79 vs Winner 80
        93: (knockout_results[83], knockout_results[84]),  # Winner 83 vs Winner 84
        94: (knockout_results[81], knockout_results[82]),  # Winner 81 vs Winner 82
        95: (knockout_results[86], knockout_results[88]),  # Winner 86 vs Winner 88
        96: (knockout_results[85], knockout_results[87]),  # Winner 85 vs Winner 87
        }

        _ = run_knockout_round(r16_matches, "Round of 16", andreas_bonus=5)

 
        qf_matches = {
        97: (knockout_results[89], knockout_results[90]),
        98: (knockout_results[93], knockout_results[94]),
        99: (knockout_results[91], knockout_results[92]),
        100: (knockout_results[95], knockout_results[96]),
        }

        _ = run_knockout_round(qf_matches, "Quarterfinals", andreas_bonus=6)
        

        sf_matches = {
        101: (knockout_results[97], knockout_results[98]),
        102: (knockout_results[99], knockout_results[100]),
        }

        third_place_losers = run_knockout_round(sf_matches, "Semifinals", andreas_bonus=7)


        third_place_match = {
        103: (tuple(third_place_losers)),
        }

        _ = run_knockout_round(third_place_match, "Third Place Match")
        
        
        final_match = {
        104: (knockout_results[101], knockout_results[102]),
        }
        
        _ = run_knockout_round(final_match, "Final", andreas_bonus=10)

        if collect_paths:
            seen_round = {}  # round -> set of participating teams (for stage-reach)
            for rec in sim_bracket:
                num = rec['num']
                slot_meta[num] = rec['round']
                slot_winner.setdefault(num, {})
                slot_winner[num][rec['w']] = slot_winner[num].get(rec['w'], 0) + 1
                key = f"{rec['a']} vs {rec['b']}"
                slot_matchup.setdefault(num, {})
                slot_matchup[num][key] = slot_matchup[num].get(key, 0) + 1
                if rec['round'] != 'Third Place Match':  # not a progression round
                    seen_round.setdefault(rec['round'], set()).update((rec['a'], rec['b']))
                    if rec['round'] == 'Final':
                        stage_reach.setdefault(rec['w'], {})
                        stage_reach[rec['w']]['Champion'] = stage_reach[rec['w']].get('Champion', 0) + 1
            for rnd, teams in seen_round.items():
                for t in teams:
                    stage_reach.setdefault(t, {})
                    stage_reach[t][rnd] = stage_reach[t].get(rnd, 0) + 1
            last_bracket = sim_bracket

        sample_scores = {}
        if pools is not None:  # score each participant for THIS simulation, then rank
            sim_a = {t: andreas_points[t] - snap_a[t] for t in andreas_points}
            sim_t = {t: trap_points[t] - snap_t[t] for t in trap_points}
            metric = {'andreas': sim_a, 'trap': sim_t}
            for pn, pd in pools.items():
                m = metric[pd['metric']]
                pots = pd.get('pots')
                parts = list(pd['participants'].items())
                keys = [_pool_sort_key(teams, m, pots) for _, teams in parts]  # incl. tiebreakers
                order = sorted(range(len(parts)), key=lambda i: keys[i], reverse=True)
                for finish, i in enumerate(order):
                    name = parts[i][0]
                    pool_agg[pn][name]['pts'] += keys[i][0]
                    pool_agg[pn][name]['pos'][finish] += 1
                mat = h2h_agg[pn]['mat']   # order is best->worst, so earlier beats later
                for a in range(len(order)):
                    rowa = mat[order[a]]
                    for b in range(a + 1, len(order)):
                        rowa[order[b]] += 1
                sample_scores[pn] = {parts[i][0]: round(keys[i][0], 2) for i in range(len(parts))}

        # Keep this sim as a replayable scenario (bracket + this-sim points).
        if collect_paths and len(samples) < n_samples:
            sample = {'bracket': sim_bracket, 'scores': sample_scores}
            if pools is not None:   # per-team points earned in THIS scenario
                sample['team'] = {'andreas': {t: round(sim_a[t], 2) for t in sim_a},
                                  'trap': {t: round(sim_t[t], 2) for t in sim_t}}
            samples.append(sample)

    if collect_paths or pools is not None:
        extra = {}
        if collect_paths:
            extra['paths'] = {
                'slot_meta': slot_meta,
                'slot_winner': slot_winner,
                'slot_matchup': slot_matchup,
                'sample': last_bracket,
            }
            extra['stage_reach'] = stage_reach
            extra['group_pos'] = group_pos
            extra['group_adv'] = group_adv
            extra['samples'] = samples
        if pools is not None:
            extra['pools'] = pool_agg
            extra['h2h'] = h2h_agg
        return winners, andreas_points, trap_points, timestart, extra
    return winners, andreas_points, trap_points, timestart


def _order_group(gi, group, pts, gd, gs, group_matches, elo, inv_team_dict):
    """Deterministic FIFA-style ordering of a group (no random tiebreak)."""
    rows = []
    for ti, name in enumerate(group):
        t_pts, t_gd, t_gs = pts[gi, ti], gd[gi, ti], gs[gi, ti]
        tied = [r for ri, r in enumerate(group) if pts[gi, ri] == t_pts and r != name]
        h2h_pts = h2h_gs = h2h_con = 0
        for rival in tied:
            mk = (inv_team_dict[name], inv_team_dict[rival])
            if mk in group_matches:
                a, b = group_matches[mk]
                h2h_gs += a; h2h_con += b
                h2h_pts += 3 if a > b else (1 if a == b else 0)
        rows.append((ti, (t_pts, h2h_pts, h2h_gs - h2h_con, h2h_gs, t_gd, t_gs, elo[inv_team_dict[name]])))
    return [ti for ti, _ in sorted(rows, key=lambda x: x[1], reverse=True)]


# Andreas knockout bonus by round (winner only); BRONZE (3rd place) scores nothing.
KO_ANDREAS_BONUS = {'R32': 4, 'R16': 5, 'QF': 6, 'SF': 7, 'FINAL': 10, 'BRONZE': 0}
_ROUND_ALIAS = {'R32': 'R32', 'RO32': 'R32', 'R16': 'R16', 'RO16': 'R16',
                'QF': 'QF', 'QUARTER': 'QF', 'QUARTERFINAL': 'QF',
                'SF': 'SF', 'SEMI': 'SF', 'SEMIFINAL': 'SF',
                'F': 'FINAL', 'FINAL': 'FINAL',
                '3RD': 'BRONZE', 'THIRD': 'BRONZE', 'BRONZE': 'BRONZE'}


def load_knockout(path):
    """Parse the hand-maintained knockout results file (data/knockout.csv).
    Returns a list of match dicts; [] if the file is missing or has no data rows."""
    if not os.path.exists(path):
        return []

    def score(s):
        s = (s or '').strip().replace(' ', '')
        if not s:
            return (0, 0)
        a, b = s.split('-')
        return (int(a), int(b))

    out = []
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            raw = (row.get('round') or '').strip()
            if not raw or raw.startswith('#'):          # skip blanks and comment lines
                continue
            rnd = _ROUND_ALIAS.get(raw.upper())
            if rnd is None:
                continue
            out.append({
                'round': rnd,
                'home': (row.get('home') or '').strip(),
                'away': (row.get('away') or '').strip(),
                'reg': score(row.get('reg')),
                'et': score(row.get('et')),
                'decider': (row.get('decider') or 'FT').strip().upper(),
                'winner': (row.get('winner') or '').strip(),
            })
    return out


def realized_points(groups, elo_dict, team_dict, fixtures, results, knockout=None):
    """Points actually banked so far from matches that have been played (deterministic).
    Group stage only — knockout points start once those results appear in results.tsv.
    Group-position bonuses are awarded only for groups that are mathematically complete;
    the 3rd-place qualifier bonus only once every group is done."""
    all_teams = [t for g in groups for t in g]
    points_map = {team: (i, j) for i, g in enumerate(groups) for j, team in enumerate(g)}
    inv_team_dict = {v: k for k, v in team_dict.items()}
    andreas = {t: 0 for t in all_teams}
    trap = {t: 0 for t in all_teams}
    gf = {t: 0 for t in all_teams}   # goals scored (regulation) per team, for tiebreakers
    ga = {t: 0 for t in all_teams}   # goals conceded per team

    played, current_elo = {}, dict(elo_dict)
    for _, r in results.sort_values(['Y', 'M', 'D']).iterrows():
        played[(r['HT'], r['AT'])] = (int(r['GH']), int(r['GA']))
        current_elo[r['HT']] = r['H_elo']
        current_elo[r['AT']] = r['A_elo']

    shape = np.shape(groups)
    pts, gd, gs = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    group_matches = {}
    pcount = [0] * len(groups)

    for fix in fixtures.itertuples(index=False, name=None):
        ht, at = fix[0], fix[1]
        if (ht, at) in played:
            g_a, g_b = played[(ht, at)]
        elif (at, ht) in played:
            g_b, g_a = played[(at, ht)]
        else:
            continue  # not played yet
        a, b = team_dict[ht], team_dict[at]
        ia, ib = points_map[a], points_map[b]
        group_matches[(ht, at)] = (g_a, g_b)
        group_matches[(at, ht)] = (g_b, g_a)
        gs[ia] += g_a; gs[ib] += g_b
        gd[ia] += g_a - g_b; gd[ib] += g_b - g_a
        gf[a] += g_a; ga[a] += g_b; gf[b] += g_b; ga[b] += g_a
        pcount[ia[0]] += 1
        if g_a == g_b:
            pts[ia] += 1; pts[ib] += 1
            for t in (a, b):
                trap[t] += 1; andreas[t] += 1
        else:
            w = a if g_a > g_b else b
            pts[points_map[w]] += 3
            trap[w] += 3; andreas[w] += 3
            if abs(g_a - g_b) >= 4:
                trap[w] += 0.5

    rr_games = len(groups[0]) * (len(groups[0]) - 1) // 2  # 6 for groups of 4
    complete = [gi for gi in range(len(groups)) if pcount[gi] >= rr_games]
    for gi in complete:
        order = _order_group(gi, groups[gi], pts, gd, gs, group_matches, current_elo, inv_team_dict)
        andreas[groups[gi][order[0]]] += 5          # group winner
        andreas[groups[gi][order[1]]] += 3          # runner-up
        if pts[gi, order[0]] == 9:                  # perfect group -> trap bonus
            trap[groups[gi][order[0]]] += 0.5

    if len(complete) == len(groups):                # all groups done -> 3rd-place qualifiers
        thirds = []
        for gi in range(len(groups)):
            ti = _order_group(gi, groups[gi], pts, gd, gs, group_matches, current_elo, inv_team_dict)[2]
            thirds.append((gi, ti, (pts[gi, ti], gd[gi, ti], gs[gi, ti], current_elo[inv_team_dict[groups[gi][ti]]])))
        thirds.sort(key=lambda x: x[2], reverse=True)
        for gi, ti, _ in thirds[:8]:
            andreas[groups[gi][ti]] += 1

    # --- knockout matches (from knockout.csv) ---
    ko_scored = 0   # KO games that award points (excludes the bronze match)
    ko_played = 0   # all valid KO games played (incl. bronze) -> total match count
    for ko in (knockout or []):
        h, aw, win = ko['home'], ko['away'], ko['winner']
        if h not in andreas or aw not in andreas or win not in andreas:
            continue  # unknown team name -> skip (data typo)
        ko_played += 1
        rh, ra = ko['reg']
        gf[h] += rh; ga[h] += ra; gf[aw] += ra; ga[aw] += rh   # regulation goals (tiebreaker)
        if ko['round'] == 'BRONZE':
            continue  # 3rd-place match scores no points
        ko_scored += 1
        andreas[win] += KO_ANDREAS_BONUS.get(ko['round'], 0)
        dec = ko['decider']
        if dec == 'P':
            trap[h] += 1; trap[aw] += 1; trap[win] += 0.5
        elif dec == 'ET':
            trap[h] += 1; trap[aw] += 1; trap[win] += 1
        else:                                                  # FT
            trap[win] += 3
        tot_h, tot_aw = rh + ko['et'][0], ra + ko['et'][1]
        if abs(tot_h - tot_aw) >= 4:                           # blowout bonus
            trap[win] += 0.5

    info = {'played': int(sum(pcount)), 'groups_complete': len(complete),
            'groups_total': len(groups), 'knockout_scored': ko_scored,
            'ko_played': ko_played}
    return andreas, trap, gf, ga, info


def print_winner_statistics(timestart, winners, nsim):
    # Sort the dictionary by the number of wins in descending order
    sorted_winners = sorted(winners.items(), key=lambda item: item[1], reverse=True)

    # Calculate the winning percentage and odds
    results = []
    for rank, (country, wins) in enumerate(sorted_winners, start=1):
        percentage = (wins / nsim) * 100
        if percentage > 0:
            odds = 100 / percentage
        else:
            odds = float('inf')  # If the percentage is 0, odds are infinite
        results.append((rank, country, percentage, odds))

    # Write the results to a .txt file
    file_name = "wc_winners_statistics.txt"
    with open(file_name, "w") as file:
        file.write(f"{'Rank':<5} {'Country':<15} {'%':<10} {'Odds':<10}\n")
        file.write("="*40 + "\n")
        for rank, country, percentage, odds in results:
            file.write(f"{rank:<5} {country:<15} {percentage:<10.2f} {odds:<10.2f}\n")
        #include time and number of simulations
        file.write(f"\nTime taken: {time.time()-timestart:.2f} seconds\n")
        file.write(f"Number of simulations: {nsim}\n")

def print_andreas_expected_pts(timestart, andreas_points, nsim):
    # Sort the dictionary by the number of points in descending order
    sorted_pts = sorted(andreas_points.items(), key=lambda item: item[1], reverse=True)

    results = []
    for rank, (country, pts) in enumerate(sorted_pts, start=1):
        average = (pts / nsim)
        results.append((rank, country, average))

    # Write the results to a .txt file
    file_name = "andreas_wc_expected_points.txt"
    with open(file_name, "w") as file:
        file.write(f"{'Rank':<5} {'Country':<15} {'xPts':<10}\n")
        file.write("="*30 + "\n")
        for rank, country, average in results:
            file.write(f"{rank:<5} {country:<15} {average:<10.2f}\n")
        #include time and number of simulations
        file.write(f"\nTime taken: {time.time()-timestart:.2f} seconds\n")
        file.write(f"Number of simulations: {nsim}\n")

def print_trap_expected_pts(timestart, trap_points, nsim):
    # Sort the dictionary by the number of points in descending order
    sorted_pts = sorted(trap_points.items(), key=lambda item: item[1], reverse=True)

    results = []
    for rank, (country, pts) in enumerate(sorted_pts, start=1):
        average = (pts / nsim)
        results.append((rank, country, average))

    # Write the results to a .txt file
    file_name = "trap_wc_expected_points.txt"
    with open(file_name, "w") as file:
        file.write(f"{'Rank':<5} {'Country':<15} {'xPts':<10}\n")
        file.write("="*30 + "\n")
        for rank, country, average in results:
            file.write(f"{rank:<5} {country:<15} {average:<10.2f}\n")
        #include time and number of simulations
        file.write(f"\nTime taken: {time.time()-timestart:.2f} seconds\n")
        file.write(f"Number of simulations: {nsim}\n")

def print_semifinal_statistics(timestart, semifinals, nsim):
    # Sort the dictionary by the number of wins in descending order
    sorted_semifinals = sorted(semifinals.items(), key=lambda item: item[1], reverse=True)

    # Calculate the winning percentage and odds
    results = []
    for rank, (country, semifinals) in enumerate(sorted_semifinals, start=1):
        percentage = (semifinals / nsim) * 100
        if percentage > 0:
            odds = 100 / percentage
        else:
            odds = float('inf')  # If the percentage is 0, odds are infinite
        results.append((rank, country, percentage, odds))

    # Write the results to a .txt file
    file_name = "final_euro_semifinalists_statistics.txt"
    with open(file_name, "w") as file:
        file.write(f"{'Rank':<5} {'Country':<15} {'%':<10} {'Odds':<10}\n")
        file.write("="*40 + "\n")
        for rank, country, percentage, odds in results:
            file.write(f"{rank:<5} {country:<15} {percentage:<10.2f} {odds:<10.2f}\n")
        #include time and number of simulations
        file.write(f"\nTime taken: {time.time()-timestart:.2f} seconds\n")
        file.write(f"Number of simulations: {nsim}\n")

if __name__ == "__main__":
    # nsim = 50000
    # groups, third_place_pairings, elo_dict, team_dict, fixtures = load_data()
    # winners, andreas_points, trap_points, timestart = simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures, nsim=nsim, print_results=False)
    # # print_semifinal_statistics(timestart, semi_final_stats, nsim)
    # print_winner_statistics(timestart, winners, nsim)
    # print_andreas_expected_pts(timestart, andreas_points, nsim)
    # print_trap_expected_pts(timestart, trap_points, nsim)

    groups, third_place_pairings, elo_dict, team_dict, fixtures, results = load_data()

    #normalize elo_dict to rule out structurally bad options (take host boost into account)
    # for team in elo_dict.keys():
    #     elo_dict[team] = 1500


    def calculate_score(option, point_dict):
        points = 0
        for team in option:
            points += point_dict[team]
        return points


    options = {
    'Christian': (['Argentina', 'Spain', 'Netherlands', 'Ecuador', 'Paraguay', 'Bosnia and Herzegovina'], 0),
    'Lone': (['Argentina', 'England', 'Germany', 'Norway', 'Sweden', 'Bosnia and Herzegovina'], 0),
    'Freja': (['France','England', 'Belgium', 'Austria', 'Sweden', 'New Zealand'], 0),
    'Søren': (['Brazil', 'Spain', 'Netherlands', 'Turkey', 'Sweden', 'South Africa'], 0),
    'Lauritz': (['France', 'Spain', 'Germany', 'Austria', 'Ivory Coast', 'Ghana'], 0),
    'Louise': (['Brazil', 'Spain', 'Germany', 'Turkey', 'Sweden', 'South Africa'], 0),
    }
    # options = {
    # 'Fred': (['Spain', 'Mexico', 'Switzerland', 'Cape Verde'], 0),
    # 'Emil': (['Argentina', 'Norway', 'Sweden', 'Scotland'], 0),
    # 'SadoTheShadow': (['Brazil', 'Germany', 'Ivory Coast', 'South Africa'], 0),
    # 'Stefan Winston Bligaard Netopil': (['Portugal', 'Turkey', 'Mexico', 'Switzerland'], 0),
    # 'Manni': (['Portugal', 'Netherlands', 'Mexico', 'Egypt'], 0),
    # 'Rasmus Bundgaard': (['Brazil', 'Germany', 'Algeria', 'South Africa'], 0),
    # 'Bjørnen i det blå hus': (['France', 'Norway', 'Egypt', 'Ivory Coast'], 0),
    # 'Nicolai Lind Mosbjerg': (['Spain', 'Switzerland', 'Turkey', 'Saudi Arabia'], 0),
    # 'Kenneth Sadolin Pedersen': (['France', 'Morocco', 'Japan', 'South Africa'], 0),
    # 'Andreas "the master" Simonsen': (['Spain', 'Mexico', 'Ecuador', 'Iran'], 0),
    # }

    simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures, results, nsim=1, print_results=True, skip_group_stage=False)

    # n = len(options)
    # nsol = 10000
    # points = np.zeros(n)
    # standings = np.zeros((n,n))

    # for _ in range(nsol):
    #     winners, andreas_points, trap_points, timestart = simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures, nsim=1, print_results=False)
        
    #     list_of_points = []
    #     for (option, opt_points) in options.values():
    #         points_option = calculate_score(option, trap_points)
    #         points_option += opt_points
    #         list_of_points.append(points_option)

    #     arg_sorted = np.argsort(list_of_points)[::-1]

    #     for standing, option in enumerate(arg_sorted):
    #         standings[option,standing] += 1
    #     points += np.array(list_of_points)

    # # print(standings)
    # # print(standings/nsol)
    # # print(points/nsol)
    # percentage = standings/nsol
    # for i,manager in enumerate(options.keys()):
    #     print(f'{manager}: {points[i]/nsol}')
    # print()
    # for i,manager in enumerate(options.keys()):
    #     print(f'{manager}: {percentage[i]}')

        

