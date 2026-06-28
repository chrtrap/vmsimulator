import json
from itertools import combinations

# 1. Load your current JSON
with open('fifa_2026_combinations_complete.json', 'r') as f:
    extracted_data = json.load(f)

# 2. Extract the set of groups for every option we DID find
# We convert each row into a sorted tuple of group indices (0-11)
def get_indices_from_row(row):
    group_letters = {val[1] for key, val in row.items() if key != "Option"}
    return tuple(sorted([ord(g) - ord('A') for g in group_letters]))

extracted_combinations = {get_indices_from_row(row) for row in extracted_data}

# 3. Generate the "Master List" of all 495 possible combinations
all_groups = list(range(12)) # 0 to 11 (A to L)
master_combinations = set(combinations(all_groups, 8))

# 4. Compare
missing = master_combinations - extracted_combinations

print(f"Extracted: {len(extracted_combinations)}")
print(f"Expected: 495")
print(f"Missing: {len(missing)}")

if missing:
    print("\nMissing Group Combinations (by Index):")
    for m in sorted(list(missing))[:10]: # Show first 10
        letters = [chr(i + ord('A')) for i in m]
        print(f"- {' '.join(letters)}")