import json
import requests

# Toggle between World Cup and Euro standings endpoints
url = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
# url = "https://site.api.espn.com/apis/v2/sports/soccer/uefa.euro/standings"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

response = requests.get(url, headers=headers)
data = response.json()

groups = {}

# ESPN structures standings under the 'children' key
if "children" in data:
    for group_stage in data["children"]:
        group_name = group_stage.get("name")  # e.g., "Group A"
        group_data = []

        # Loop through each team entry in the current group
        standings = (
            group_stage.get("standings", {}).get("entries", [])
        )
        for entry in standings:
            team_info = entry.get("team", {})
            team_name = team_info.get("displayName")

            # Extract the team's current position rank
            stats = entry.get("stats", [])
            pos = next(
                (
                    stat.get("displayValue")
                    for stat in stats
                    if stat.get("name") == "rank"
                ),
                None,
            )

            if pos and team_name:
                group_data.append((pos, team_name))

        groups[group_name] = group_data

# Save the structured API data to a text file
filename = (
    "groups.txt"
)
with open(filename, "w", encoding="utf-8") as file:
    for group, data in groups.items():
        file.write(f"{group}:\n")
        for item in data:
            file.write(f"  {item[0]}: {item[1]}\n")
        file.write("\n")

print(f"API Data fetched and saved to '{filename}'.")