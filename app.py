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
    year = st.sidebar.selectbox("Year", range(current_year + 1, 2018, -1), index=1)
    
    # Get Schedule
    try:
        schedule = fastf1.get_event_schedule(year)
        events = schedule[schedule['EventFormat'] != 'testing']
        
        today = pd.Timestamp.now(tz='UTC')
        past_events = events[events['Session5Date'] < today]
        default_index = len(past_events) - 1 if not past_events.empty else 0
        if default_index < 0: default_index = 0
        
        event_names = events['EventName'].tolist()
        
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
        events_to_show = schedule[['RoundNumber', 'EventName', 'Location', 'Session5Date', 'Country']].copy()
        
        # Grid layout
        cols = st.columns(3)
        for idx, row in events_to_show.iterrows():
            with cols[idx % 3]:
                try:
                    date_str = row['Session5Date'].strftime('%d %b %Y')
                except:
                    date_str = str(row['Session5Date'])
                
                st.markdown(f"""
                <div class="calendar-card">
                    <div class="calendar-round">Round {row['RoundNumber']}</div>
                    <div class="calendar-date">🗓️ {date_str}</div>
                    <div class="calendar-event">{row['EventName']}</div>
                    <div class="calendar-location">📍 {row['Location']}, {row['Country']}</div>
                </div>
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
    total_laps = int(session.laps['LapNumber'].max())
    lap_options = ["Full Race"] + list(range(1, total_laps + 1))
    selected_lap = st.selectbox("Select Lap to Replay", lap_options, index=0)
    
    driver_map = session.results.set_index('FullName')['Abbreviation'].to_dict()
    all_drivers = list(driver_map.keys())
    replay_drivers = st.multiselect("Select Drivers to Replay", all_drivers, default=all_drivers)
    focus_driver = st.selectbox("Focus Driver (Telemetry)", replay_drivers, index=0 if replay_drivers else None)

    if replay_drivers and focus_driver:
        if st.button("Load Replay", type="primary"):
            with st.spinner("Generating Arcade Replay... This may take a moment."):
                try:
                    ref_lap = session.laps.pick_fastest()
                    ref_tel = ref_lap.get_telemetry()
                    track_x = ref_tel['X']
                    track_y = ref_tel['Y']
                    
                    if selected_lap == "Full Race":
                        start_time = session.laps['LapStartTime'].min().total_seconds()
                        end_time = session.laps['Time'].max().total_seconds()
                        time_grid = np.arange(start_time, end_time, 2.0) 
                    else:
                        time_grid = np.arange(0, 150, 0.5)

                    driver_data = {}
                    for d in replay_drivers:
                        abbr = driver_map[d]
                        try:
                            d_laps = session.laps.pick_driver(abbr)
                            if selected_lap == "Full Race":
                                tel = d_laps.get_telemetry()
                                tel['TimeSec'] = tel['SessionTime'].dt.total_seconds()
                            else:
                                lap = d_laps[d_laps['LapNumber'] == selected_lap].iloc[0]
                                tel = lap.get_telemetry()
                                tel['TimeSec'] = tel['Time'].dt.total_seconds()
                            
                            tel = tel[['TimeSec', 'X', 'Y', 'Speed', 'nGear', 'DRS', 'Distance', 'LapNumber']].dropna()
                            driver_data[d] = tel
                        except:
                            continue

                    frames = []
                    interpolated_data = {}
                    for d, tel in driver_data.items():
                        t_orig = tel['TimeSec'].values
                        x_new = np.interp(time_grid, t_orig, tel['X'].values, left=np.nan, right=np.nan)
                        y_new = np.interp(time_grid, t_orig, tel['Y'].values, left=np.nan, right=np.nan)
                        dist_new = np.interp(time_grid, t_orig, tel['Distance'].values, left=0, right=np.nan)
                        speed_new = np.interp(time_grid, t_orig, tel['Speed'].values, left=0, right=0)
                        
                        idx = np.searchsorted(t_orig, time_grid, side='right') - 1
                        idx = np.clip(idx, 0, len(t_orig)-1)
                        gear_new = tel['nGear'].values[idx]
                        drs_new = tel['DRS'].values[idx]
                        lap_new = tel['LapNumber'].values[idx]
                        
                        team_name = session.results.loc[session.results['Abbreviation'] == driver_map[d], 'TeamName'].iloc[0]
                        color = fastf1.plotting.get_team_color(team_name, session=session)
                        
                        interpolated_data[d] = {
                            'x': x_new, 'y': y_new, 'dist': dist_new, 'lap': lap_new,
                            'speed': speed_new, 'gear': gear_new, 'drs': drs_new,
                            'color': color, 'abbr': driver_map[d]
                        }

                    for i, t in enumerate(time_grid):
                        frame_x, frame_y, frame_colors, frame_hover = [], [], [], []
                        driver_stats = []
                        focus_info = None
                        
                        for d, data in interpolated_data.items():
                            if np.isnan(data['x'][i]): continue
                            frame_x.append(data['x'][i])
                            frame_y.append(data['y'][i])
                            frame_colors.append(data['color'])
                            frame_hover.append(d)
                            
                            driver_stats.append({
                                'name': d, 'abbr': data['abbr'], 'lap': data['lap'][i],
                                'dist': data['dist'][i], 'color': data['color']
                            })
                            
                            if d == focus_driver:
                                focus_info = {
                                    'speed': data['speed'][i], 'gear': data['gear'][i],
                                    'drs': data['drs'][i], 'lap': data['lap'][i], 'color': data['color']
                                }

                        driver_stats.sort(key=lambda x: (x['lap'], x['dist']), reverse=True)
                        leaderboard_text = "<b>Leaderboard</b><br>" + "".join([f"<span style='color:{s['color']}'>{r+1}. {s['abbr']}</span><br>" for r, s in enumerate(driver_stats[:10])])
                        
                        tel_text = "No Data"
                        if focus_info:
                            drs_status = "ON" if focus_info['drs'] > 8 else "OFF"
                            tel_text = (f"<span style='color:{focus_info['color']}; font-size: 16px'><b>Driver: {driver_map[focus_driver]}</b></span><br>"
                                        f"Speed: {focus_info['speed']:.0f} km/h<br>Gear: {focus_info['gear']}<br>DRS: {drs_status}<br>Lap: {focus_info['lap']:.0f}")

                        frames.append(go.Frame(
                            data=[go.Scatter(x=frame_x, y=frame_y, mode='markers', marker=dict(color=frame_colors, size=12, line=dict(width=1, color='white')), text=frame_hover, hoverinfo='text')],
                            layout=go.Layout(annotations=[
                                dict(x=1.15, y=1, xref='paper', yref='paper', text=leaderboard_text, showarrow=False, align='left', bgcolor='rgba(0,0,0,0.5)', bordercolor='#333', borderwidth=1, font=dict(color='white', family="monospace", size=12)),
                                dict(x=-0.15, y=0.5, xref='paper', yref='paper', text=tel_text, showarrow=False, align='left', bgcolor='rgba(0,0,0,0.5)', bordercolor=focus_info['color'] if focus_info else '#333', borderwidth=2, font=dict(color='white', family="monospace", size=14)),
                                dict(x=0, y=1.1, xref='paper', yref='paper', text=f"Time: {t:.1f}s", showarrow=False, align='left', font=dict(color='white', size=16))
                            ]), name=f"{t:.1f}",
                            traces=[1] 
                        ))

                    if not frames:
                        st.warning("No data available for animation.")
                    else:
                        initial_data = frames[0].data[0] if frames and frames[0].data else go.Scatter(x=[], y=[], mode='markers')
                        x_min, x_max = track_x.min(), track_x.max()
                        y_min, y_max = track_y.min(), track_y.max()
                        padding = 500
                        
                        fig = go.Figure(
                            data=[go.Scatter(x=track_x, y=track_y, mode='lines', line=dict(color='rgba(255, 255, 255, 0.5)', width=6), hoverinfo='skip'), initial_data],
                            layout=go.Layout(
                                title=f"Arcade Replay - {selected_lap}", template="plotly_dark", plot_bgcolor='black', paper_bgcolor='black',
                                xaxis=dict(visible=False, showgrid=False, range=[x_min - padding, x_max + padding], scaleanchor="y", scaleratio=1),
                                yaxis=dict(visible=False, showgrid=False, range=[y_min - padding, y_max + padding]),
                                showlegend=False, width=1000, height=800, margin=dict(l=150, r=150, t=50, b=50),
                                updatemenus=[dict(type='buttons', showactive=False, y=0, x=0.5, xanchor='center', buttons=[
                                    dict(label='▶ Play', method='animate', args=[None, dict(frame=dict(duration=100, redraw=True), fromcurrent=True)]),
                                    dict(label='⏸ Pause', method='animate', args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')])
                                ])],
                                sliders=[dict(steps=[dict(method='animate', args=[[f.name], dict(mode='immediate', frame=dict(duration=0, redraw=True))], label=f.name) for f in frames], currentvalue=dict(prefix='Time: '), active=0)]
                            ), frames=frames
                        )
                        if frames and frames[0].layout: fig.update_layout(annotations=frames[0].layout.annotations)
                        st.plotly_chart(fig, use_container_width=True)

                except Exception as e:
                    st.error(f"Error generating arcade replay: {e}")
                    st.exception(e)
    else:
        st.info("Please select drivers and a focus driver to start.")

# --- Main Execution ---

st.title("🏎️ Formula 1 Realtime Dashboard")

# Session Selector & Default View - Always render sidebar
year, schedule = render_session_selector()

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
        render_telemetry_tab(session)
    with tab3:
        render_lap_comparison_tab(session)
    with tab4:
        event_name = st.session_state['loaded_event'].split(' - ')[0]
        render_track_map_tab(session, event_name)
    with tab5:
        render_replay_tab(session)
        
else:
    # Default View (Calendar/Standings)
    render_championship_view(year, schedule)
