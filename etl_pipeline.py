import os
import time
import requests
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

try:
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor(buffered=True)
except mysql.connector.Error as err:
    print(f"Database connection failed: {err}")
    exit(1)

API_BASE = "https://play.limitlesstcg.com/api"

# --- HELPER FUNCTIONS ---
def make_request(url):
    """Wrapper that checks rate limit headers and pauses if necessary."""
    response = requests.get(url)
    remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
    if remaining < 5:
        print(f"Rate limit approaching ({remaining} left). Pausing for 5 seconds...")
        time.sleep(5)
    response.raise_for_status()
    return response.json()

def convert_date(iso_string):
    """Converts ISO 8601 timestamp to SQL DATE (YYYY-MM-DD)."""
    if not iso_string: return None
    return iso_string.split("T")[0]

def lookup_id_by_name(table_name, id_column_name, name_string):
    """
    Looks up an entity's ID in the database by its formatted name string.
    Includes a Python dictionary to translate Limitless strings to PokeAPI strings.
    """
    if not name_string: return None
    clean_name = name_string.strip()
    
    if table_name == "Pokemon":
        translations = {
            "Basculegion": "Basculegion Male", "Wash Rotom": "Rotom Wash",
            "Heat Rotom": "Rotom Heat", "Mow Rotom": "Rotom Mow",
            "Frost Rotom": "Rotom Frost", "Fan Rotom": "Rotom Fan",
            "Alolan Ninetales": "Ninetales Alola", "Hisuian Arcanine": "Arcanine Hisui",
            "Hisuian Samurott": "Samurott Hisui", "Galarian Slowking": "Slowking Galar",
            "Paldean Tauros Aqua Breed": "Tauros Paldea Aqua Breed",
            "Paldean Tauros Blaze Breed": "Tauros Paldea Blaze Breed",
            "Palafin": "Palafin Zero", "Maushold": "Maushold Family Of Four",
            "Aegislash": "Aegislash Shield", "Meowstic": "Meowstic Male",
            "Mimikyu": "Mimikyu Disguised", "Eternal Flower Floette": "Floette Eternal",
            "Lycanroc": "Lycanroc Midday", "Urshifu": "Urshifu Single Strike",
            "Urshifu-Rapid-Strike": "Urshifu Rapid Strike", "Tornadus": "Tornadus Incarnate",
            "Thundurus": "Thundurus Incarnate", "Landorus": "Landorus Incarnate",
            "Enamorus": "Enamorus Incarnate"
        }
        clean_name = translations.get(clean_name, clean_name)

    query = f"SELECT {id_column_name} FROM {table_name} WHERE name = %s"
    try:
        cursor.execute(query, (clean_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except mysql.connector.Error as err:
        return None

# --- CORE INGESTION PROCESS ---
def sync_vgc_data(target_count=5):
    """Fetches open-list VGC tournaments and triggers standings ingestion."""
    print(f"Searching for {target_count} tournaments with open team lists...")
    page = 1
    stored_count = 0
    
    while stored_count < target_count:
        url = f"{API_BASE}/tournaments?game=VGC&limit=50&page={page}"
        response_data = make_request(url)
        if not response_data: break
            
        for t_summary in response_data:
            if stored_count >= target_count: break
                
            tournament_api_id = t_summary['id']
            details_url = f"{API_BASE}/tournaments/{tournament_api_id}/details"
            details = make_request(details_url)
            
            if not details.get('decklists'): continue
                
            format_code = t_summary.get('format')
            country = "Online" if details.get('isOnline', True) else "In-Person"
            start_date = convert_date(t_summary.get('date'))
            
            cursor.execute("""
                INSERT INTO Tournament (generation_id, name, country, start_date, format_ruleset)
                VALUES (%s, %s, %s, %s, %s)
            """, (9, t_summary['name'], country, start_date, format_code))
            
            tournament_db_id = cursor.lastrowid
            print(f"👉 Found & Stored Open-List Tournament: {t_summary['name']} (ID: {tournament_db_id})")
            
            fetch_and_store_standings(tournament_api_id, tournament_db_id, start_date)
            stored_count += 1
            
        page += 1
    db.commit()

def fetch_and_store_standings(tournament_api_id, tournament_db_id, creation_date):
    """Maps players and match results, and passes team structures to the parser."""
    standings_url = f"{API_BASE}/tournaments/{tournament_api_id}/standings"
    standings = make_request(standings_url)
    
    for row in standings:
        api_player_handle = row.get('player') 
        display_name = row.get('name', '')    
        country_code = row.get('country', 'US')
        placement = row.get('placing')
        
        if not api_player_handle: continue
            
        name_parts = display_name.split(" ", 1)
        first_name = name_parts[0] if len(name_parts) > 0 else display_name
        last_name = name_parts[1] if len(name_parts) > 1 else None

        cursor.execute("""
            INSERT INTO Player (handle, first_name, last_name, country)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE handle=handle
        """, (api_player_handle, first_name, last_name, country_code))
        
        cursor.execute("SELECT player_id FROM Player WHERE handle = %s", (api_player_handle,))
        player_id = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO Team (player_id, creation_date)
            VALUES (%s, %s)
        """, (player_id, creation_date))
        team_id = cursor.lastrowid
        
        try:
            cursor.execute("""
                INSERT INTO Tournament_Result (tournament_id, player_id, team_id, placement)
                VALUES (%s, %s, %s, %s)
            """, (tournament_db_id, player_id, team_id, placement))
        except mysql.connector.Error:
            continue

        decklist_data = row.get('decklist')
        if decklist_data:
            process_vgc_team_members(decklist_data, team_id)

def process_vgc_team_members(decklist_data, team_id):
    """Unpacks the flexible API array and commits Pokemon, Items, Abilities, and Moves."""
    if isinstance(decklist_data, list):
        pokemon_entries = decklist_data
    elif isinstance(decklist_data, dict):
        pokemon_entries = decklist_data.get('pokemon', [])
    else:
        return

    for poke in pokemon_entries:
        species_name = poke.get('name')
        if not species_name: continue
            
        ability_name = poke.get('ability')
        item_name = poke.get('item')
        tera_type = poke.get('teraType', 'Normal')
        
        species_id = lookup_id_by_name("Pokemon", "species_id", species_name)
        if not species_id:
            base_name = species_name.split('-')[0].split(' ')[0]
            species_id = lookup_id_by_name("Pokemon", "species_id", base_name)
            if not species_id: continue 
        
        ability_id = lookup_id_by_name("Ability", "ability_id", ability_name) if ability_name else 1
        item_id = lookup_id_by_name("Item", "item_id", item_name) if item_name else None
        if not ability_id: ability_id = 1 
            
        evs = poke.get('evs', {})
        ev_hp = evs.get('hp', 0)
        ev_atk = evs.get('atk', 0)
        ev_def = evs.get('def', 0)
        ev_spa = evs.get('spa', 0)
        ev_spd = evs.get('spd', 0)
        ev_spe = evs.get('spe', 0)
        
        if (ev_hp + ev_atk + ev_def + ev_spa + ev_spd + ev_spe) > 510:
            ev_hp, ev_atk, ev_def, ev_spa, ev_spd, ev_spe = 0, 0, 0, 0, 0, 0

        cursor.execute("""
            INSERT INTO Team_Member (team_id, species_id, item_id, ability_id, tera_type, 
                                     ev_hp, ev_atk, ev_def, ev_spa, ev_spd, ev_spe)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (team_id, species_id, item_id, ability_id, tera_type, 
              ev_hp, ev_atk, ev_def, ev_spa, ev_spd, ev_spe))
        member_id = cursor.lastrowid
        
        moves_list = poke.get('attacks', [])
        for slot, move_name in enumerate(moves_list[:4], start=1):
            
            # --- ADD THIS DIAGNOSTIC PRINT ---
            print(f"      Attempting to map move: '{move_name}'")
            # ---------------------------------
            
            move_id = lookup_id_by_name("Move", "move_id", move_name)
            if move_id:
                cursor.execute("""
                    INSERT INTO Team_Member_Move (member_id, move_id, slot_number)
                    VALUES (%s, %s, %s)
                """, (member_id, move_id, slot))
            else:
                # --- ADD THIS DIAGNOSTIC PRINT ---
                print(f"      [!] FAILED to map move: '{move_name}'")

if __name__ == "__main__":
    sync_vgc_data(target_count=5)
    cursor.close()
    db.close()
    print("\n✅ VGC Tournament Ingestion Complete!")