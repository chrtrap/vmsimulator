import sys
import pandas as pd
import numpy as np
# Add this line right here:
np.bool = bool  # Fixes old libraries looking for np.bool
import time
from docplex.mp.model import Model
from translate import Translator
import sys
import os

import wc_simulation as wc

DANISH_TO_ENGLISH = {
    "Spanien": "Spain",
    "Frankrig": "France",
    "England": "England",
    "Brasilien": "Brazil",
    "Argentina": "Argentina",
    "Portugal": "Portugal",
    "Tyskland": "Germany",
    "Holland": "Netherlands",
    "Norge": "Norway",
    "Belgien": "Belgium",
    "Colombia": "Colombia",
    "Japan": "Japan",
    "Marokko": "Morocco",
    "USA": "United States",
    "Uruguay": "Uruguay",
    "Kroatien": "Croatia",
    "Mexico": "Mexico",
    "Schweiz": "Switzerland",
    "Tyrkiet": "Turkey",
    "Senegal": "Senegal",
    "Ecuador": "Ecuador",
    "Sverige": "Sweden",
    "Canada": "Canada",
    "Østrig": "Austria",
    "Paraguay": "Paraguay",
    "Skotland": "Scotland",
    "Bosnien-Hercegovina": "Bosnia and Herzegovina",
    "Egypten": "Egypt",
    "Elfenbenskysten": "Ivory Coast",
    "Tjekkiet": "Czechia",
    "Ghana": "Ghana",
    "Algeriet": "Algeria",
    "Australien": "Australia",
    "Sydkorea": "South Korea",
    "Iran": "Iran",
    "Tunesien": "Tunisia",
    "DR Congo": "DR Congo",
    "Qatar": "Qatar",
    "Saudi-Arabien": "Saudi Arabia",
    "Sydafrika": "South Africa",
    "Panama": "Panama",
    "New Zealand": "New Zealand",
    "Irak": "Iraq",
    "Usbekistan": "Uzbekistan",
    "Kap Verde": "Cape Verde",
    "Curacao": "Curaçao",
    "Jordan": "Jordan",
    "Haiti": "Haiti",
    "Ukraine": "Ukraine",
}

def load_seeding(file_name):
    translator = DANISH_TO_ENGLISH
    #translator = Translator(from_lang="Danish", to_lang="English")
    with open(file_name,'r') as f:
        df = pd.DataFrame(columns=["Country","Pot"])
        while True:
            #check if line is wcpty
            line = f.readline().split()
            if not line:
                break
            #check if line is a number
            if line[0].isdigit():
                current_pot = int(line[0])
                continue
            row = []
            if len(line) == 2:
                translated = translator.get(line[0]+" "+line[1], line[0]+" "+line[1])
                row.extend([translated, current_pot])
            elif len(line) == 3:
                translated = translator.get(line[0]+" "+line[1]+" "+line[2], line[0]+" "+line[1]+" "+line[2])
                row.extend([translated, current_pot])
            else:
                translated = translator.get(line[0], line[0])
                if line[0] == 'Ukraine':
                    translated = "Ukraine"
                elif translated == "Curacao":
                    translated = "Curaçao"
                elif translated == "USA":
                    translated = "United States"
                row.extend([translated, current_pot])
            df_len = len(df)
            df.loc[df_len] = row
        f.close()
    return df

def load_prices(file_name):
    translator = Translator(from_lang="English", to_lang="English")
    with open(file_name,'r') as f:
        df = pd.DataFrame(columns=["Country","Price"])
        while True:
            line = f.readline().split()
            row = []
            if len(line) == 0:
                break
            elif len(line) == 3:
                translated = translator.translate(line[0]+" "+line[1])
                row.extend([translated, int(line[2])])
            elif len(line) == 4:
                translated = translator.translate(line[0]+" "+line[1]+" "+line[2])
                row.extend([translated, int(line[3])])
            else:
                translated = translator.translate(line[0])
                if line[0] == 'Ukraine':
                    translated = "Ukraine"
                elif translated == "The Netherlands ":
                    translated = "Netherlands"
                elif translated == "Curacao":
                    translated = "Curaçao"
                elif translated == "USA":
                    translated = "United States"
                row.extend([translated, int(line[1])])
            df_len = len(df)
            df.loc[df_len] = row
        f.close()
    return df

