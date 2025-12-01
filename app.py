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
        
        # Sort: Recent/Upcoming first
        # We'll sort by date descending so the latest races are at the top
        today = pd.Timestamp.now(tz='UTC')
        schedule['Session5Date'] = pd.to_datetime(schedule['Session5Date'], utc=True)
        schedule['DateDiff'] = (schedule['Session5Date'] - today).abs()
        # Sort by date descending (newest first)
        events_to_show = schedule.sort_values(by='Session5Date', ascending=False)
        
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

        for idx, row in events_to_show.iterrows():
            col = cols[idx % 3]
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
    selected_drivers = st.multiselect("Select Drivers to Compare", drivers, default=drivers)
    
    if selected_drivers:
        fig_speed = go.Figure()
        fig_throttle = go.Figure()
        fig_brake = go.Figure()
        fig_rpm = go.Figure()
        fig_gear = go.Figure()
        fig_drs = go.Figure()
        
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
        
        fig_speed.update_layout(title="Speed Trace", xaxis_title="Distance (m)", yaxis_title="Speed (km/h)")
        st.plotly_chart(fig_speed, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            fig_throttle.update_layout(title="Throttle Trace", xaxis_title="Distance (m)", yaxis_title="Throttle %")
            st.plotly_chart(fig_throttle, use_container_width=True)
        with col2:
            fig_brake.update_layout(title="Brake Trace", xaxis_title="Distance (m)", yaxis_title="Brake")
            st.plotly_chart(fig_brake, use_container_width=True)
            
        col3, col4 = st.columns(2)
        with col3:
            fig_rpm.update_layout(title="RPM Trace", xaxis_title="Distance (m)", yaxis_title="RPM")
            st.plotly_chart(fig_rpm, use_container_width=True)
        with col4:
            fig_gear.update_layout(title="Gear Trace", xaxis_title="Distance (m)", yaxis_title="Gear")
            st.plotly_chart(fig_gear, use_container_width=True)
            
        fig_drs.update_layout(title="DRS Trace", xaxis_title="Distance (m)", yaxis_title="DRS Status")
        st.plotly_chart(fig_drs, use_container_width=True)

def render_lap_comparison_tab(session):
    st.subheader("Lap Time Comparison")
    laps = session.laps
    valid_laps = laps.pick_quicklaps()
    
    if not valid_laps.empty:
        valid_laps['LapTimeSeconds'] = valid_laps['LapTime'].dt.total_seconds()
        fig_laps = px.box(valid_laps, x="Team", y="LapTimeSeconds", color="Team", title="Lap Time Distribution by Team")
        st.plotly_chart(fig_laps, use_container_width=True)
        
        driver_map_reverse = session.results.set_index('Abbreviation')['FullName'].to_dict()
        valid_laps['DriverName'] = valid_laps['Driver'].map(driver_map_reverse)
        fig_scatter = px.scatter(valid_laps, x="LapNumber", y="LapTimeSeconds", color="DriverName", title="Lap Times per Lap")
        st.plotly_chart(fig_scatter, use_container_width=True)

def render_track_map_tab(session, selected_event_name):
    st.subheader("Track Map")
    try:
        lap = session.laps.pick_fastest()
        if lap is not None:
            tel = lap.get_telemetry()
            x = tel['X']
            y = tel['Y']
            
            fig_map = go.Figure(go.Scatter(x=x, y=y, mode='lines', line=dict(width=4, color='white')))
            fig_map.update_layout(
                title=f"Track Map - {selected_event_name}",
                template="plotly_dark",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(visible=False, showgrid=False),
                yaxis=dict(visible=False, showgrid=False, scaleanchor="x", scaleratio=1),
                height=600,
                showlegend=False
            )
            # fig_map.update_yaxes(scaleanchor="x", scaleratio=1) # Moved inside update_layout
            st.plotly_chart(fig_map, use_container_width=True)
    except Exception as e:
        st.warning("Could not generate track map.")

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
                        lap_new = tel['LapNumber'].values[idx]
                        
                        # Get Team Color
                        team_name = session.results.loc[session.results['Abbreviation'] == abbr, 'TeamName'].iloc[0]
                        color = fastf1.plotting.get_team_color(team_name, session=session)
                        
                        interpolated_data[d_name] = {
                            'x': x_new, 'y': y_new, 'dist': dist_new, 'lap': lap_new,
                            'speed': speed_new, 'gear': gear_new, 'drs': drs_new,
                            'color': color, 'abbr': abbr
                        }
                        
                    except Exception as e:
                        # st.warning(f"Skipping {d_name}: {e}")
                        continue

                status_text.text("Generating animation frames...")
                
                # 4. Generate Frames
                frames = []
                for i, t in enumerate(time_grid):
                    frame_x, frame_y, frame_colors, frame_hover = [], [], [], []
                    driver_stats = []
                    focus_info = None
                    
                    for d_name, data in interpolated_data.items():
                        if np.isnan(data['x'][i]): continue
                        
                        frame_x.append(data['x'][i])
                        frame_y.append(data['y'][i])
                        frame_colors.append(data['color'])
                        frame_hover.append(f"{d_name} (Lap {data['lap'][i]:.0f})")
                        
                        driver_stats.append({
                            'abbr': data['abbr'], 
                            'dist': data['dist'][i], 
                            'color': data['color']
                        })
                        
                        if d_name == focus_driver:
                            focus_info = {
                                'speed': data['speed'][i], 
                                'gear': data['gear'][i],
                                'drs': data['drs'][i], 
                                'lap': data['lap'][i], 
                                'color': data['color']
                            }
                    
                    # Sort leaderboard by distance (approximate position)
                    driver_stats.sort(key=lambda x: x['dist'], reverse=True)
                    
                    # Leaderboard HTML
                    lb_html = "<b>LEADERBOARD</b><br>" + "".join(
                        [f"<span style='color:{s['color']}'>{r+1}. {s['abbr']}</span><br>" for r, s in enumerate(driver_stats[:10])]
                    )
                    
                    # Telemetry HTML
                    tel_html = "NO DATA"
                    if focus_info:
                        drs_on = focus_info['drs'] in [10, 12, 14] or focus_info['drs'] > 8 # FastF1 DRS codes vary
                        drs_str = "OPEN" if drs_on else "CLOSED"
                        drs_color = "#00ff00" if drs_on else "#ffffff"
                        
                        tel_html = (
                            f"<span style='color:{focus_info['color']}; font-size: 18px'><b>{driver_map[focus_driver]}</b></span><br>"
                            f"SPEED: <b>{focus_info['speed']:.0f}</b> km/h<br>"
                            f"GEAR: <b>{focus_info['gear']}</b><br>"
                            f"DRS: <span style='color:{drs_color}'><b>{drs_str}</b></span>"
                        )

                    frames.append(go.Frame(
                        data=[go.Scatter(
                            x=frame_x, y=frame_y, 
                            mode='markers', 
                            marker=dict(color=frame_colors, size=12, line=dict(width=1, color='white')),
                            text=frame_hover, hoverinfo='text'
                        )],
                        layout=go.Layout(annotations=[
                            dict(x=1.02, y=1, xref='paper', yref='paper', text=lb_html, showarrow=False, align='left', 
                                 bgcolor='rgba(0,0,0,0.8)', bordercolor='#444', borderwidth=1, 
                                 font=dict(color='white', family="monospace", size=10)),
                            dict(x=0.02, y=0.05, xref='paper', yref='paper', text=tel_html, showarrow=False, align='left', 
                                 bgcolor='rgba(0,0,0,0.8)', bordercolor=focus_info['color'] if focus_info else '#444', borderwidth=2, 
                                 font=dict(color='white', family="monospace", size=14)),
                            dict(x=0.5, y=1.05, xref='paper', yref='paper', text=f"Time: {t:.1f}s", showarrow=False, align='center', 
                                 font=dict(color='white', size=14))
                        ]),
                        name=f"{t:.1f}",
                        traces=[1] # IMPORTANT: Only update trace 1 (drivers), keep trace 0 (track) static
                    ))
                
                # 5. Build Figure
                x_min, x_max = track_x.min(), track_x.max()
                y_min, y_max = track_y.min(), track_y.max()
                padding = 500
                
                # Initial Data (First Frame)
                if frames:
                    init_data = frames[0].data[0]
                else:
                    init_data = go.Scatter(x=[], y=[], mode='markers')

                fig = go.Figure(
                    data=[
                        # Trace 0: Track Map
                        go.Scatter(x=track_x, y=track_y, mode='lines', line=dict(color='#333', width=8), hoverinfo='skip'),
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
