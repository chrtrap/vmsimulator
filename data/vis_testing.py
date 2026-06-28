import numpy as np
import pandas as pd

# Placeholder functions for match_simulator
class MatchSimulator:
    @staticmethod
    def simulate_match(fix, elo_dict, group_stage=True):
        # Randomly decide the outcome for simplicity
        return np.random.choice([fix[0], fix[1], 'Draw'])

    @staticmethod
    def update_elo(outcome, fix, elo_dict):
        pass

match_simulator = MatchSimulator()

# Placeholder data for elo_dict and groups
elo_dict = {'Germany': 2000, 'Belgium': 1900, 'Spain': 1950, 'England': 1850, 'Ukraine': 1750,
            'Portugal': 1800, 'France': 2100, 'Scotland': 1600, 'Italy': 1700, 'Switzerland': 1650,
            'Croatia': 1680, 'Netherlands': 1700, 'Hungary': 1550, 'Czechia': 1580, 'Serbia': 1600,
            'Denmark': 1620, 'Austria': 1570, 'Turkey': 1530, 'Slovenia': 1510, 'Poland': 1490,
            'Albania': 1450, 'Slovakia': 1460, 'Romania': 1440, 'Georgia': 1400}

teams = list(elo_dict.keys())
np.random.shuffle(teams)
groups = np.array(teams).reshape((6, 4))

# Initialize points array and fixture
points = np.zeros(np.shape(groups))
fixtures = pd.DataFrame([(groups[i, j], groups[i, k]) for i in range(groups.shape[0]) for j in range(groups.shape[1]) for k in range(j+1, groups.shape[1])], columns=['Team1', 'Team2'])

# Group Stage Simulation
for idx, fix in fixtures.iterrows():
    outcome = match_simulator.simulate_match(fix, elo_dict, group_stage=True)
    match_simulator.update_elo(outcome, fix, elo_dict)  # Update elo
    if outcome == 'Draw':
        points[np.where(groups == fix['Team1'])] += 1
        points[np.where(groups == fix['Team2'])] += 1
    else:
        points[np.where(groups == outcome)] += 3

# Calculate group standings
int_points = points.astype(int)
noise = np.random.normal(0, 250, np.shape(points)) * 1e-4 + np.array([[elo_dict[team] for team in group] for group in groups]) * 1e-4
noisy_points = points + noise
standings = np.argsort(-noisy_points, axis=1)

# Third place rankings
thirds = standings[:, 2]
third_points = noisy_points[np.arange(noisy_points.shape[0]), thirds]
sorted_third_indices = np.argsort(-third_points)[:4]
top_third_teams = thirds[sorted_third_indices]

# Generate Text File
file_name = "tournament_visualization.txt"
with open(file_name, "w") as file:
    file.write("Group Stage Standings:\n")
    file.write("="*80 + "\n")
    
    for i in range(6):
        file.write(f"Group {chr(65 + i)} Standings:\n")
        group_standing = standings[i]
        teams_sorted = groups[i][group_standing]
        points_sorted = noisy_points[i][group_standing]
        for j, (team, point) in enumerate(zip(teams_sorted, points_sorted)):
            qualifier = " (Q)" if j < 2 or group_standing[j] in top_third_teams else ""
            file.write(f"{j+1}. {team:<15} Points: {point:.2f}{qualifier}\n")
        file.write("\n")
    
    file.write("\nThird-Place Rankings:\n")
    file.write("="*80 + "\n")
    third_team_names = [groups[i][third] for i, third in enumerate(thirds)]
    third_team_points = int_points[np.arange(noisy_points.shape[0]), thirds]
    sorted_third_team_names = [third_team_names[i] for i in sorted_third_indices]
    sorted_third_team_points = third_team_points[sorted_third_indices]
    
    for i, (team, point) in enumerate(zip(sorted_third_team_names, sorted_third_team_points)):
        qualifier = " (Q)" if i < 4 else ""
        file.write(f"{i+1}. {team:<15} Points: {point:.2f}{qualifier}\n")
    file.write("\n")

    # Function to generate knockout phase matchups and results
    def generate_knockout_phase(phase_name, pairings, outcomes):
        file.write(f"{phase_name}:\n")
        file.write("="*80 + "\n")
        for i, (team1, team2) in enumerate(pairings):
            outcome = outcomes[i]
            file.write(f"{team1} vs {team2} - Winner: {outcome}\n")
        file.write("\n")

    # Quarterfinals
    quarterfinal_pairings = [
        (groups[0, standings[0, 0]], groups[1, standings[1, 1]]),
        (groups[2, standings[2, 0]], groups[3, standings[3, 1]]),
        (groups[4, standings[4, 0]], groups[5, standings[5, 1]]),
        (groups[0, standings[0, 1]], groups[1, standings[1, 0]])
    ]
    quarterfinal_outcomes = []
    for team1, team2 in quarterfinal_pairings:
        outcome = match_simulator.simulate_match((team1, team2), elo_dict, group_stage=False)
        if outcome == 'Draw':
            outcome = np.random.choice([team1, team2])
        match_simulator.update_elo(outcome, (team1, team2), elo_dict)
        quarterfinal_outcomes.append(outcome)
    
    generate_knockout_phase("Quarterfinals", quarterfinal_pairings, quarterfinal_outcomes)

    # Semifinals
    semifinal_pairings = [
        (quarterfinal_outcomes[0], quarterfinal_outcomes[1]),
        (quarterfinal_outcomes[2], quarterfinal_outcomes[3])
    ]
    semifinal_outcomes = []
    for team1, team2 in semifinal_pairings:
        outcome = match_simulator.simulate_match((team1, team2), elo_dict, group_stage=False)
        if outcome == 'Draw':
            outcome = np.random.choice([team1, team2])
        match_simulator.update_elo(outcome, (team1, team2), elo_dict)
        semifinal_outcomes.append(outcome)
    
    generate_knockout_phase("Semifinals", semifinal_pairings, semifinal_outcomes)

    # Final
    final_pairing = (semifinal_outcomes[0], semifinal_outcomes[1])
    final_outcome = match_simulator.simulate_match(final_pairing, elo_dict, group_stage=False)
    if final_outcome == 'Draw':
        final_outcome = np.random.choice(final_pairing)
    match_simulator.update_elo(final_outcome, final_pairing, elo_dict)
    
    file.write("Final:\n")
    file.write("="*80 + "\n")
    file.write(f"{final_pairing[0]} vs {final_pairing[1]} - Winner: {final_outcome}\n")
    file.write("\n")

print(f"Results written to {file_name}")