def load_xPts(file_name):
    with open(file_name,'r') as f:
        df = pd.DataFrame(columns=["Country","xPts"])
        #skip frist two lines
        f.readline()
        f.readline()
        while True:
            line = f.readline().split()
            row = []
            if len(line) == 0:
                break
            elif len(line) == 4:
                row.extend([line[1]+" "+line[2], float(line[3])])
            elif len(line) == 5:
                row.extend([line[1]+" "+line[2]+" "+line[3], float(line[4])])
            else:
                row.extend([line[1], float(line[2])])
            df_len = len(df)
            df.loc[df_len] = row
        f.close()
    #write dict in format {Land: float}
    dictionary = {}
    for i in range(len(df)):
        dictionary[df.iloc[i,0]] = df.iloc[i,1]
    return dictionary


def solve_Trap(data, point_dict, nsol=1, print_sol=False):
    translator = Translator(to_lang="Danish")
    teams = list(set(data['Country'].tolist()))
    team_data =  data.set_index('Country').T.to_dict()
    # model
    model = Model()

    #variables
    pick_team = model.binary_var_dict(teams, name='team')
    
    model.add_constraint(model.sum(pick_team[land] for land in teams) == 6, ctname='team_count')
    model.add_constraint(model.sum(pick_team[land] for land in teams if team_data[land]["Pot"] == 1) == 2, ctname='pot_1')
    model.add_constraint(model.sum(pick_team[land] for land in teams if team_data[land]["Pot"] == 2) == 1, ctname='pot_2')
    model.add_constraint(model.sum(pick_team[land] for land in teams if team_data[land]["Pot"] == 3) == 1, ctname='pot_3')
    model.add_constraint(model.sum(pick_team[land] for land in teams if team_data[land]["Pot"] == 4) == 1, ctname='pot_4')
    model.add_constraint(model.sum(pick_team[land] for land in teams if team_data[land]["Pot"] == 5) == 1, ctname='pot_5')

    
    #objective
    objective = model.sum(point_dict[land]*pick_team[land] for land in teams)
    
    model.set_objective('min',-objective)
    solution_list = []
    for i in range(nsol):
        model.solve()
        if print_sol:
            print("Løsning {}".format(i+1))
            print(f'xPoints: {round(objective.solution_value,2)}')
        count = 1
        solution = []
        for land in teams:
            if pick_team[land].solution_value == 1:
                if print_sol:
                    print(f'{count}. {translator.translate(land)} - Seedningslag: {team_data[land]["Pot"]} - xPts: {point_dict[land]*pick_team[land].solution_value}')
                solution.append(land)
                count += 1
        model.add_constraint(model.sum(pick_team[land] for land in solution) <= 5, ctname='new_solution')
        solution_list.append(solution)
    if nsol == 1:
        return [tuple(sorted(solution_list[0]))]
    return [tuple(sorted(solution)) for solution in solution_list]

def solve_Andreas(data, point_dict, nsol=1, print_sol=False):
    translator = Translator(to_lang="Danish")
    teams = list(set(data['Country'].tolist()))
    team_data =  data.set_index('Country').T.to_dict()
    # model
    model = Model()

    #variables
    pick_team = model.binary_var_dict(teams, name='team')
    
    model.add_constraint(model.sum(pick_team[land] for land in teams) == 4, ctname='team_count')
    model.add_constraint(model.sum(pick_team[land]*team_data[land]["Price"] for land in teams) <= 1300, ctname='budget')

    
    #objective
    objective = model.sum(point_dict[land]*pick_team[land] for land in teams)
    
    model.set_objective('min',-objective)
    solution_list = []
    for i in range(nsol):
        model.solve()
        if print_sol:
            print("Løsning {}".format(i+1))
            print(f'xPoints: {round(objective.solution_value,2)} - Budget: {int(model.sum(pick_team[land]*team_data[land]["Price"] for land in teams).solution_value)}')
        count = 1
        solution = []
        for land in teams:
            if pick_team[land].solution_value == 1:
                if print_sol:
                    print(f'{count}. {translator.translate(land)} - Pris: {team_data[land]["Price"]} - xPts: {point_dict[land]*pick_team[land].solution_value}')
                solution.append(land)
                count += 1
        model.add_constraint(model.sum(pick_team[land] for land in solution) <= 3, ctname='new_solution')
        solution_list.append(solution)
    if nsol == 1:
        return [tuple(sorted(solution_list[0]))]
    return [tuple(sorted(solution)) for solution in solution_list]

