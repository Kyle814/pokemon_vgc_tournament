import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
from dotenv import load_dotenv
import umap.umap_ as umap
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
# --- 1. INITIALIZATION & CONFIG ---
load_dotenv()

st.set_page_config(page_title="VGC Meta Analyzer", page_icon="🏆", layout="wide")
st.title("🏆 VGC Analytics Data Warehouse")
st.markdown("Advanced competitive insights driven by automated tournament ETL pipelines.")

# --- 2. CACHED DATABASE CONNECTION ---
@st.cache_resource
def get_db_engine():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    database = os.getenv('DB_NAME')
    db_uri = f"mysql+pymysql://{user}:{password}@{host}/{database}"
    return create_engine(db_uri)

engine = get_db_engine()

# --- 3. CACHED ANALYTICAL QUERIES ---

@st.cache_data
def load_pokemon_usage():
    query = """
        SELECT p.name AS Pokemon, COUNT(tm.member_id) AS Usage_Count
        FROM Team_Member tm
        JOIN Pokemon p ON tm.species_id = p.species_id
        GROUP BY p.species_id, p.name
        ORDER BY Usage_Count DESC;
    """
    return pd.read_sql(query, engine)

@st.cache_data
def load_top_moves():
    query = """
        SELECT 
            m.name AS Move,
            COUNT(tmm.move_id) AS Total_Uses,
            ROUND((COUNT(tmm.move_id) * 100.0) / (SELECT COUNT(*) FROM Team_Member), 2) AS Usage_Percent
        FROM Team_Member_Move tmm
        JOIN Move m ON tmm.move_id = m.move_id
        GROUP BY tmm.move_id, m.name
        ORDER BY Total_Uses DESC;
    """
    return pd.read_sql(query, engine)

@st.cache_data
def load_ability_synergy():
    query = """
        SELECT 
            a.name AS Ability,
            COUNT(tm.member_id) AS Total_Meta_Usage,
            GROUP_CONCAT(DISTINCT p.name SEPARATOR ', ') AS Pokemon_With_Ability
        FROM Team_Member tm
        JOIN Ability a ON tm.ability_id = a.ability_id
        JOIN Pokemon p ON tm.species_id = p.species_id
        GROUP BY a.ability_id, a.name
        ORDER BY Total_Meta_Usage DESC;
    """
    return pd.read_sql(query, engine)

@st.cache_data
def load_hall_of_fame():
    query = """
        SELECT 
            p.handle AS Player,
            p.country AS Country,
            COUNT(tr.tournament_id) AS Tournaments_Played,
            SUM(CASE WHEN tr.placement <= 8 THEN 1 ELSE 0 END) AS Top_8_Finishes,
            MIN(tr.placement) AS Best_Placement
        FROM Player p
        JOIN Tournament_Result tr ON p.player_id = tr.player_id
        GROUP BY p.player_id, p.handle, p.country
        HAVING Top_8_Finishes > 0
        ORDER BY Top_8_Finishes DESC, Best_Placement ASC;
    """
    return pd.read_sql(query, engine)

# Dynamic queries (Not fully cached globally because they depend on UI sliders/inputs)
def scout_stat_tier(min_speed, min_spa):
    query = """
        SELECT p.name AS Pokemon, pgs.base_hp AS HP, pgs.base_atk AS Attack, 
               pgs.base_def AS Defense, pgs.base_spa AS Sp_Attack, 
               pgs.base_spd AS Sp_Defense, pgs.base_spe AS Speed
        FROM Pokemon p
        JOIN Pokemon_Generation_Stat pgs ON p.species_id = pgs.species_id
        WHERE pgs.base_spe >= %s AND pgs.base_spa >= %s
        ORDER BY pgs.base_spe DESC;
    """
    return pd.read_sql(query, engine, params=(min_speed, min_spa))

def scout_role_replacements(move1, move2):
    query = """
        SELECT p.name AS Pokemon
        FROM Pokemon p
        JOIN Pokemon_Learnset pl1 ON p.species_id = pl1.species_id
        JOIN Move m1 ON pl1.move_id = m1.move_id
        JOIN Pokemon_Learnset pl2 ON p.species_id = pl2.species_id
        JOIN Move m2 ON pl2.move_id = m2.move_id
        WHERE m1.name = %s AND m2.name = %s
        ORDER BY p.name ASC;
    """
    return pd.read_sql(query, engine, params=(move1, move2))

@st.cache_data
def get_all_move_names():
    return pd.read_sql("SELECT name FROM Move ORDER BY name ASC;", engine)["name"].tolist()

@st.cache_data
def load_advanced_clustering_data():
    """
    Fetches data with move-pool flattening and Mega/GMax filtering.
    """
    query = """
        SELECT 
            p.species_id,
            p.name AS Pokemon, 
            pgs.type_1, 
            pgs.type_2,
            a.name AS Ability,
            GROUP_CONCAT(DISTINCT m.name SEPARATOR ', ') AS Move_Pool,
            pgs.base_hp AS HP, 
            pgs.base_atk AS Attack, 
            pgs.base_def AS Defense, 
            pgs.base_spa AS Sp_Attack, 
            pgs.base_spd AS Sp_Defense, 
            pgs.base_spe AS Speed
        FROM Pokemon p
        JOIN Pokemon_Generation_Stat pgs ON p.species_id = pgs.species_id
        LEFT JOIN Team_Member tm ON p.species_id = tm.species_id
        LEFT JOIN Ability a ON tm.ability_id = a.ability_id
        LEFT JOIN Pokemon_Learnset pl ON p.species_id = pl.species_id
        LEFT JOIN Move m ON pl.move_id = m.move_id
        WHERE p.name NOT LIKE '%%Mega %%' 
          AND p.name NOT LIKE '%%GMax %%'
          AND pgs.base_hp > 0
        GROUP BY p.species_id, p.name, pgs.type_1, pgs.type_2, a.name, HP, Attack, Defense, Sp_Attack, Sp_Defense, Speed;
    """
    df = pd.read_sql(query, engine)
    df['type_2'] = df['type_2'].fillna('None')
    df['Ability'] = df['Ability'].fillna('Unknown')
    df['Move_Pool'] = df['Move_Pool'].fillna('None')
    return df
