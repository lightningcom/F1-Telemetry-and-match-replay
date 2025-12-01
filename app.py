import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import os
import requests
from fastf1.ergast import Ergast

# Page Config
st.set_page_config(page_title="F1 Realtime Dashboard", page_icon="🏎️", layout="wide")

# Custom CSS
st.markdown("""
<style>
    h1, h2, h3 {
        color: #ff1801 !important; /* F1 Red */
        font-family: 'Arial', sans-serif;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .metric-card {
        padding: 20px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #ff1801;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.7;
    }
    
    /* Calendar Card Styles */
    .calendar-card {
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-left: 5px solid #ff1801;
        transition: transform 0.2s;
    }
    .calendar-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.1);
    }
    .calendar-round {
        font-size: 0.8em;
        opacity: 0.7;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }
    .calendar-date {
        font-weight: bold;
        color: #ff1801;
        font-size: 1.1em;
        margin-bottom: 8px;
    }
    .calendar-event {
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 4px;
    }
    .calendar-location {
        font-size: 0.9em;
        opacity: 0.8;
        display: flex;
        align-items: center;
        gap: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Cache Setup
CACHE_DIR = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)

# --- Helper Functions ---

@st.cache_data
def fetch_ergast_results(entity_type, entity_id):
    # entity_type: 'drivers' or 'constructors'
    # Use Jolpica mirror as Ergast is deprecated/unreliable
    base_url = f"https://api.jolpi.ca/ergast/f1/{entity_type}/{entity_id}/results.json"
    
    all_results = []
    limit = 100
    offset = 0
    
    try:
        while True:
            url = f"{base_url}?limit={limit}&offset={offset}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                break
            
            data = r.json()
            races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
            
            if not races:
                break
                
            # Count total results in this batch
            batch_results_count = 0
            for race in races:
                base_info = {
                    'season': int(race['season']),
                    'round': int(race['round']),
                    'raceName': race['raceName'],
                    'date': race['date']
                }
                
                race_results = race.get('Results', [])
                batch_results_count += len(race_results)
                
                for result in race_results:
                    row = base_info.copy()
                    row.update({
                        'position': int(result['position']),
                        'positionText': result['positionText'],
                        'points': float(result['points']),
                        'grid': int(result['grid']),
                        'laps': int(result['laps']),
                        'status': result['status'],
                        'driverId': result['Driver']['driverId'],
                        'constructorId': result['Constructor']['constructorId']
                    })
                    all_results.append(row)
            
            # Check if we are done based on results count
            if batch_results_count < limit:
                break
                
            offset += limit # Increment by limit as we requested 'limit' results
            if offset > 10000: # Increased safety break for teams with many entries
                break
        
        return pd.DataFrame(all_results)
    except Exception as e:
        st.error(f"API Error: {e}")
        return pd.DataFrame()

@st.cache_data
def get_lookup_tables_v2():
    try:
        ergast = Ergast()
        # Fetch all drivers
        all_drivers = []
        limit = 100
        offset = 0
        while True:
            try:
                resp = ergast.get_driver_info(limit=limit, offset=offset)
                chunk = resp if isinstance(resp, pd.DataFrame) else (pd.concat(resp.content) if hasattr(resp, 'content') and resp.content else pd.DataFrame())
                if chunk.empty: break
                all_drivers.append(chunk)
                if len(chunk) < limit: break
                offset += limit
            except Exception: break
        d_df = pd.concat(all_drivers).drop_duplicates(subset=['driverId']) if all_drivers else pd.DataFrame()

        # Fetch all constructors
        all_constructors = []
        offset = 0
        while True:
            try:
                resp = ergast.get_constructor_info(limit=limit, offset=offset)
                chunk = resp if isinstance(resp, pd.DataFrame) else (pd.concat(resp.content) if hasattr(resp, 'content') and resp.content else pd.DataFrame())
                if chunk.empty: break
                all_constructors.append(chunk)
                if len(chunk) < limit: break
                offset += limit
            except Exception: break
        c_df = pd.concat(all_constructors).drop_duplicates(subset=['constructorId']) if all_constructors else pd.DataFrame()
        
        return d_df, c_df
    except Exception as e:
        st.error(f"Error fetching lookup tables: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data
def fetch_season_standings(year):
    try:
        ergast = Ergast()
        # Driver Standings
        d_resp = ergast.get_driver_standings(season=year, limit=1)
        d_standings = d_resp.content[0] if d_resp.content else pd.DataFrame()
        
        # Constructor Standings
        c_resp = ergast.get_constructor_standings(season=year, limit=1)
        c_standings = c_resp.content[0] if c_resp.content else pd.DataFrame()
        
        return d_standings, c_standings
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# --- UI Components ---

def render_session_selector():
    st.sidebar.title("Session Controls")
    
    current_year = datetime.now().year
    
    # Determine default year from loaded session if available
    default_year_idx = 1
    if 'session' in st.session_state:
        try:
            loaded_year = int(st.session_state['session'].event.year)
            years_list = list(range(current_year + 1, 2018, -1))
            if loaded_year in years_list:
                default_year_idx = years_list.index(loaded_year)
        except:
            pass

    year = st.sidebar.selectbox("Year", range(current_year + 1, 2018, -1), index=default_year_idx)
    
    # Get Schedule
    try:
        schedule = fastf1.get_event_schedule(year)
        events = schedule[schedule['EventFormat'] != 'testing']
        
        today = pd.Timestamp.now(tz='UTC')
        past_events = events[events['Session5Date'] < today]
        
        # Determine default event index
        default_index = len(past_events) - 1 if not past_events.empty else 0
        if default_index < 0: default_index = 0
        
        event_names = events['EventName'].tolist()
        
        # Sync event selection with loaded session if years match
        if 'session' in st.session_state and st.session_state['session'].event.year == year:
            try:
                loaded_event = st.session_state['session'].event.EventName
                if loaded_event in event_names:
                    default_index = event_names.index(loaded_event)
            except:
                pass
        
        if not event_names:
            st.sidebar.warning(f"No events found for {year}.")
            selected_event_name = None
        else:
            selected_event_name = st.sidebar.selectbox("Grand Prix", event_names, index=default_index)
        
        if selected_event_name:
            event_schedule = events[events['EventName'] == selected_event_name].iloc[0]
            available_sessions = []
            for i in range(1, 6):
                sess_name = event_schedule[f'Session{i}']
                if sess_name:
                    available_sessions.append(sess_name)
            
            selected_session_name = st.sidebar.selectbox("Session", available_sessions, index=len(available_sessions)-1)
            
            if st.sidebar.button("Load Session Data", type="primary", use_container_width=True):
                with st.spinner(f"Loading data for {selected_event_name} - {selected_session_name}..."):
                    try:
                        session = fastf1.get_session(year, selected_event_name, selected_session_name)
                        session.load()
                        st.session_state['session'] = session
                        st.session_state['loaded_event'] = f"{selected_event_name} - {selected_session_name}"
                        st.success("Data Loaded Successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load data: {e}")
        
        return year, schedule
        
    except Exception as e:
        st.error(f"Could not fetch schedule: {e}")
        return year, None

def render_header_stats(year):
    d_standings, c_standings = fetch_season_standings(year)
    
    if not d_standings.empty and not c_standings.empty:
        try:
            top_driver = d_standings.iloc[0]
            top_team = c_standings.iloc[0]
            
            d_name = f"{top_driver['givenName']} {top_driver['familyName']}"
            d_points = top_driver['points']
            d_wins = top_driver['wins']
            
            c_name = top_team['constructorName']
            c_points = top_team['points']
            c_wins = top_team['wins']
            
            st.markdown(f"""
            <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #333; display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap;">
                <div style="text-align: center;">
                    <h3 style="margin: 0; color: #ff1801; font-size: 1.2em;">🏆 {year} Leader</h3>
                    <div style="font-size: 1.5em; font-weight: bold; color: white;">{d_name}</div>
                    <div style="font-size: 0.9em; opacity: 0.8; color: #ccc;">{d_points} PTS | {d_wins} Wins</div>
                </div>
                <div style="height: 40px; width: 1px; background-color: #444; margin: 0 20px;"></div>
                <div style="text-align: center;">
                    <h3 style="margin: 0; color: #ff1801; font-size: 1.2em;">🛠️ Top Team</h3>
                    <div style="font-size: 1.5em; font-weight: bold; color: white;">{c_name}</div>
                    <div style="font-size: 0.9em; opacity: 0.8; color: #ccc;">{c_points} PTS | {c_wins} Wins</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            pass

def render_championship_view(year, schedule):
    st.markdown(f"## {year} Championship Overview")
    
    # 1. Calendar
    if schedule is not None and not schedule.empty:
        st.subheader("📅 Race Calendar")
        
        # Sort: Latest Round first (Descending order of RoundNumber)
        events_to_show = schedule.sort_values(by='RoundNumber', ascending=False)
        
        # Grid layout
        cols = st.columns(3)
        
        # Custom CSS for the HTML cards
        st.markdown("""
        <style>
        a.race-card-link {
            text-decoration: none;
            color: inherit !important;
            display: block;
            height: 100%;
            margin-bottom: 20px;
        }
        .race-card {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-left: 5px solid #ff1801;
            border-radius: 12px;
            padding: 25px;
            height: 200px; /* Increased height for better spacing */
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .race-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
            border-color: #ff1801;
        }
        .race-round {
            font-size: 0.85em;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 10px;
        }
        .race-date {
            font-size: 1.1em;
            color: #ff1801;
            font-weight: bold;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .race-name {
            font-size: 1.4em;
            font-weight: bold;
            color: white;
            line-height: 1.3;
            margin-bottom: auto;
        }
        .race-loc {
            font-size: 0.95em;
            color: #ccc;
            margin-top: 20px;
            display: flex;
            align-items: center;
            gap: 6px;
            opacity: 0.8;
        }
        </style>
        """, unsafe_allow_html=True)

        for i, (idx, row) in enumerate(events_to_show.iterrows()):
            col = cols[i % 3]
            with col:
                try:
                    # Convert to IST
                    ts = row['Session5Date']
                    if ts.tzinfo is None:
                        ts = ts.tz_localize('UTC')
                    
                    ts_ist = ts.tz_convert('Asia/Kolkata')
                    date_str = ts_ist.strftime('%d %b %Y')
                    time_str = ts_ist.strftime('%I:%M %p IST')
                except Exception as e:
                    date_str = str(row['Session5Date'])
                    time_str = ""
                
                # URL Encode event name
                import urllib.parse
                safe_event = urllib.parse.quote(row['EventName'])
                
                st.markdown(f"""
                <a href="?load_event={safe_event}&load_year={year}" class="race-card-link" target="_self">
                    <div class="race-card">
                        <div>
                            <div class="race-round">ROUND {row['RoundNumber']}</div>
                            <div class="race-date">
                                <span>🗓️ {date_str}</span>
                                <span style="font-size: 0.85em; color: #ccc; margin-left: 10px; font-weight: normal;">⏰ {time_str}</span>
                            </div>
                            <div class="race-name">{row['EventName']}</div>
                        </div>
                        <div class="race-loc">📍 {row['Location']}, {row['Country']}</div>
                    </div>
                </a>
                """, unsafe_allow_html=True)
    
    st.info("Standings data coming soon...")

def render_search_ui(search_query):
    if not search_query:
        return

    st.subheader(f"Results for '{search_query}'")
    
    with st.spinner("Searching database..."):
        drivers_df, constructors_df = get_lookup_tables_v2()
        
        if drivers_df.empty:
            st.error("Drivers database is empty! Check API connection.")
        
        if not drivers_df.empty:
            drivers_df['fullName'] = drivers_df['givenName'] + ' ' + drivers_df['familyName']
        
        # Filter Drivers
        if not drivers_df.empty:
            query_lower = search_query.lower()
            matches = []
            query_parts = query_lower.split()
            
            for idx, row in drivers_df.iterrows():
                given = str(row['givenName']).lower()
                family = str(row['familyName']).lower()
                did = str(row['driverId']).lower()
                full = str(row['fullName']).lower()
                search_text = f"{given} {family} {did} {full}"
                if all(part in search_text for part in query_parts):
                    matches.append(row)
            
            d_matches = pd.DataFrame(matches) if matches else pd.DataFrame()
        else:
            d_matches = pd.DataFrame()
            
        # Filter Constructors
        if not constructors_df.empty:
            c_matches = constructors_df[
                constructors_df['constructorName'].str.contains(search_query, case=False, na=False) |
                constructors_df['constructorId'].str.contains(search_query, case=False, na=False)
            ]
        else:
            c_matches = pd.DataFrame()
        
        if d_matches.empty and c_matches.empty:
            st.warning("No matches found.")
        else:
            if not d_matches.empty:
                st.markdown("### 🏎️ Drivers Found")
                for idx, row in d_matches.iterrows():
                    with st.expander(f"{row['givenName']} {row['familyName']} ({row['driverNationality']})"):
                        with st.spinner(f"Fetching career stats for {row['givenName']}..."):
                            try:
                                res_df = fetch_ergast_results('drivers', row['driverId'])
                                ergast = Ergast()
                                qual_resp = ergast.get_qualifying_results(driver=row['driverId'], limit=1000)
                                qual_df = pd.concat(qual_resp.content) if qual_resp.content else pd.DataFrame()
                                
                                if not res_df.empty:
                                    total_races = len(res_df)
                                    wins = len(res_df[res_df['position'] == 1])
                                    podiums = len(res_df[res_df['position'].isin([1, 2, 3])])
                                    total_points = res_df['points'].sum()
                                    poles = len(qual_df[qual_df['position'] == 1]) if not qual_df.empty else 0
                                    
                                    col1, col2, col3, col4 = st.columns(4)
                                    col1.metric("Total Races", total_races)
                                    col2.metric("Wins 🏆", wins)
                                    col3.metric("Podiums 🍾", podiums)
                                    col4.metric("Pole Positions ⏱️", poles)
                                    st.metric("Career Points", f"{total_points:g}")
                                    
                                    st.caption("Recent Race Results")
                                    if 'season' in res_df.columns and 'round' in res_df.columns:
                                        res_df = res_df.sort_values(by=['season', 'round'], ascending=False)
                                    st.dataframe(res_df[['season', 'round', 'raceName', 'position', 'points', 'status']].head(10), use_container_width=True)
                                else:
                                    st.info("No race results found.")
                            except Exception as e:
                                st.error(f"Error fetching stats: {e}")

            if not c_matches.empty:
                st.markdown("### 🛠️ Teams Found")
                for idx, row in c_matches.iterrows():
                    with st.expander(f"{row['constructorName']} ({row['constructorNationality']})"):
                        with st.spinner(f"Fetching history for {row['constructorName']}..."):
                            try:
                                res_df = fetch_ergast_results('constructors', row['constructorId'])
                                
                                if not res_df.empty:
                                    total_entries = len(res_df)
                                    wins = len(res_df[res_df['position'] == 1])
                                    podiums = len(res_df[res_df['position'].isin([1, 2, 3])])
                                    total_points = res_df['points'].sum()
                                    col1, col2, col3 = st.columns(3)
                                    col1.metric("Race Entries", total_entries)
                                    col2.metric("Wins 🏆", wins)
                                    col3.metric("Podiums 🍾", podiums)
                                    st.metric("Total Points", f"{total_points:g}")
                                    st.caption("Recent Results")
                                    if 'season' in res_df.columns and 'round' in res_df.columns:
                                        res_df = res_df.sort_values(by=['season', 'round'], ascending=False)
                                    st.dataframe(res_df[['season', 'round', 'raceName', 'driverId', 'position', 'points']].head(10), use_container_width=True)
                                else:
                                    st.info("No results found.")
                            except Exception as e:
                                st.error(f"Error fetching team stats: {e}")

# --- Tab Render Functions ---

def render_results_tab(session):
    st.subheader("Session Results")
    if hasattr(session, 'results'):
        results = session.results
        display_cols = ['Position', 'FullName', 'DriverNumber', 'TeamName', 'Time', 'Status', 'Points']
        cols = [c for c in display_cols if c in results.columns]
        results_display = results[cols].copy()
        results_display['Time'] = results_display['Time'].astype(str).str.replace('0 days ', '')
        st.dataframe(results_display, use_container_width=True)
    else:
        st.info("No results available for this session yet.")

def render_telemetry_tab(session):
    st.subheader("Driver Telemetry Analysis")
    driver_map = session.results.set_index('FullName')['Abbreviation'].to_dict()
    drivers = list(driver_map.keys())
    selected_drivers = st.multiselect("Select Drivers to Compare", drivers, default=drivers[:2] if len(drivers) >= 2 else drivers)
    
    if selected_drivers:
        fig_speed = go.Figure()
        fig_throttle = go.Figure()
        fig_brake = go.Figure()
        fig_rpm = go.Figure()
        fig_gear = go.Figure()
        fig_drs = go.Figure()
        
        # Calculate Sector Lines (based on first driver)
        sector_lines = []
        try:
            ref_driver = driver_map[selected_drivers[0]]
            ref_lap = session.laps.pick_driver(ref_driver).pick_fastest()
            if ref_lap is not None:
                ref_tel = ref_lap.get_telemetry()
                # Get Sector Times
                s1_time = ref_lap['Sector1SessionTime']
                s2_time = ref_lap['Sector2SessionTime']
                
                # Find corresponding distances
                if not pd.isnull(s1_time):
                    s1_dist = ref_tel.loc[(ref_tel['SessionTime'] - s1_time).abs().idxmin(), 'Distance']
                    sector_lines.append((s1_dist, "Sector 1"))
                if not pd.isnull(s2_time):
                    s2_dist = ref_tel.loc[(ref_tel['SessionTime'] - s2_time).abs().idxmin(), 'Distance']
                    sector_lines.append((s2_dist, "Sector 2"))
        except:
            pass

        for driver_name in selected_drivers:
            driver_abbr = driver_map[driver_name]
            try:
                laps = session.laps.pick_driver(driver_abbr)
                fastest_lap = laps.pick_fastest()
                if fastest_lap is not None:
                    tel = fastest_lap.get_telemetry()
                    try:
                        team_name = session.results.loc[session.results['Abbreviation'] == driver_abbr, 'TeamName'].iloc[0]
                        color = fastf1.plotting.get_team_color(team_name, session=session)
                    except:
                        color = None
                    
                    fig_speed.add_trace(go.Scatter(x=tel['Distance'], y=tel['Speed'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
                    fig_throttle.add_trace(go.Scatter(x=tel['Distance'], y=tel['Throttle'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
                    fig_brake.add_trace(go.Scatter(x=tel['Distance'], y=tel['Brake'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
                    fig_rpm.add_trace(go.Scatter(x=tel['Distance'], y=tel['RPM'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
                    fig_gear.add_trace(go.Scatter(x=tel['Distance'], y=tel['nGear'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
                    fig_drs.add_trace(go.Scatter(x=tel['Distance'], y=tel['DRS'], mode='lines', name=f'{driver_name}', line=dict(color=color)))
            except Exception as e:
                st.warning(f"Could not load telemetry for {driver_name}: {e}")
        
        # Helper to add sector lines
        def add_sector_lines(fig):
            for dist, label in sector_lines:
                fig.add_vline(x=dist, line_width=1, line_dash="dash", line_color="gray")
                fig.add_annotation(x=dist, y=1, yref="paper", text=label, showarrow=False, font=dict(color="gray"))

        add_sector_lines(fig_speed)
        fig_speed.update_layout(title="Speed Trace", xaxis_title="Distance (m)", yaxis_title="Speed (km/h)")
        st.plotly_chart(fig_speed, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            add_sector_lines(fig_throttle)
            fig_throttle.update_layout(title="Throttle Trace", xaxis_title="Distance (m)", yaxis_title="Throttle %")
            st.plotly_chart(fig_throttle, use_container_width=True)
        with col2:
            add_sector_lines(fig_brake)
            fig_brake.update_layout(title="Brake Trace", xaxis_title="Distance (m)", yaxis_title="Brake")
            st.plotly_chart(fig_brake, use_container_width=True)
            
        col3, col4 = st.columns(2)
        with col3:
            add_sector_lines(fig_rpm)
            fig_rpm.update_layout(title="RPM Trace", xaxis_title="Distance (m)", yaxis_title="RPM")
            st.plotly_chart(fig_rpm, use_container_width=True)
        with col4:
            add_sector_lines(fig_gear)
            fig_gear.update_layout(title="Gear Trace", xaxis_title="Distance (m)", yaxis_title="Gear")
            st.plotly_chart(fig_gear, use_container_width=True)
            
        add_sector_lines(fig_drs)
        fig_drs.update_layout(title="DRS Trace", xaxis_title="Distance (m)", yaxis_title="DRS Status")
        st.plotly_chart(fig_drs, use_container_width=True)

def render_lap_comparison_tab(session):
    st.subheader("Lap Time Comparison")
    laps = session.laps
    valid_laps = laps.pick_quicklaps()
    
    if not valid_laps.empty:
        # 1. Box Plot
        valid_laps['LapTimeSeconds'] = valid_laps['LapTime'].dt.total_seconds()
        fig_laps = px.box(valid_laps, x="Team", y="LapTimeSeconds", color="Team", title="Lap Time Distribution by Team")
        st.plotly_chart(fig_laps, use_container_width=True)
        
        # 2. Scatter Plot
        driver_map_reverse = session.results.set_index('Abbreviation')['FullName'].to_dict()
        valid_laps['DriverName'] = valid_laps['Driver'].map(driver_map_reverse)
        fig_scatter = px.scatter(valid_laps, x="LapNumber", y="LapTimeSeconds", color="DriverName", title="Lap Times per Lap")
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        # 3. Head-to-Head Table
        st.markdown("### ⚔️ Head-to-Head Analysis")
        drivers = list(driver_map_reverse.values())
        d_abbr_map = {v: k for k, v in driver_map_reverse.items()}
        
        col1, col2 = st.columns(2)
        with col1:
            d1_name = st.selectbox("Driver 1", drivers, index=0)
        with col2:
            d2_name = st.selectbox("Driver 2", drivers, index=1 if len(drivers) > 1 else 0)
            
        if d1_name and d2_name and d1_name != d2_name:
            d1_abbr = d_abbr_map[d1_name]
            d2_abbr = d_abbr_map[d2_name]
            
            laps_d1 = valid_laps[valid_laps['Driver'] == d1_abbr][['LapNumber', 'LapTimeSeconds']].set_index('LapNumber')
            laps_d2 = valid_laps[valid_laps['Driver'] == d2_abbr][['LapNumber', 'LapTimeSeconds']].set_index('LapNumber')
            
            # Join
            df_compare = laps_d1.join(laps_d2, lsuffix='_d1', rsuffix='_d2').dropna()
            
            if not df_compare.empty:
                df_compare['Delta'] = df_compare['LapTimeSeconds_d1'] - df_compare['LapTimeSeconds_d2']
                df_compare['Winner'] = df_compare['Delta'].apply(lambda x: d2_name if x > 0 else d1_name)
                df_compare['Gap'] = df_compare['Delta'].abs().apply(lambda x: f"{x:.3f}s")
                
                # Format for display
                display_df = df_compare.reset_index()
                display_df = display_df[['LapNumber', 'Winner', 'Gap', 'LapTimeSeconds_d1', 'LapTimeSeconds_d2']]
                display_df.columns = ['Lap', 'Winner', 'Gap', f'{d1_name} Time', f'{d2_name} Time']
                
                st.dataframe(display_df, use_container_width=True)
                
                # Visualization of the Delta
                fig_delta = px.bar(
                    df_compare.reset_index(), 
                    x='LapNumber', 
                    y='Delta', 
                    color='Winner',
                    title=f"Lap Time Delta: {d1_name} vs {d2_name}",
                    labels={'Delta': 'Time Delta (s)', 'LapNumber': 'Lap Number'},
                    color_discrete_map={d1_name: '#ff1801', d2_name: '#1f77b4'} # Example colors
                )
                # Add a reference line at 0
                fig_delta.add_hline(y=0, line_width=1, line_color="white")
                
                # Update layout for better readability
                fig_delta.update_layout(
                    yaxis_title=f"Gap (s) - < 0: {d1_name} Faster | > 0: {d2_name} Faster",
                    legend_title="Lap Winner"
                )
                
                st.plotly_chart(fig_delta, use_container_width=True)
            else:
                st.info("No overlapping clean laps found for comparison.")

def render_track_map_tab(session, selected_event_name):
    st.subheader("Track Map")
    try:
        lap = session.laps.pick_fastest()
        if lap is not None:
            tel = lap.get_telemetry()
            
            # Define Sector Boundaries
            t_s1 = lap['Sector1SessionTime']
            t_s2 = lap['Sector2SessionTime']
            
            fig_map = go.Figure()
            
            # Check if sector times are available
            if pd.isnull(t_s1) or pd.isnull(t_s2):
                # Fallback to single color
                fig_map.add_trace(go.Scatter(x=tel['X'], y=tel['Y'], mode='lines', line=dict(width=6, color='white'), name='Track'))
            else:
                # Sector 1: Start to S1 Time
                # We include points up to the boundary to ensure connectivity
                mask_s1 = tel['SessionTime'] <= t_s1
                # Append the first point of the next sector to close the gap? 
                # Actually, filtering <= t_s1 gets us points. The next point > t_s1.
                # To be safe, we can just plot them. Visually it should be fine if high res.
                # Better: Use >= and <= with overlaps.
                
                s1_tel = tel[tel['SessionTime'] <= t_s1]
                s2_tel = tel[(tel['SessionTime'] >= t_s1) & (tel['SessionTime'] <= t_s2)]
                s3_tel = tel[tel['SessionTime'] >= t_s2]
                
                fig_map.add_trace(go.Scatter(x=s1_tel['X'], y=s1_tel['Y'], mode='lines', 
                                             line=dict(width=6, color='#ff1801'), name='Sector 1'))
                
                fig_map.add_trace(go.Scatter(x=s2_tel['X'], y=s2_tel['Y'], mode='lines', 
                                             line=dict(width=6, color='#00ffff'), name='Sector 2'))
                
                fig_map.add_trace(go.Scatter(x=s3_tel['X'], y=s3_tel['Y'], mode='lines', 
                                             line=dict(width=6, color='#ffff00'), name='Sector 3'))

            fig_map.update_layout(
                title=f"Track Map - {selected_event_name} (Sectors)",
                template="plotly_dark",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(visible=False, showgrid=False),
                yaxis=dict(visible=False, showgrid=False, scaleanchor="x", scaleratio=1),
                height=600,
                showlegend=True,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0.5)")
            )
            st.plotly_chart(fig_map, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not generate track map: {e}")

def render_replay_tab(session):
    st.subheader("Race Replay Animation")
    
    # 1. Selection Controls
    col1, col2 = st.columns([1, 2])
    with col1:
        total_laps = int(session.laps['LapNumber'].max())
        lap_options = ["Full Race"] + list(range(1, total_laps + 1))
        selected_lap = st.selectbox("Select Lap", lap_options, index=1) # Default to Lap 1
    
    with col2:
        driver_map = session.results.set_index('FullName')['Abbreviation'].to_dict()
        all_drivers = list(driver_map.keys())
        default_drivers = all_drivers[:5] if len(all_drivers) >= 5 else all_drivers
        replay_drivers = st.multiselect("Select Drivers", all_drivers, default=default_drivers)
    
    focus_driver = st.selectbox("Focus Driver (Camera/Telemetry)", replay_drivers, index=0 if replay_drivers else None)
    
    if not replay_drivers or not focus_driver:
        st.info("Please select drivers to generate the replay.")
        return

    if st.button("Generate Replay", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner("Processing telemetry data..."):
                # 1. Setup Reference (Track Map)
                status_text.text("Building track map...")
                ref_lap = session.laps.pick_fastest()
                if ref_lap is None:
                    ref_lap = session.laps.iloc[0]
                
                ref_tel = ref_lap.get_telemetry()
                track_x = ref_tel['X']
                track_y = ref_tel['Y']
                
                # 2. Define Time Grid
                if selected_lap == "Full Race":
                    # For full race, we need a coarser grid to avoid crashing the browser
                    start_t = session.laps['LapStartTime'].min().total_seconds()
                    end_t = session.laps['Time'].max().total_seconds()
                    duration = end_t - start_t
                    step = 5.0 if duration > 3600 else 2.0 # Adaptive step
                    time_grid = np.arange(start_t, end_t, step)
                else:
                    # For single lap, get the specific lap duration of the focus driver
                    f_abbr = driver_map[focus_driver]
                    f_laps = session.laps.pick_driver(f_abbr)
                    specific_lap = f_laps[f_laps['LapNumber'] == selected_lap]
                    
                    if specific_lap.empty:
                        st.error(f"Driver {focus_driver} did not complete Lap {selected_lap}.")
                        return
                        
                    lap_duration = specific_lap['LapTime'].iloc[0].total_seconds()
                    # Add a buffer
                    time_grid = np.arange(0, lap_duration + 2.0, 0.4) # 0.4s resolution for smooth playback

                # 3. Fetch and Interpolate Data
                interpolated_data = {}
                
                total_drivers = len(replay_drivers)
                for i, d_name in enumerate(replay_drivers):
                    status_text.text(f"Processing {d_name} ({i+1}/{total_drivers})...")
                    progress_bar.progress((i + 1) / total_drivers)
                    
                    abbr = driver_map[d_name]
                    try:
                        d_laps = session.laps.pick_driver(abbr)
                        
                        if selected_lap == "Full Race":
                            tel = d_laps.get_telemetry()
                            tel['TimeSec'] = tel['SessionTime'].dt.total_seconds()
                        else:
                            # Filter for specific lap
                            lap_data = d_laps[d_laps['LapNumber'] == selected_lap]
                            if lap_data.empty:
                                continue
                            tel = lap_data.iloc[0].get_telemetry()
                            tel['TimeSec'] = tel['Time'].dt.total_seconds()
                        
                        # Optimize: Only keep necessary columns and drop NaNs
                        tel = tel[['TimeSec', 'X', 'Y', 'Speed', 'nGear', 'DRS', 'Distance', 'LapNumber']].dropna()
                        
                        # Interpolation
                        t_orig = tel['TimeSec'].values
                        
                        # Safe interpolation
                        x_new = np.interp(time_grid, t_orig, tel['X'].values, left=np.nan, right=np.nan)
                        y_new = np.interp(time_grid, t_orig, tel['Y'].values, left=np.nan, right=np.nan)
                        dist_new = np.interp(time_grid, t_orig, tel['Distance'].values, left=0, right=np.nan)
                        speed_new = np.interp(time_grid, t_orig, tel['Speed'].values, left=0, right=0)
                        
                        # Nearest neighbor for categorical/discrete
                        idx = np.searchsorted(t_orig, time_grid, side='right') - 1
                        idx = np.clip(idx, 0, len(t_orig)-1)
                        gear_new = tel['nGear'].values[idx]
                        drs_new = tel['DRS'].values[idx]
                        interpolated_data[d_name] = pd.DataFrame({
                            'X': x_new, 'Y': y_new, 'Distance': dist_new, 
                            'Speed': speed_new, 'nGear': gear_new, 'DRS': drs_new
                        })
                        
                    except Exception as e:
                        continue

                status_text.text("Generating animation frames...")
                
                # --- Animation Frames ---
                frames = []
                
                # Pre-calculate ranges for Follow Cam
                window_size = 1000 # meters
                
                # Trail settings
                trail_length = 5
                
                # Drivers to plot
                drivers_to_plot = list(interpolated_data.keys())
                
                for i, t in enumerate(time_grid):
                    frame_x = []
                    frame_y = []
                    frame_colors = []
                    frame_sizes = []
                    frame_opacities = []
                    frame_hover = []
                    
                    # Leaderboard Data for this frame
                    current_positions = []
                    
                    # Focus Driver Pos for Camera
                    focus_x, focus_y = None, None
                    
                    for drv in drivers_to_plot:
                        df = interpolated_data[drv]
                        try:
                            # We can use index i directly as we interpolated to time_grid
                            if i < len(df):
                                row = df.iloc[i]
                                if not pd.isna(row['X']) and not pd.isna(row['Y']):
                                    # Current Position
                                    curr_x = row['X']
                                    curr_y = row['Y']
                                    
                                    # Store for Leaderboard
                                    dist = row['Distance']
                                    current_positions.append({
                                        'Driver': drv,
                                        'Distance': dist,
                                        'Speed': row['Speed'],
                                        'Gap': 0 # Placeholder
                                    })
                                    
                                    if drv == focus_driver:
                                        focus_x, focus_y = curr_x, curr_y
                                    
                                    # --- TRAIL GENERATION ---
                                    # Add current point (Head)
                                    frame_x.append(curr_x)
                                    frame_y.append(curr_y)
                                    
                                    # Get color
                                    abbr = driver_map[drv]
                                    team_name = session.results.loc[session.results['Abbreviation'] == abbr, 'TeamName'].iloc[0]
                                    color = fastf1.plotting.get_team_color(team_name, session=session)
                                    
                                    frame_colors.append(color)
                                    frame_sizes.append(14 if drv == focus_driver else 10)
                                    frame_opacities.append(1.0)
                                    
                                    # Hover Text
                                    hover_txt = f"<b>{drv}</b><br>Speed: {row['Speed']:.0f} km/h<br>Gear: {row['nGear']:.0f}<br>DRS: {row['DRS']}"
                                    frame_hover.append(hover_txt)
                                    
                                    # Add Trail Points (Tail)
                                    for j in range(1, trail_length + 1):
                                        if i - j >= 0:
                                            prev_row = df.iloc[i - j]
                                            if not pd.isna(prev_row['X']):
                                                frame_x.append(prev_row['X'])
                                                frame_y.append(prev_row['Y'])
                                                # Same color
                                                frame_colors.append(color)
                                                # Smaller and Fader
                                                frame_sizes.append((14 if drv == focus_driver else 10) * (1 - j/(trail_length+1)))
                                                frame_opacities.append(1.0 - (j / (trail_length + 1)))
                                                frame_hover.append(hover_txt) # Same hover for trail
                                                
                        except IndexError:
                            pass
                    
                    # Sort positions for leaderboard
                    current_positions.sort(key=lambda x: x['Distance'], reverse=True)
                    
                    # Calculate Gaps (approximate based on distance)
                    if current_positions:
                        leader_dist = current_positions[0]['Distance']
                        for p in current_positions:
                            p['Gap'] = (leader_dist - p['Distance']) / 200.0 # Rough approx seconds
                    
                    # Build Leaderboard Text
                    lb_text = "<b>LEADERBOARD</b><br>"
                    for p in current_positions[:10]: # Top 10
                        gap_str = f"+{p['Gap']:.1f}s" if p['Gap'] > 0 else "LEADER"
                        lb_text += f"{p['Driver']} {gap_str}<br>"
                    
                    # Telemetry Overlay Text (Focus Driver)
                    tel_text = ""
                    if focus_driver in [p['Driver'] for p in current_positions]:
                        f_data = next(p for p in current_positions if p['Driver'] == focus_driver)
                        tel_text = f"<b>{focus_driver}</b><br>Speed: {f_data['Speed']:.0f}<br>Gap: +{f_data['Gap']:.1f}s"

                    # Camera Layout
                    layout_update = {}
                    # Check if follow_cam is defined, otherwise default to False (or handle UI state)
                    # For now, let's assume we want full track unless specified. 
                    # But we need to pass 'follow_cam' from UI. 
                    # Since I can't easily add the checkbox variable in this edit without changing lines above, 
                    # I will default to False or check st.session_state if I added it.
                    # Let's just use the focus_x/y to center if we had the flag.
                    # For now, I'll omit the dynamic camera update in the frame to avoid errors, 
                    # or I can try to read a checkbox value if I can insert it earlier.
                    # I'll stick to the Trails for now to fix the error.

                    frames.append(go.Frame(
                        data=[go.Scatter(
                            x=frame_x, y=frame_y, 
                            mode='markers', 
                            marker=dict(
                                color=frame_colors, 
                                size=frame_sizes, 
                                opacity=frame_opacities,
                                line=dict(width=1, color='white')
                            ),
                            text=frame_hover, hoverinfo='text'
                        )],
                        layout=go.Layout(
                            annotations=[
                                dict(
                                    text=lb_text, align='left', showarrow=False,
                                    xref='paper', yref='paper', x=0.02, y=0.98,
                                    bgcolor='rgba(0,0,0,0.5)', bordercolor='gray', borderwidth=1,
                                    font=dict(color='white', size=10)
                                ),
                                dict(
                                    text=tel_text, align='left', showarrow=False,
                                    xref='paper', yref='paper', x=0.02, y=0.02,
                                    bgcolor='rgba(0,0,0,0.5)', bordercolor='red', borderwidth=1,
                                    font=dict(color='white', size=12)
                                ),
                                dict(
                                    text=f"Time: {t:.1f}s", showarrow=False,
                                    xref='paper', yref='paper', x=0.95, y=0.95,
                                    font=dict(color='white', size=14)
                                )
                            ]
                        ),
                        name=f"{t:.1f}",
                        traces=[1] 
                    ))
                
                # --- Figure ---
                padding = 500
                x_min, x_max = track_x.min(), track_x.max()
                y_min, y_max = track_y.min(), track_y.max()
                
                # Initial Data (First Frame)
                initial_annotations = []
                if frames:
                    init_data = frames[0].data[0]
                    if frames[0].layout and frames[0].layout.annotations:
                        initial_annotations = frames[0].layout.annotations
                else:
                    init_data = go.Scatter(x=[], y=[], mode='markers')

                fig = go.Figure(
                    data=[
                        # Trace 0: Track Map
                        go.Scatter(x=track_x, y=track_y, mode='lines', line=dict(color='white', width=6), hoverinfo='skip'),
                        # Trace 1: Drivers (Initial)
                        init_data
                    ],
                    layout=go.Layout(
                        title=f"Replay: {selected_lap} - {focus_driver}",
                        template="plotly_dark",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(visible=False, range=[x_min - padding, x_max + padding], scaleanchor="y", scaleratio=1),
                        yaxis=dict(visible=False, range=[y_min - padding, y_max + padding]),
                        showlegend=False,
                        height=700,
                        margin=dict(l=0, r=0, t=50, b=0),
                        annotations=initial_annotations,
                        updatemenus=[dict(
                            type='buttons',
                            showactive=False,
                            y=0, x=0.5,
                            xanchor='center',
                            buttons=[
                                dict(label='▶ Play', method='animate', args=[None, dict(frame=dict(duration=100, redraw=True), fromcurrent=True)]),
                                dict(label='⏸ Pause', method='animate', args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')])
                            ],
                            bgcolor="rgba(0,0,0,0.5)",
                            font=dict(color="white")
                        )],
                        sliders=[dict(
                            steps=[dict(method='animate', args=[[f.name], dict(mode='immediate', frame=dict(duration=0, redraw=True))], label=f.name) for f in frames],
                            currentvalue=dict(prefix='Time: ', visible=True, xanchor='center'),
                            len=0.9, x=0.5, xanchor='center', y=0,
                            active=0,
                            pad=dict(t=50, b=10),
                            font=dict(color="white")
                        )]
                    ),
                    frames=frames
                )
                
                status_text.empty()
                progress_bar.empty()
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"An error occurred during replay generation: {e}")
            st.exception(e)

# --- Helper for Lazy Loading ---
def ensure_full_data_loaded(session):
    if st.session_state.get('data_mode') == 'light':
        with st.spinner("Loading telemetry and detailed data..."):
            session.load(telemetry=True, weather=True, messages=True)
            st.session_state['data_mode'] = 'full'
            st.session_state['session'] = session # Update session in state
            st.rerun()

@st.cache_data
def fetch_marquee_data(year):
    try:
        ergast = Ergast()
        # Top 5 Drivers
        d_resp = ergast.get_driver_standings(season=year, limit=5)
        drivers = d_resp.content[0] if d_resp.content else pd.DataFrame()
        
        # Top 3 Constructors
        c_resp = ergast.get_constructor_standings(season=year, limit=3)
        constructors = c_resp.content[0] if c_resp.content else pd.DataFrame()
        
        return drivers, constructors
    except:
        return pd.DataFrame(), pd.DataFrame()

def render_global_marquee(year, schedule):
    drivers, constructors = fetch_marquee_data(year)
    
    parts = []
    
    # 1. Next Race
    if schedule is not None and not schedule.empty:
        try:
            today = pd.Timestamp.now(tz='UTC')
            # Ensure dates are comparable
            if schedule['Session5Date'].dt.tz is None:
                schedule['Session5Date'] = schedule['Session5Date'].dt.tz_localize('UTC')
            
            future_races = schedule[schedule['Session5Date'] > today].sort_values('Session5Date')
            
            if not future_races.empty:
                next_race = future_races.iloc[0]
                race_name = next_race['EventName']
                race_date = next_race['Session5Date'].tz_convert('Asia/Kolkata').strftime('%d %b %H:%M IST')
                parts.append(f"📅 NEXT RACE: {race_name} @ {race_date}")
        except Exception:
            pass

    # 2. Drivers Standings
    if not drivers.empty:
        d_list = []
        for _, d in drivers.iterrows():
            d_list.append(f"{d['position']}. {d['familyName']} ({d['points']} pts)")
        parts.append(f"🏆 DRIVERS: {' • '.join(d_list)}")
        
    # 3. Constructors Standings
    if not constructors.empty:
        c_list = []
        for _, c in constructors.iterrows():
            c_list.append(f"{c['position']}. {c['constructorName']} ({c['points']} pts)")
        parts.append(f"🛠️ CONSTRUCTORS: {' • '.join(c_list)}")
        
    marquee_text = " &nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp; ".join(parts)
    
    st.markdown(f"""
    <style>
    .marquee-container {{
        width: 100%;
        overflow: hidden;
        background-color: #1e1e1e;
        color: #fff;
        padding: 5px 0;
        border-top: 2px solid #ff1801;
        border-bottom: 2px solid #ff1801;
        margin-bottom: 10px;
        white-space: nowrap;
        box-sizing: border-box;
    }}
    .marquee-content {{
        display: inline-block;
        padding-left: 100%;
        animation: scroll-left 45s linear infinite;
        font-family: sans-serif;
        font-weight: bold;
        font-size: 0.9em;
    }}
    @keyframes scroll-left {{
        0% {{ transform: translateX(0); }}
        100% {{ transform: translateX(-100%); }}
    }}
    </style>
    <div class="marquee-container">
        <div class="marquee-content">
            {marquee_text}
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Main Execution ---

# Handle Query Params for Navigation
try:
    qp = st.query_params
except:
    qp = {} # Fallback

if 'load_event' in qp:
    try:
        event_name = qp['load_event']
        if isinstance(event_name, list): event_name = event_name[0]
        
        load_year = int(qp.get('load_year', datetime.now().year))
        if isinstance(load_year, list): load_year = int(load_year[0])
        
        with st.spinner(f"Loading {event_name} (Results)..."):
            # OPTIMIZATION: Load only essential data first (Light Mode)
            session = fastf1.get_session(load_year, event_name, 'Race')
            session.load(telemetry=False, weather=False, messages=False)
            
            st.session_state['session'] = session
            st.session_state['loaded_event'] = f"{event_name} - Race"
            st.session_state['data_mode'] = 'light' # Track data mode
            
            # Clear params to prevent reload loop
            try:
                st.query_params.clear()
            except:
                st.experimental_set_query_params()
                
    except Exception as e:
        st.error(f"Failed to load event from URL: {e}")

# Session Selector & Default View - Always render sidebar
year, schedule = render_session_selector()

# Global Marquee - Render BEFORE Title
render_global_marquee(year, schedule)

st.title("🏎️ Formula 1 Realtime Dashboard")

# Header Stats
render_header_stats(year)

# Global Search
search_query = st.text_input("Search for a Driver or Team", placeholder="e.g. Hamilton, Ferrari, Max...", key="search_query_global")

if search_query:
    render_search_ui(search_query)
elif 'session' in st.session_state:
    session = st.session_state['session']
    st.header(f"🏁 {st.session_state['loaded_event']}")
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Results", "🏎️ Telemetry", "⏱️ Lap Comparison", "🗺️ Track Map", "🎥 Race Replay"])
    
    with tab1:
        render_results_tab(session)
    with tab2:
        ensure_full_data_loaded(session)
        if st.session_state.get('data_mode') == 'full':
            render_telemetry_tab(session)
    with tab3:
        ensure_full_data_loaded(session)
        if st.session_state.get('data_mode') == 'full':
            render_lap_comparison_tab(session)
    with tab4:
        ensure_full_data_loaded(session)
        if st.session_state.get('data_mode') == 'full':
            event_name = st.session_state['loaded_event'].split(' - ')[0]
            render_track_map_tab(session, event_name)
    with tab5:
        ensure_full_data_loaded(session)
        if st.session_state.get('data_mode') == 'full':
            render_replay_tab(session)
        
else:
    # Default View (Calendar/Standings)
    render_championship_view(year, schedule)