def solve_by_xpts(nsol=1, comp="Andreas", print_sol=False):
    data = load_prices(f'{comp} konkurrence/prisliste.txt')
    xPts = load_xPts(f'{comp} konkurrence/{comp}_wc_expected_points.txt')
    if comp == "Andreas":
        solution = solve_Andreas(data, xPts, nsol=nsol, print_sol=print_sol)
    elif comp == "Trap":
        solution = solve_Trap(data, xPts, nsol=nsol, print_sol=print_sol)
    return solution

def solve_by_single_tournament(nsol=1, comp="Andreas", include_top=10, print_sol=False):
    time_start = time.time()
    if comp == "Andreas":
        data = load_prices(f'{comp} konkurrence/prisliste.txt')
    elif comp == "Trap":
        data = load_seeding(f'{comp} konkurrence/{comp}_seeding.txt')
    groups, third_place_pairings, elo_dict, team_dict, fixtures = wc.load_data()
    solution_dict = {}
    bcpu = 0
    cfhu = 0
    for _ in range(nsol):
        winners, andreas_points, trap_points, timestart = wc.simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures,nsim=1)
        if comp == "Andreas":
            solution = solve_Andreas(data, andreas_points, nsol=include_top, print_sol=False)
        elif comp == "Trap":
            solution = solve_Trap(data, trap_points, nsol=include_top, print_sol=False)
        for sol in solution:
            if sol in solution_dict:
                solution_dict[sol] += 1
            else:
                solution_dict[sol] = 1
        if ('Belgium', 'Czechia', 'Portugal', 'Ukraine') in solution:
            bcpu += 1
        if ('Croatia', 'France', 'Hungary', 'Ukraine') in solution:
            cfhu += 1
    # print(f'Belgium, Czechia, Portugal, Ukraine: {bcpu/nsol*100:.2f}%')
    # print(f'Croatia, France, Hungary, Ukraine: {cfhu/nsol*100:.2f}%')
    # print(f"Time taken: {time.time()-time_start:.2f} seconds")
    if print_sol:
        sorted_sols = sorted(solution_dict.items(), key=lambda x: x[1], reverse=True)
        file_name = f"{comp}_most_common.txt"
        with open(file_name, "w") as file:
            file.write(f"{'Rank':<5} {'Solution':<40} {'%':<10}\n")
            file.write("="*55 + "\n")
            for idx,(solution,freq) in enumerate(sorted_sols):
                solution = ", ".join(solution)
                file.write(f"{idx+1:<5} {solution:<40} {round(freq/nsol*100,2):<10.2f}\n")
            #include time and number of simulations
            file.write(f"\nTime taken: {time.time()-time_start:.2f} seconds\n")
            file.write(f"Number of solves: {nsol}\n")
    return solution_dict



if __name__ == "__main__":
    #solve_by_single_tournament(nsol=10000, comp="Andreas", include_top=1, print_sol=True)
    solve_by_xpts(nsol=20, comp='Andreas', print_sol=True) 


    # groups, third_place_pairings, elo_dict, team_dict, fixtures = wc.load_data()
    # # solutions = solve_by_xpts(nsol=10, print_sol=False)

    # # options = {f'option_{i+1}': solution for i,solution in enumerate(solutions)}


    # def calculate_sccore(option, point_dict):
    #     pts = 0
    #     for team in option:
    #         pts += point_dict[team]
    #     return pts

    # options = {
    # 'option_3' : ['Hungary', 'Croatia', 'France', 'Ukraine'],
    # 'option_4' : ['Austria', 'Croatia', 'France', 'Ukraine'],
    #     }


    # n = len(options)
    # nsol =50000
    # points = np.zeros(n)
    # standings = np.zeros((n,n))

    # for _ in range(nsol):
    #     winners, andreas_points, trap_points, timestart = wc.simulate_tournament(groups, third_place_pairings, elo_dict, team_dict, fixtures, nsim=1, print_results=False)
        
    #     list_of_points = []
    #     for option in options.values():
    #         points_option = calculate_sccore(option, andreas_points)
    #         list_of_points.append(points_option)

    #     arg_sorted = np.argsort(list_of_points)[::-1]

    #     for standing, option in enumerate(arg_sorted):
    #         standings[option,standing] += 1
    #     points += np.array(list_of_points)

    # print(standings)
    # print(standings/nsol)
    
    # for i, option in enumerate(options.values()):
    #     print(f'{option}: {points[i]/nsol} xPts, {standings[i,0]/nsol*100:.2f}% 1st, {standings[i,1]/nsol*100:.2f}% 2nd' )
    #     print(f'Ending last {standings[i,-1]/nsol*100:.2f}% of the time')
    #     print()