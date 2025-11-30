import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import os

# Page Config
st.set_page_config(page_title="F1 Realtime Dashboard", page_icon="🏎️", layout="wide")

# Custom CSS for premium look
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    .stSelectbox, .stMultiSelect {
        color: #fafafa;
    }
    h1, h2, h3 {
        color: #ff1801 !important; /* F1 Red */
        font-family: 'Arial', sans-serif;
    }
    .metric-card {
        background-color: #1f2937;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #374151;
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #ff1801;
    }
    .metric-label {
        font-size: 14px;
        color: #9ca3af;
    }
</style>
""", unsafe_allow_html=True)

# Cache Setup
CACHE_DIR = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)
import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import os

# Page Config
st.set_page_config(page_title="F1 Realtime Dashboard", page_icon="🏎️", layout="wide")

# Custom CSS for premium look and calendar
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

st.title("🏎️ Formula 1 Realtime Dashboard")

# Sidebar
st.sidebar.title("Session Controls")
current_year = datetime.now().year
# Include next year for 2026 support
year = st.sidebar.selectbox("Select Year", range(current_year + 1, 2018, -1), index=1)

# Get Schedule
try:
    schedule = fastf1.get_event_schedule(year)
    # Filter out testing if needed, or keep it
    events = schedule[schedule['EventFormat'] != 'testing']
    
    # Find next or last event
    today = pd.Timestamp.now(tz='UTC')
    # This is a bit complex to find the "current" event easily, so we just list them
    event_names = events['EventName'].tolist()
    
    # Default to latest event that has happened or is happening
    # We can check Session5Date (usually Race)
    past_events = events[events['Session5Date'] < today]
    default_index = len(past_events) - 1 if not past_events.empty else 0
    if default_index < 0: default_index = 0
    
    # Handle case where event_names might be empty (e.g. future year with no data yet)
    if not event_names:
        selected_event_name = None
        st.warning(f"No events found for {year} yet.")
    else:
        selected_event_name = st.sidebar.selectbox("Select Grand Prix", event_names, index=default_index)
    
    if selected_event_name:
        event_schedule = events[events['EventName'] == selected_event_name].iloc[0]
        
        # Session Selection
        # Map session names to keys if needed, but fastf1 uses 'FP1', 'FP2', 'FP3', 'Qualifying', 'Sprint', 'Race'
        # The schedule has columns like Session1, Session2...
        available_sessions = []
        for i in range(1, 6):
            sess_name = event_schedule[f'Session{i}']
            if sess_name:
                available_sessions.append(sess_name)
                
        selected_session_name = st.sidebar.selectbox("Select Session", available_sessions, index=len(available_sessions)-1)
        
        if st.sidebar.button("Load Session Data", type="primary"):
            with st.spinner(f"Loading data for {selected_event_name} - {selected_session_name}..."):
                try:
                    session = fastf1.get_session(year, selected_event_name, selected_session_name)
                    session.load()
                    
                    st.session_state['session'] = session
                    st.session_state['loaded_event'] = f"{selected_event_name} - {selected_session_name}"
                    st.success("Data Loaded Successfully!")
                except Exception as e:
                    st.error(f"Failed to load data: {e}")

except Exception as e:
    st.error(f"Could not fetch schedule: {e}")

# Main Content
if 'session' in st.session_state:
    session = st.session_state['session']
    st.header(f"🏁 {st.session_state['loaded_event']}")
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Results", "🏎️ Telemetry", "⏱️ Lap Comparison", "🗺️ Track Map", "🎥 Race Replay"])
    
    with tab1:
        st.subheader("Session Results")
        if hasattr(session, 'results'):
            results = session.results
            # Clean up for display
            display_cols = ['Position', 'FullName', 'DriverNumber', 'TeamName', 'Time', 'Status', 'Points']
            # Filter cols that exist
            cols = [c for c in display_cols if c in results.columns]
            
            # Format Time
            results_display = results[cols].copy()
            results_display['Time'] = results_display['Time'].astype(str).str.replace('0 days ', '')
            
            st.dataframe(results_display, use_container_width=True)
        else:
            st.info("No results available for this session yet.")

    with tab2:
        st.subheader("Driver Telemetry Analysis")
        driver_map = session.results.set_index('FullName')['Abbreviation'].to_dict()
        drivers = list(driver_map.keys())
        # Default to ALL drivers
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
                            # Get team name for the driver
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

    with tab3:
        st.subheader("Lap Time Comparison")
        # Box plot of lap times for top teams
        top_teams = session.results['TeamName'].unique()[:5] # Top 5 teams
        
        laps = session.laps
        # Filter out slow laps (e.g. > 107% or just outliers)
        # Simple filter: laps with no pit stops and valid times
        valid_laps = laps.pick_quicklaps()
        
        if not valid_laps.empty:
            # Convert timedelta to seconds for plotting
            valid_laps['LapTimeSeconds'] = valid_laps['LapTime'].dt.total_seconds()
            
            fig_laps = px.box(valid_laps, x="Team", y="LapTimeSeconds", color="Team", title="Lap Time Distribution by Team")
            st.plotly_chart(fig_laps, use_container_width=True)
            
            # Scatter plot of all laps
            # Map Driver abbreviation to Full Name for the scatter plot
            driver_map_reverse = session.results.set_index('Abbreviation')['FullName'].to_dict()
            valid_laps['DriverName'] = valid_laps['Driver'].map(driver_map_reverse)
            
            fig_scatter = px.scatter(valid_laps, x="LapNumber", y="LapTimeSeconds", color="DriverName", title="Lap Times per Lap")
            st.plotly_chart(fig_scatter, use_container_width=True)

    with tab4:
        st.subheader("Track Map")
        # We can plot the track map using telemetry position data
        try:
            lap = session.laps.pick_fastest()
            if lap is not None:
                tel = lap.get_telemetry()
                x = tel['X']
                y = tel['Y']
                
                fig_map = go.Figure(go.Scatter(x=x, y=y, mode='lines', line=dict(width=4, color='white')))
                fig_map.update_layout(
                    title=f"Track Map - {selected_event_name}",
                    xaxis=dict(visible=False),
                    yaxis=dict(visible=False),
                    height=600,
                    showlegend=False
                )
                fig_map.update_yaxes(scaleanchor="x", scaleratio=1)
                st.plotly_chart(fig_map, use_container_width=True)
        except Exception as e:
            st.warning("Could not generate track map.")

    with tab5:
        st.subheader("Race Replay Animation")
        
        # 1. Select Lap
        total_laps = int(session.laps['LapNumber'].max())
        lap_options = ["Full Race"] + list(range(1, total_laps + 1))
        selected_lap = st.selectbox("Select Lap to Replay", lap_options, index=0)
        
        # 2. Select Drivers
        driver_map = session.results.set_index('FullName')['Abbreviation'].to_dict()
        all_drivers = list(driver_map.keys())
        # Default to all drivers
        replay_drivers = st.multiselect("Select Drivers to Replay", all_drivers, default=all_drivers)
        
        # 3. Select Focus Driver (for Telemetry Box)
        focus_driver = st.selectbox("Focus Driver (Telemetry)", replay_drivers, index=0 if replay_drivers else None)

        if replay_drivers and focus_driver:
            if st.button("Load Replay", type="primary"):
                with st.spinner("Generating Arcade Replay... This may take a moment."):
                    try:
                        # --- Data Preparation ---
                        # Get reference track (from fastest lap of the session)
                        ref_lap = session.laps.pick_fastest()
                        ref_tel = ref_lap.get_telemetry()
                        track_x = ref_tel['X']
                        track_y = ref_tel['Y']
                        
                        # Determine time bounds
                        if selected_lap == "Full Race":
                            start_time = session.laps['LapStartTime'].min().total_seconds()
                            end_time = session.laps['Time'].max().total_seconds()
                            # Coarser grid for full race to prevent browser crash
                            time_grid = np.arange(start_time, end_time, 2.0) 
                        else:
                            # Single Lap
                            # Get max duration of this lap among selected drivers
                            # (Simplified: just take 0 to 120s or typical lap time)
                            time_grid = np.arange(0, 150, 0.5) # 0.5s resolution

                        # Pre-fetch data for all drivers
                        driver_data = {}
                        for d in replay_drivers:
                            abbr = driver_map[d]
                            try:
                                d_laps = session.laps.pick_driver(abbr)
                                if selected_lap == "Full Race":
                                    tel = d_laps.get_telemetry()
                                    tel['TimeSec'] = tel['SessionTime'].dt.total_seconds()
                                    # Add LapNumber for sorting
                                    # Interpolating LapNumber is tricky, but we can use 'Distance' and cumulative distance
                                    # For leaderboard sorting, we need (Lap, Distance)
                                    # Let's just use 'TimeSec' to find the row, then get Lap/Dist
                                else:
                                    lap = d_laps[d_laps['LapNumber'] == selected_lap].iloc[0]
                                    tel = lap.get_telemetry()
                                    tel['TimeSec'] = tel['Time'].dt.total_seconds()
                                
                                # Clean and store
                                tel = tel[['TimeSec', 'X', 'Y', 'Speed', 'nGear', 'DRS', 'Distance', 'LapNumber']].dropna()
                                driver_data[d] = tel
                            except:
                                continue

                        # --- Frame Generation ---
                        frames = []
                        
                        # We need to interpolate everything to the time_grid
                        # To optimize, we'll create a big DataFrame or dict of arrays
                        interpolated_data = {}
                        for d, tel in driver_data.items():
                            # Interpolate X, Y, Distance, LapNumber(ffill)
                            # We use np.interp for continuous, searchsorted/indexing for discrete
                            
                            # Reindex to time_grid
                            # Using pandas reindex/interpolate is easier but slower? 
                            # Let's use numpy for speed
                            
                            t_orig = tel['TimeSec'].values
                            
                            # Safe interpolation
                            x_new = np.interp(time_grid, t_orig, tel['X'].values, left=np.nan, right=np.nan)
                            y_new = np.interp(time_grid, t_orig, tel['Y'].values, left=np.nan, right=np.nan)
                            dist_new = np.interp(time_grid, t_orig, tel['Distance'].values, left=0, right=np.nan)
                            speed_new = np.interp(time_grid, t_orig, tel['Speed'].values, left=0, right=0)
                            
                            # For discrete values like Gear, DRS, LapNumber, use nearest or ffill
                            # np.interp doesn't do nearest well. 
                            idx = np.searchsorted(t_orig, time_grid, side='right') - 1
                            idx = np.clip(idx, 0, len(t_orig)-1)
                            
                            gear_new = tel['nGear'].values[idx]
                            drs_new = tel['DRS'].values[idx]
                            lap_new = tel['LapNumber'].values[idx]
                            
                            # Team Color
                            team_name = session.results.loc[session.results['Abbreviation'] == driver_map[d], 'TeamName'].iloc[0]
                            color = fastf1.plotting.get_team_color(team_name, session=session)
                            
                            interpolated_data[d] = {
                                'x': x_new, 'y': y_new, 
                                'dist': dist_new, 'lap': lap_new,
                                'speed': speed_new, 'gear': gear_new, 'drs': drs_new,
                                'color': color, 'abbr': driver_map[d]
                            }

                        # Build Frames
                        for i, t in enumerate(time_grid):
                            # 1. Current Positions
                            frame_x = []
                            frame_y = []
                            frame_colors = []
                            frame_hover = []
                            frame_sizes = []
                            
                            # For Leaderboard Sorting
                            # Sort by LapNumber DESC, then Distance DESC
                            driver_stats = []
                            
                            focus_info = None
                            
                            for d, data in interpolated_data.items():
                                # Check if data exists for this time
                                if np.isnan(data['x'][i]):
                                    continue
                                
                                frame_x.append(data['x'][i])
                                frame_y.append(data['y'][i])
                                frame_colors.append(data['color'])
                                frame_hover.append(d)
                                frame_sizes.append(10) # Default size
                                
                                # Stats for leaderboard
                                driver_stats.append({
                                    'name': d,
                                    'abbr': data['abbr'],
                                    'lap': data['lap'][i],
                                    'dist': data['dist'][i],
                                    'color': data['color']
                                })
                                
                                # Focus Driver Info
                                if d == focus_driver:
                                    focus_info = {
                                        'speed': data['speed'][i],
                                        'gear': data['gear'][i],
                                        'drs': data['drs'][i],
                                        'lap': data['lap'][i],
                                        'color': data['color']
                                    }

                            # Sort Leaderboard
                            driver_stats.sort(key=lambda x: (x['lap'], x['dist']), reverse=True)
                            
                            # Construct Leaderboard Text
                            leaderboard_text = "<b>Leaderboard</b><br>"
                            for rank, stat in enumerate(driver_stats[:10]): # Top 10
                                leaderboard_text += f"<span style='color:{stat['color']}'>{rank+1}. {stat['abbr']}</span><br>"
                            
                            # Construct Telemetry Box Text
                            if focus_info:
                                drs_status = "ON" if focus_info['drs'] in [10, 12, 14] else "OFF" # FastF1 DRS codes vary, usually > 8 is enabled
                                if focus_info['drs'] > 8: drs_status = "ON"
                                else: drs_status = "OFF"
                                
                                tel_text = (
                                    f"<span style='color:{focus_info['color']}; font-size: 16px'><b>Driver: {driver_map[focus_driver]}</b></span><br>"
                                    f"Speed: {focus_info['speed']:.0f} km/h<br>"
                                    f"Gear: {focus_info['gear']}<br>"
                                    f"DRS: {drs_status}<br>"
                                    f"Lap: {focus_info['lap']:.0f}"
                                )
                            else:
                                tel_text = "No Data"

                            # Create Frame
                            frames.append(go.Frame(
                                data=[go.Scatter(
                                    x=frame_x, y=frame_y,
                                    mode='markers',
                                    marker=dict(color=frame_colors, size=12, line=dict(width=1, color='white')),
                                    text=frame_hover,
                                    hoverinfo='text'
                                )],
                                layout=go.Layout(
                                    annotations=[
                                        # Leaderboard (Right Side)
                                        dict(
                                            x=1.15, y=1, xref='paper', yref='paper',
                                            text=leaderboard_text,
                                            showarrow=False, align='left',
                                            bgcolor='rgba(0,0,0,0.5)', bordercolor='#333', borderwidth=1,
                                            font=dict(color='white', family="monospace", size=12)
                                        ),
                                        # Telemetry Box (Left Side)
                                        dict(
                                            x=-0.15, y=0.5, xref='paper', yref='paper',
                                            text=tel_text,
                                            showarrow=False, align='left',
                                            bgcolor='rgba(0,0,0,0.5)', bordercolor=focus_info['color'] if focus_info else '#333', borderwidth=2,
                                            font=dict(color='white', family="monospace", size=14)
                                        ),
                                        # Time/Lap Info (Top Left)
                                        dict(
                                            x=0, y=1.1, xref='paper', yref='paper',
                                            text=f"Time: {t:.1f}s",
                                            showarrow=False, align='left',
                                            font=dict(color='white', size=16)
                                        )
                                    ]
                                ),
                                name=f"{t:.1f}"
                            ))

                        # --- Base Figure ---
                        if not frames:
                            st.warning("No data available for animation.")
                        else:
                            # Use data from the first frame for the initial state
                            # If the first frame is empty (no drivers started yet), create a dummy empty trace
                            initial_data = frames[0].data[0] if frames and frames[0].data else go.Scatter(x=[], y=[], mode='markers')

                            # Calculate track bounds with some padding
                            x_min, x_max = track_x.min(), track_x.max()
                            y_min, y_max = track_y.min(), track_y.max()
                            padding = 500 # meters
                            
                            fig = go.Figure(
                                data=[
                                    # Trace 0: Track Map
                                    go.Scatter(
                                        x=track_x, y=track_y,
                                        mode='lines',
                                        line=dict(color='rgba(255, 255, 255, 0.5)', width=6),
                                        hoverinfo='skip'
                                    ),
                                    # Trace 1: Drivers (Initial State)
                                    initial_data
                                ],
                                layout=go.Layout(
                                    title=f"Arcade Replay - {selected_lap}",
                                    template="plotly_dark",
                                    plot_bgcolor='black',
                                    paper_bgcolor='black',
                                    xaxis=dict(visible=False, showgrid=False, range=[x_min - padding, x_max + padding], scaleanchor="y", scaleratio=1),
                                    yaxis=dict(visible=False, showgrid=False, range=[y_min - padding, y_max + padding]),
                                    showlegend=False,
                                    width=1000,
                                    height=800,
                                    margin=dict(l=150, r=150, t=50, b=50), # Margins for annotations
                                    updatemenus=[dict(
                                        type='buttons',
                                        showactive=False,
                                        y=0, x=0.5, xanchor='center',
                                        buttons=[
                                            dict(label='▶ Play',
                                                 method='animate',
                                                 args=[None, dict(frame=dict(duration=100, redraw=True), fromcurrent=True)]), # redraw=True needed for annotations
                                            dict(label='⏸ Pause',
                                                 method='animate',
                                                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')])
                                        ]
                                    )],
                                    sliders=[dict(
                                        steps=[dict(method='animate', args=[[f.name], dict(mode='immediate', frame=dict(duration=0, redraw=True))], label=f.name) for f in frames],
                                        currentvalue=dict(prefix='Time: '),
                                        active=0
                                    )]
                                ),
                                frames=frames
                            )
                            
                            # Set initial layout from the first frame if available
                            if frames and frames[0].layout:
                                fig.update_layout(annotations=frames[0].layout.annotations)
                            
                            st.plotly_chart(fig, use_container_width=True)

                    except Exception as e:
                        st.error(f"Error generating arcade replay: {e}")
                        st.exception(e)
        else:
            st.info("Please select drivers and a focus driver to start.")

else:
    st.info("Please select a session and click 'Load Session Data' to begin.")
    
    # Show upcoming schedule
    if 'schedule' in locals():
        
        # Create a grid layout for the calendar
        events_to_show = schedule[['RoundNumber', 'EventName', 'Location', 'Session5Date', 'Country']].copy()
        
        # Grid layout
        cols = st.columns(3)
        for idx, row in events_to_show.iterrows():
            with cols[idx % 3]:
                # Format date
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