# --- 4. DATA PIPELINE UI LAYOUT ---

# Create clean navigation tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Pokémon Usage", 
    "⚔️ Common Moves", 
    "🧬 Ability Synergies", 
    "🏆 Hall of Fame",
    "🎛️ Stat Tier Scout",
    "🔍 Move-Set Role Scout",
    "🤖 ML: UMAP Clustering"
])

# TAB 1: POKEMON USAGE
with tab1:
    st.subheader("Top Used Pokémon Meta-Game Standings")
    df_pokemon = load_pokemon_usage()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(df_pokemon.head(15), use_container_width=True)
    with col2:
        st.bar_chart(data=df_pokemon.head(15).set_index("Pokemon"))

# TAB 2: COMMON MOVES
with tab2:
    st.subheader("Most Frequently Equipped Attacks")
    df_moves = load_top_moves()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(df_moves.head(15), use_container_width=True)
    with col2:
        st.bar_chart(data=df_moves.head(15).set_index("Move")["Total_Uses"])

# TAB 3: ABILITY SYNERGIES
with tab3:
    st.subheader("Active Meta Abilities & Core Species Triggers")
    df_abilities = load_ability_synergy()
    st.dataframe(df_abilities.head(20), use_container_width=True)

# TAB 4: HALL OF FAME (TOP PLAYERS)
with tab4:
    st.subheader("Player Leaderboards: Top 8 Finishes")
    df_players = load_hall_of_fame()
    st.dataframe(df_players, use_container_width=True)

# TAB 5: STAT TIER SCOUT (DYNAMIC SLIDERS)
with tab5:
    st.subheader("Filter Pokémon Species by Minimum Performance Baselines")
    st.markdown("Use the sliders to filter your warehouse for species exceeding specific competitive thresholds.")
    
    col1, col2 = st.columns(2)
    with col1:
        req_speed = st.slider("Minimum Base Speed", min_value=0, max_value=255, value=100)
    with col2:
        req_spa = st.slider("Minimum Base Special Attack", min_value=0, max_value=255, value=120)
        
    df_stats = scout_stat_tier(req_speed, req_spa)
    st.metric(label="Species Matching Criteria", value=len(df_stats))
    st.dataframe(df_stats, use_container_width=True)

# TAB 6: ROLE REPLACEMENT SCOUT (DYNAMIC DROP-DOWNS)
with tab6:
    st.subheader("Identify Alternative Options via Shared Learnsets")
    st.markdown("Select any two moves to query the `Pokemon_Learnset` dictionary and discover every species capable of running that combination.")
    
    all_moves = get_all_move_names()
    
    col1, col2 = st.columns(2)
    with col1:
        selected_move_1 = st.selectbox("Select First Move Slot", options=all_moves, index=all_moves.index("Fake Out") if "Fake Out" in all_moves else 0)
    with col2:
        selected_move_2 = st.selectbox("Select Second Move Slot", options=all_moves, index=all_moves.index("Parting Shot") if "Parting Shot" in all_moves else 0)
        
    if selected_move_1 and selected_move_2:
        df_roles = scout_role_replacements(selected_move_1, selected_move_2)
        st.success(f"Found {len(df_roles)} alternative species capable of learning both **{selected_move_1}** and **{selected_move_2}**.")
        st.dataframe(df_roles, use_container_width=True)
with tab7:
    st.subheader("🤖 ML: Non-Linear Meta-Archetype Projection")
    df_ml = load_advanced_clustering_data()
    num_clusters = st.slider("Number of Archetypes (K)", 2, 8, 3)

    # 1. Scale Stats
    features_num = ["HP", "Attack", "Defense", "Sp_Attack", "Sp_Defense", "Speed"]
    X_num = StandardScaler().fit_transform(df_ml[features_num])
    
    # 2. Encode Categories
    X_cat = pd.get_dummies(df_ml[['type_1', 'type_2', 'Ability', 'Move_Pool']])
    X_combined = pd.concat([pd.DataFrame(X_num), X_cat], axis=1)

    # 3. UMAP Reduction
    reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15)
    embedding = reducer.fit_transform(X_combined)
    
    # 4. Clustering
    df_ml['Cluster_ID'] = KMeans(n_clusters=num_clusters, random_state=42, n_init=10).fit_predict(embedding)
    df_ml['Cluster_Label'] = df_ml['Cluster_ID'].apply(lambda x: f"Archetype {x+1}")
    df_ml['UMAP_X'], df_ml['UMAP_Y'] = embedding[:, 0], embedding[:, 1]

    # 5. Native Streamlit Scatter Chart
    # We set the x and y to our UMAP coordinates and color by Cluster_Label
    st.scatter_chart(
        data=df_ml, 
        x='UMAP_X', 
        y='UMAP_Y', 
        color='Cluster_Label'
    )

    # Inspect results
    selected_cluster = st.selectbox("Inspect Archetype:", sorted(df_ml["Cluster_Label"].unique()))
    st.dataframe(df_ml[df_ml["Cluster_Label"] == selected_cluster][["Pokemon", "Ability"] + features_num], use_container_width=True)