import os
import requests
import mysql.connector
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

# 2. Database Configuration
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
    """PokeAPI returns URLs like 'https://pokeapi.co/api/v2/item/1/'. This extracts the '1'."""
    return int(url.strip('/').split('/')[-1])

def format_name(raw_name):
    """
    Cleans up PokeAPI formatting for your database display.
    Turns 'flutter-mane' into 'Flutter Mane', but protects real hyphens.
    """
    # A whitelist of competitive Pokemon/Moves that actually have hyphens
    KEEP_HYPHENS = {
        "ho-oh", "porygon-z", "jangmo-o", "hakamo-o", "kommo-o", 
        "chien-pao", "wo-chien", "ting-lu", "chi-yu", "ting-lu",
        "u-turn", "v-create", "will-o-wisp", "x-scissor", "freeze-dry", 
        "double-edge", "self-destruct", "baby-doll-eyes"
    }
    
    if raw_name.lower() in KEEP_HYPHENS:
        # Keep the hyphen, just capitalize the letters (e.g., 'U-Turn')
        return raw_name.title()
    else:
        # Replace hyphens with spaces for everything else (e.g., 'Flutter Mane')
        return raw_name.replace('-', ' ').title()

# --- EXTRACTION FUNCTIONS ---
def fetch_and_insert_dictionaries(cursor):
    """Fetches all basic dictionaries (Items, Moves, Abilities)."""
    
    endpoints = {
        'Item': 'https://pokeapi.co/api/v2/item?limit=2500',
        'Move': 'https://pokeapi.co/api/v2/move?limit=1500',
        'Ability': 'https://pokeapi.co/api/v2/ability?limit=500'
    }
    
    for table, url in endpoints.items():
        print(f"Fetching {table}s from PokeAPI...")
        response = requests.get(url).json()
        
        for result in response['results']:
            entity_id = extract_id_from_url(result['url'])
            
            # Use our new smart formatter!
            clean_name = format_name(result['name']) 
            
            cursor.execute(f"INSERT IGNORE INTO {table} ({table.lower()}_id, name) VALUES (%s, %s)", (entity_id, clean_name))

def fetch_and_insert_pokemon(cursor, limit=1025):
    """Fetches Pokemon names, types, and stats."""
    print(f"\nFetching {limit} Pokémon stats (This will take a minute or two...)")
    
    cursor.execute("INSERT IGNORE INTO Generation (generation_id, name) VALUES (9, 'Scarlet/Violet')")
    
    for i in range(1, limit + 1):
        try:
            res = requests.get(f"https://pokeapi.co/api/v2/pokemon/{i}").json()
            
            species_id = res['id']
            
            # Use our new smart formatter!
            clean_name = format_name(res['name'])
            
            cursor.execute("INSERT IGNORE INTO Pokemon (species_id, name) VALUES (%s, %s)", (species_id, clean_name))
            
            # Parse Types
            type_1 = res['types'][0]['type']['name'].title()
            type_2 = None 
            if len(res['types']) > 1:
                type_2 = res['types'][1]['type']['name'].title()
                
            # Parse Stats
            stats = {stat['stat']['name']: stat['base_stat'] for stat in res['stats']}
            
            # Insert Versioned Stats for Gen 9
            cursor.execute("""
                INSERT IGNORE INTO Pokemon_Generation_Stat 
                (species_id, generation_id, type_1, type_2, base_hp, base_atk, base_def, base_spa, base_spd, base_spe)
                VALUES (%s, 9, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                species_id, type_1, type_2, 
                stats['hp'], stats['attack'], stats['defense'], 
                stats['special-attack'], stats['special-defense'], stats['speed']
            ))
            
            if i % 100 == 0:
                print(f"Processed {i}/{limit} Pokémon...")
                
        except Exception as e:
            print(f"Failed to process Pokemon ID {i}: {e}")

# --- MASTER EXECUTION ---
if __name__ == "__main__":
    print("Connecting to database...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        fetch_and_insert_dictionaries(cursor)
        fetch_and_insert_pokemon(cursor, limit=1025) 
        
        conn.commit()
        print("\n✅ PokeAPI Data Ingestion Complete! Your dictionary tables are beautifully formatted.")
    except Exception as e:
        conn.rollback()
        print(f"An error occurred: {e}")
    finally:
        cursor.close()
        conn.close()