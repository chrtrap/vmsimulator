import json

# Load the messy JSON we just extracted
with open('fifa_2026_combinations_complete.json', 'r') as f:
    raw_data = json.load(f)

# Helper to convert 'A' -> 0, 'B' -> 1, etc.
def letter_to_idx(letter):
    return ord(letter.upper()) - ord('A')

# Helper to parse '3E' into (3, 4)
def parse_team_code(code):
    # code[0] is '3', code[1] is the group letter
    return (int(code[0]), letter_to_idx(code[1]))

parsed_combinations = {}

for row in raw_data:
    # 1. Figure out which groups are in this option
    # We look at all values (except 'Option') and extract the group letter from '3X'
    advancing_groups = []
    for key, val in row.items():
        if key != "Option":
            advancing_groups.append(letter_to_idx(val[1]))
    
    # Sort them to create the unique key (the tuple of indices)
    group_key = tuple(sorted(advancing_groups))
    
    # 2. Map the opponents for 1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L in order
    # This matches your old list structure [(3, 0), (3, 3)...]
    matchup_list = [
        parse_team_code(row["1A"]),
        parse_team_code(row["1B"]),
        parse_team_code(row["1D"]),
        parse_team_code(row["1E"]),
        parse_team_code(row["1G"]),
        parse_team_code(row["1I"]),
        parse_team_code(row["1K"]),
        parse_team_code(row["1L"])
    ]
    
    parsed_combinations[group_key] = matchup_list

# Save to the format your old model expects
output_file = "parsed_wc2026_combinations.txt"
with open(output_file, 'w') as file:
    for groups, matchups in parsed_combinations.items():
        file.write(f"{groups}: {matchups}\n")

print(f"Done! Format matched and saved to {output_file}")
