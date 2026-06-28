import math
import numpy as np

def simulate_match(fix, elo_dict, group_stage=True, extra_time=False):
    """
    Simulates a match and returns (goals_team_a, goals_team_b)
    """
    # 1. Fetch baseline Elo ratings
    elo_a = elo_dict[fix[0]]
    elo_b = elo_dict[fix[1]]

    # 2. Update host advantages for 2026 (USA, MX, CA)
    # Note: In the group stage, they all play at home. 
    # In the knockout stage, only the US get host advantage, as the majority of matches are played on their home soil.
    if group_stage:
        hosts = ['US', 'MX', 'CA']
        if fix[0] in hosts:
            elo_a += 100
        if fix[1] in hosts:
            elo_b += 100
    else:
        hosts = ['US']
        if fix[0] in hosts:
            elo_a += 75 
        if fix[1] in hosts:
            elo_b += 75
        # MX/CA get a minor nod for early home matches & friendly border stadiums
        if fix[0] in ["MX", "CA"]:
            elo_a += 25
        if fix[1] in ["MX", "CA"]:
            elo_b += 25

    # 3. Establish macroeconomic tournament scoring baseline (1.35 goals/team)
    # Adjust baseline goals if we are in Extra Time
    base_goals = 1.35
    if extra_time:
        base_goals = base_goals * (30 / 90)  


    # 4. Convert Elo difference into expected goals (Lambdas)
    # A 400 Elo point advantage adds +1.0 expected goal to a team's baseline
    lambda_a = base_goals + ((elo_a - elo_b) / 400)
    lambda_b = base_goals + ((elo_b - elo_a) / 400)

    # Floor the values at 0.1 so a heavily outmatched team still has a tiny scoring chance
    lambda_a = max(0.1, lambda_a)
    lambda_b = max(0.1, lambda_b)

    # 5. Use Poisson to generate the final integers for goals scored
    goals_a = np.random.poisson(lam=lambda_a)
    goals_b = np.random.poisson(lam=lambda_b) 
    
    return goals_a, goals_b

def simulate_knockout_match(fix, elo_dict):
    """Wraps the simulator to guarantee a definitive winner for knockouts"""
    # 1. Regulation 90 minutes
    g_a, g_b = simulate_match(fix, elo_dict, extra_time=False, group_stage=False)
    total_g_a, total_g_b = g_a, g_b

    # 2. Check for Extra Time
    if total_g_a == total_g_b:
        et_g_a, et_g_b = simulate_match(fix, elo_dict, extra_time=True, group_stage=False)
        total_g_a += et_g_a
        total_g_b += et_g_b

        # 3. Check for Penalty Shootout (Coin Flip)
        if total_g_a == total_g_b:

            # Fetch current ratings to determine the skill gap
            elo_a = elo_dict[fix[0]]
            elo_b = elo_dict[fix[1]]
            elo_diff = elo_a - elo_b

            # Calculate a realistic edge (e.g., +10% probability per 400 Elo points)
            prob_a = 0.5 + (elo_diff / 4000)
            
            # Clamp between 35% and 65% to ensure it remains a high-variance shootout
            prob_a = np.clip(prob_a, 0.35, 0.65)
            prob_b = 1.0 - prob_a

            # Determine who advances based on the weighted probabilities
            penalty_winner = np.random.choice([fix[0], fix[1]], p=[prob_a, prob_b])
            return penalty_winner, total_g_a, total_g_b, "Penalties"
        else:
            winner = fix[0] if total_g_a > total_g_b else fix[1]
        return winner, total_g_a, total_g_b, "ET"

    winner = fix[0] if total_g_a > total_g_b else fix[1]
    return winner, total_g_a, total_g_b, "FT"
    
def update_elo(outcome, fix, elo_dict, group_stage=True):
    """
    outcome: name of the winning team (e.g. 'US') or 'Draw'
    fix: tuple/list of the two teams playing e.g. ('US', 'MX')
    """
    # 1. Grab base Elos
    elo_a = elo_dict[fix[0]]
    elo_b = elo_dict[fix[1]]

    # 2. Apply 2026 Host Advantages
    if group_stage:
        hosts = ['US', 'MX', 'CA']
        if fix[0] in hosts: elo_a += 100
        if fix[1] in hosts: elo_b += 100
    else:
        hosts = ['US']
        if fix[0] in hosts:
            elo_a += 75 
        if fix[1] in hosts:
            elo_b += 75
        # MX/CA get a minor nod for early home matches & friendly border stadiums
        if fix[0] in ["MX", "CA"]:
            elo_a += 25
        if fix[1] in ["MX", "CA"]:
            elo_b += 25

    # 3. Calculate Team A's win probability directly (handles negative dr perfectly!)
    dr = elo_a - elo_b
    expected_a = 1 / (10**(-dr / 400) + 1)
    expected_b = 1 - expected_a

    # 4. Convert match outcome to numeric values for Team A and Team B
    if outcome == 'Draw':
        actual_a, actual_b = 0.5, 0.5
    elif outcome == fix[0]:
        actual_a, actual_b = 1.0, 0.0
    else:
        actual_a, actual_b = 0.0, 1.0
    
    # 5. Calculate shifts using your K-factor
    K = 22  # You can adjust this based on how volatile you want the ratings to be
    elo_change_a = K * (actual_a - expected_a)
    elo_change_b = K * (actual_b - expected_b)
    
    # Update the actual dictionary (WITHOUT the host advantage baked in permanently)
    elo_dict[fix[0]] += elo_change_a
    elo_dict[fix[1]] += elo_change_b
    
    return elo_change_a, elo_change_b

