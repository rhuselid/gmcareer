## General Manager Career Mode Game

The goal of this repo is to stand up a proof of concept for text/UI-based computer game based around simulating being a General Manager in American Football (i.e. the NFL).

The game should take from games like Football College Dynasty and Out of the Park Baseball. The goal is not impressive graphics, but rather a strong simulation engine.

### Primary DTOs

Managers have the following characteristics:
- scouting 
- developing potential 
- unlocking new potential
- convincing players to join
- in-game management

Players have the following characteristics
- height
- weight
- age
- speed
- acceleration
- lateral quickness
- vision
- lower body strength
- upper body strength
- etc.

Players additionally have position specific characteristics:
- overall (grade)
- familiarity 
- kick power
- arm strength
- run block
- pass rush 
- pass protection
- scrambling
- etc.

Teams have the following characteristics
- name
- prestige
- facility grade
- if college, NIL budget
- if pro, budget

All skills should be scored on the 0-99 basis.

### Simulation Engine
Games are simulated one by one, rather than on a per-play basis. For the time being we can leave a large TODO and simply generate the player stats as a mixture of randomness and relevant attributes. For example, rushing yards should be a (1/3 running back ability, 2/3 offensive line ability) * randomness.

### League Rank
We simulate 3 levels of football: high school, college, and professional. Each level feeds into one another with the best high school players becoming college player and so on.

We will keep things simple with the following structure:

High School
- 10 Regional Divisions each with 10 teams.

College
- 3 Divisions (D1, D2, D3) each with 10 teams.

Professional
- 1 Division with 10 teams.

All teams play each other twice inside the division. Therefore, every team should play 18 games each season. 

Managers get 'renown' beating expectations going into a season and lose it for missing them. 

### How Players Move Between Leagues

#### High School
Players simply appear at the high school level. However their abilities are a combination of the manager's scouting ability and the facility grade

#### College
Teams have a certain number of scholarships to offer which they can offer to high school players. Outside of the scholarships, players are randomly generated as with new high school players.

When a player is offered multiple scholarships, they select the school that they have the highest interest score in. Interest score is determined by a combination of proximity to home, prestige, and perceived chance at playing time.

Transferring does not exist. Red shirting does, however.

After 3 years of college, players become eligible to be drafted. Players that are not drafted after this year return to college.

After the last year of elligibility, undrafted players become free agents.

#### Professional

Drafting, free agency, and trades are all ways how a player moves between teams/levels.

### Character Creation
Players start with a set amount of skill points to allocate between their skills as a manager.

Players start managing a high school team with the goal of moving up from there.

### End of Year

Players get renown for success and lose it for failure. This stat should generally gradually move upward.

At the end of the season, users get skill points depending on performance which they can spend on their skills

### Offseason 

Draft, free agency, college recruiting, player development, position training.

---

### Development / environment

Use the project env **gmgame** so the base Python is untouched.

- **Windows (PowerShell)**  
  1. One-time: `.\scripts\ensure-venv.ps1` (creates venv `gmgame` and installs deps).  
  2. When you `cd` into GMCareer: run `.\scripts\activate.ps1` to activate.  
  3. **Auto-activate on cd**: run once `.\scripts\register-auto-activate.ps1` to add a profile hook; the `gmgame` env will activate when you enter the repo and deactivate when you leave. Open a new terminal, then `cd` into GMCareer to use it.

- **Conda**  
  `conda env create -f environment.yml` then `conda activate gmgame`.

- **direnv (Unix / WSL / Git Bash)**  
  Run `direnv allow` in the repo; `layout python` and pip install run automatically when you `cd` in.
