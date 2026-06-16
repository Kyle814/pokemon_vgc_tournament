DROP DATABASE IF EXISTS pokemon_vgc; 
CREATE DATABASE pokemon_vgc;
USE pokemon_vgc;

-- 1. IMMUTABLE DICTIONARIES (Singular Names)
CREATE TABLE Generation (
    generation_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE Pokemon (
    species_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE Move (
    move_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE Item (
    item_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE Ability (
    ability_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

-- 2. VERSIONED DICTIONARIES (Handles Generation 9 stats and types)
CREATE TABLE Pokemon_Generation_Stat (
    species_id INT,
    generation_id INT,
    type_1 VARCHAR(20) NOT NULL,
    type_2 VARCHAR(20), -- NULL if monotype
    base_hp INT NOT NULL,
    base_atk INT NOT NULL,
    base_def INT NOT NULL,
    base_spa INT NOT NULL,
    base_spd INT NOT NULL,
    base_spe INT NOT NULL,
    PRIMARY KEY (species_id, generation_id),
    FOREIGN KEY (species_id) REFERENCES Pokemon(species_id),
    FOREIGN KEY (generation_id) REFERENCES Generation(generation_id)
);

CREATE TABLE Move_Generation_Stat (
    move_id INT,
    generation_id INT,
    type VARCHAR(20) NOT NULL,
    category VARCHAR(20), 
    base_power INT,       
    accuracy INT,         
    PRIMARY KEY (move_id, generation_id),
    FOREIGN KEY (move_id) REFERENCES Move(move_id),
    FOREIGN KEY (generation_id) REFERENCES Generation(generation_id)
);

-- 3. PLAYERS AND TOURNAMENTS
CREATE TABLE Player (
    player_id INT PRIMARY KEY AUTO_INCREMENT,
    handle VARCHAR(50) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    country VARCHAR(50)
);

CREATE TABLE Tournament (
    tournament_id INT PRIMARY KEY AUTO_INCREMENT,
    generation_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(50) NOT NULL,
    start_date DATE,
    format_ruleset VARCHAR(50),
    FOREIGN KEY (generation_id) REFERENCES Generation(generation_id)
);

-- 4. TEAMS AND TOURNAMENT RESULTS
CREATE TABLE Team (
    team_id INT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    creation_date DATE,
    FOREIGN KEY (player_id) REFERENCES Player(player_id)
);

CREATE TABLE Tournament_Result (
    result_id INT PRIMARY KEY AUTO_INCREMENT,
    tournament_id INT NOT NULL,
    player_id INT NOT NULL,
    team_id INT NOT NULL,
    placement INT NOT NULL, 
    FOREIGN KEY (tournament_id) REFERENCES Tournament(tournament_id),
    FOREIGN KEY (player_id) REFERENCES Player(player_id),
    FOREIGN KEY (team_id) REFERENCES Team(team_id),
    CONSTRAINT unique_player_tournament UNIQUE (tournament_id, player_id) 
);

-- 5. SPECIFIC TEAM MEMBERS AND MOVES
CREATE TABLE Team_Member (
    member_id INT PRIMARY KEY AUTO_INCREMENT,
    team_id INT NOT NULL,
    species_id INT NOT NULL,
    item_id INT, 
    ability_id INT NOT NULL,
    tera_type VARCHAR(20), 
    ev_hp INT DEFAULT 0,
    ev_atk INT DEFAULT 0,
    ev_def INT DEFAULT 0,
    ev_spa INT DEFAULT 0,
    ev_spd INT DEFAULT 0,
    ev_spe INT DEFAULT 0,
    FOREIGN KEY (team_id) REFERENCES Team(team_id),
    FOREIGN KEY (species_id) REFERENCES Pokemon(species_id),
    FOREIGN KEY (item_id) REFERENCES Item(item_id),
    FOREIGN KEY (ability_id) REFERENCES Ability(ability_id),
    CHECK (ev_hp + ev_atk + ev_def + ev_spa + ev_spd + ev_spe <= 510)
);

CREATE TABLE Team_Member_Move (
    member_id INT NOT NULL,
    move_id INT NOT NULL,
    slot_number INT NOT NULL, 
    PRIMARY KEY (member_id, move_id),
    FOREIGN KEY (member_id) REFERENCES Team_Member(member_id),
    FOREIGN KEY (move_id) REFERENCES Move(move_id),
    CHECK (slot_number BETWEEN 1 AND 4)
);

SELECT 
    p.name AS pokemon_name,
    m.name AS move_name,
    COUNT(*) AS times_seen together
FROM Team_Member_Move tmm
JOIN Move m ON tmm.move_id = m.move_id
JOIN Team_Member tm ON tmm.member_id = tm.member_id
JOIN Pokemon p ON tm.species_id = p.species_id
GROUP BY p.name, m.name
ORDER BY p.name ASC, times_seen_together DESC;