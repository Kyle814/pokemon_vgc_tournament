import os
import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# --- HELPER FUNCTIONS ---
def extract_id_from_url(url):
    """Extracts the integer ID from the end of a PokeAPI URL."""
    return int(url.strip('/').split('/')[-1])

def format_name(raw_name):
    """
    Cleans up PokeAPI formatting for your database display.
    Turns 'flutter-mane' into 'Flutter Mane', but protects real hyphens.
    """
    KEEP_HYPHENS = {
        "ho-oh", "porygon-z", "jangmo-o", "hakamo-o", "kommo-o", 
        "chien-pao", "wo-chien", "ting-lu", "chi-yu",
        "u-turn", "v-create", "will-o-wisp", "x-scissor", "freeze-dry", 
        "double-edge", "self-destruct", "baby-doll-eyes"
    }
    
    if raw_name.lower() in KEEP_HYPHENS:
        return raw_name.title()
    else:
        return raw_name.replace('-', ' ').title()

# --- SEEDING FUNCTIONS ---
def seed_generations(cursor):
    """Pre-populates the Generation dictionary table with baseline data (Gen 1 to Gen 9)."""
    print("Seeding baseline generation dictionaries...")
    generation_data = [
        (1, 'Gen 1'), (2, 'Gen 2'), (3, 'Gen 3'),
        (4, 'Gen 4'), (5, 'Gen 5'), (6, 'Gen 6'),
        (7, 'Gen 7'), (8, 'Gen 8'), (9, 'Gen 9')
    ]
    query = "INSERT IGNORE INTO Generation (generation_id, name) VALUES (%s, %s)"
    cursor.executemany(query, generation_data)
    print(f"✅ Verified/seeded {len(generation_data)} generations.")

def fetch_and_insert_dictionaries(cursor):
    """Fetches all basic dictionaries (Items, Moves, Abilities) using batch operations."""
    endpoints = {
        'Item': 'https://pokeapi.co/api/v2/item?limit=2500',
        'Move': 'https://pokeapi.co/api/v2/move?limit=1500',
        'Ability': 'https://pokeapi.co/api/v2/ability?limit=500'
    }
    
    for table, url in endpoints.items():
        print(f"Fetching {table}s from PokeAPI...")
        response = requests.get(url).json()
        
        batch_data = []
        for result in response['results']:
            entity_id = extract_id_from_url(result['url'])
            clean_name = format_name(result['name']) 
            batch_data.append((entity_id, clean_name))
        
        query = f"INSERT IGNORE INTO {table} ({table.lower()}_id, name) VALUES (%s, %s)"
        cursor.executemany(query, batch_data)
        print(f"✅ Buffered {len(batch_data)} records into {table}.")

def fetch_and_insert_pokemon(cursor):
    """Fetches core forms, base stats, and complete Learnsets from PokeAPI."""
    print("\nFetching Pokémon resources from PokeAPI...")
    
    url = "https://pokeapi.co/api/v2/pokemon?limit=1500"
    response = requests.get(url).json()
    entries = response['results']
    total = len(entries)
    
    print(f"Processing details for {total} baseline and form variants...")
    
    for idx, entry in enumerate(entries, start=1):
        try:
            res = requests.get(entry['url']).json()
            species_id = res['id']
            clean_name = format_name(res['name'])
            
            # 1. Insert Core Species Identity
            cursor.execute("INSERT IGNORE INTO Pokemon (species_id, name) VALUES (%s, %s)", (species_id, clean_name))
            
            # 2. Extract Types and Stats
            type_1 = res['types'][0]['type']['name'].title()
            type_2 = res['types'][1]['type']['name'].title() if len(res['types']) > 1 else None
            stats = {stat['stat']['name']: stat['base_stat'] for stat in res['stats']}
            
            cursor.execute("""
                INSERT IGNORE INTO Pokemon_Generation_Stat 
                (species_id, generation_id, type_1, type_2, base_hp, base_atk, base_def, base_spa, base_spd, base_spe)
                VALUES (%s, 9, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                species_id, type_1, type_2, 
                stats.get('hp', 0), stats.get('attack', 0), stats.get('defense', 0), 
                stats.get('special-attack', 0), stats.get('special-defense', 0), stats.get('speed', 0)
            ))
            
            # 3. Process the Complete Learnset (NEW)
            learnset_data = []
            for move_entry in res.get('moves', []):
                # PokeAPI gives us the direct URL for the move, so we can extract the ID
                # without needing to query our own database to find it!
                move_url = move_entry['move']['url']
                move_id = extract_id_from_url(move_url)
                learnset_data.append((species_id, move_id))
                
            # Batch insert all possible moves for this specific Pokemon
            if learnset_data:
                cursor.executemany("""
                    INSERT IGNORE INTO Pokemon_Learnset (species_id, move_id)
                    VALUES (%s, %s)
                """, learnset_data)
            
            # 4. Progress Tracker
            if idx % 100 == 0 or idx == total:
                print(f"   Progress: {idx}/{total} Pokémon (and their Learnsets) written...")
                
        except Exception as e:
            # Safely skip corrupted or malformed API entries
            pass

# --- MASTER EXECUTION ---
if __name__ == "__main__":
    print("Connecting to database...")
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    
    try:
        seed_generations(cursor)
        fetch_and_insert_dictionaries(cursor)
        fetch_and_insert_pokemon(cursor) 
        
        conn.commit()
        print("\n✅ PokeAPI Data Ingestion Complete! Core dictionaries and full Learnsets are securely mapped.")
    except Exception as e:
        conn.rollback()
        print(f"❌ An error occurred, rollback executed: {e}")
    finally:
        cursor.close()
        conn.close()