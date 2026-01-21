import streamlit as st
import time
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Page Configuration - Immersive Full-Screen
st.set_page_config(
    page_title="Pure Storage | Fraud Detection Demo v2",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Shared Logic & Constants
BASE_DIR = Path(__file__).resolve().parent
STATS_FILE = BASE_DIR / "stats.json"
ORCHESTRATOR_SCRIPT = BASE_DIR / "run_pipeline.py"
TOTAL_ROWS_TARGET = 10_000_000
STAGES = ["Ingest", "Data Prep", "Model Train"]

# Custom CSS based on dashboard-mockup.html
st.markdown("""
<style>
    /* Pure Storage Theme */
    :root {
        --pure-orange: #FF6600;
        --pure-orange-dark: #E55A00;
        --pure-gray-dark: #1A1A2E;
        --pure-gray-medium: #2D2D44;
        --pure-gray-light: #3D3D5C;
        --text-primary: #FFFFFF;
        --text-secondary: #B0B0C0;
        --success-green: #00D4AA;
        --cpu-blue: #4A90D9;
        --gpu-green: #00D4AA;
    }

    .stApp {
        background: linear-gradient(135deg, var(--pure-gray-dark) 0%, #0F0F1A 100%);
        color: var(--text-primary);
    }
    
    /* Header */
    .header {
        background: rgba(26, 26, 46, 0.95);
        border-bottom: 2px solid var(--pure-orange);
        padding: 1rem 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        backdrop-filter: blur(10px);
        margin: -4rem -4rem 2rem -4rem;
    }
    
    .logo-container {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    
    .logo-icon {
        background: var(--pure-orange);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.2rem;
    }
    
    .logo-text {
        font-size: 1.5rem;
        font-weight: 600;
    }
    
    .logo-text span {
        color: var(--pure-orange);
    }

    .header-badges {
        display: flex;
        gap: 1rem;
        align-items: center;
    }

    .badge {
        font-size: 0.75rem;
        padding: 4px 12px;
        border-radius: 4px;
        font-weight: 600;
    }

    .badge-orange {
        background: rgba(255, 102, 0, 0.1);
        border: 1px solid var(--pure-orange);
        color: var(--pure-orange);
    }

    .badge-live {
        background: rgba(0, 212, 170, 0.1);
        border: 1px solid var(--success-green);
        color: var(--success-green);
    }

    /* Stage Navigation */
    .stage-nav {
        display: flex;
        justify-content: center;
        gap: 1rem;
        padding: 1rem;
        background: rgba(45, 45, 68, 0.5);
        border-radius: 50px;
        margin-bottom: 2rem;
    }
    
    .stage-pill {
        padding: 8px 24px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
        background: var(--pure-gray-medium);
        color: var(--text-secondary);
        border: 1px solid var(--pure-gray-light);
    }
    
    .stage-pill.active {
        background: var(--pure-orange);
        color: white;
        border-color: var(--pure-orange);
        box-shadow: 0 4px 20px rgba(255, 102, 0, 0.4);
    }
    
    .stage-pill.completed {
        background: var(--success-green);
        color: white;
        border-color: var(--success-green);
    }

    /* Cards */
    .metric-card {
        background: rgba(45, 45, 68, 0.4);
        border-radius: 16px;
        padding: 1.5rem;
        border: 1px solid var(--pure-gray-light);
        margin-bottom: 1rem;
    }

    .metric-label {
        font-size: 0.75rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 600;
        color: var(--pure-orange);
    }

    /* Control Bar */
    .control-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(26, 26, 46, 0.9);
        padding: 1.5rem 3rem;
        display: flex;
        justify-content: center;
        gap: 2rem;
        backdrop-filter: blur(10px);
        border-top: 1px solid var(--pure-gray-light);
        z-index: 1000;
    }

    /* Buttons - Nuclear Option */
    button[kind="primary"],
    button[kind="secondary"],
    div[data-testid="stButton"] button,
    div.stButton button,
    .stButton > button {
        background: var(--pure-orange) !important;
        background-color: var(--pure-orange) !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        padding: 0.75rem 2.5rem !important;
        font-weight: 700 !important;
        border: 1px solid var(--pure-orange) !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        min-height: 2.5rem !important;
    }

    button[kind="primary"]:hover,
    button[kind="secondary"]:hover,
    div[data-testid="stButton"] button:hover,
    div.stButton button:hover,
    .stButton > button:hover {
        background: var(--pure-orange-dark) !important;
        background-color: var(--pure-orange-dark) !important;
        color: #FFFFFF !important;
        border-color: var(--pure-orange-dark) !important;
        box-shadow: 0 4px 20px rgba(255, 102, 0, 0.4) !important;
    }

    /* Force text visibility */
    button[kind="primary"] p,
    button[kind="secondary"] p,
    div[data-testid="stButton"] button p,
    div.stButton button p,
    .stButton > button p,
    button[kind="primary"] span,
    button[kind="secondary"] span,
    div[data-testid="stButton"] button span,
    div.stButton button span,
    .stButton > button span {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

def get_stats():
    """Reads telemetry from pipeline_report.txt by parsing the last [TELEMETRY] entry."""
    try:
        log_file = BASE_DIR / "pipeline_report.txt"
        if not log_file.exists():
            return {"error": "Pipeline log not found."}
        
        # Read last 200 lines for efficiency
        with open(log_file, "r") as f:
            lines = f.readlines()
        
        # Find the last [TELEMETRY] entry
        for line in reversed(lines[-200:]):
            if "[TELEMETRY]" in line:
                # Parse the structured log entry
                stats = {"stage": "Waiting", "status": "Idle", "rows": 0, "throughput": 0, 
                        "elapsed": 0.0, "cpu_cores": 0.0, "ram_gb": 0.0, "ram_percent": 0.0}
                
                parts = line.split("|")
                for part in parts:
                    part = part.strip()
                    if "=" in part:
                        key, value = part.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == "stage":
                            stats["stage"] = value
                        elif key == "status":
                            stats["status"] = value
                        elif key == "rows":
                            stats["rows"] = int(value)
                        elif key == "throughput":
                            stats["throughput"] = int(value)
                        elif key == "elapsed":
                            stats["elapsed"] = float(value)
                        elif key == "cpu_cores":
                            stats["cpu_cores"] = float(value)
                        elif key == "ram_gb":
                            stats["ram_gb"] = float(value)
                        elif key == "ram_percent":
                            stats["ram_percent"] = float(value)
                
                return stats
        
        # No telemetry found
        return {"stage": "Waiting", "status": "Ready", "rows": 0, "throughput": 0, 
                "elapsed": 0.0, "cpu_cores": 0.0, "ram_gb": 0.0, "ram_percent": 0.0}
    except Exception as e:
        return {"error": f"Parse error: {str(e)}"}

def trigger_stage(stage_code):
    """Triggers the pipeline orchestrator directly via subprocess."""
    try:
        if stage_code == "all":
            st.session_state.current_stage_idx = 0
            
        subprocess.Popen(
            ["python3", str(BASE_DIR / "run_pipeline.py"), "--stage", stage_code],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        st.toast(f"Starting {stage_code.upper()}...", icon="🚀")
    except Exception as e:
        st.error(f"Execution failed: {str(e)}")

# --- UI Header ---
st.markdown(f"""
<div class="header">
    <div class="logo-container">
        <div class="logo-icon">P</div>
        <div class="logo-text">Pure<span>Storage</span></div>
        <div style="color: var(--text-secondary); border-left: 1px solid var(--pure-gray-light); padding-left: 1rem; margin-left: 0.5rem; font-size: 0.8rem;">
            AI/ML Fraud Detection Pipeline Demo
        </div>
    </div>
    <div class="header-badges">
        <div class="badge badge-orange">NVIDIA GPU</div>
        <div class="badge badge-live">● LIVE</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- State Management ---
if 'current_stage_idx' not in st.session_state:
    st.session_state.current_stage_idx = 0

# --- Real-Time Dashboard Fragment ---
@st.fragment(run_every=1)
def render_dashboard():
    # --- Stage Navigation ---
    stats = get_stats()
    active_stage = stats.get("stage", "Waiting")
    status = stats.get("status", "Idle")

    stage_map = {
        "Ingest": 0,
        "Data Prep": 1,
        "Model Train": 2,
        "Inference": 3,
        "Waiting": -1
    }
    
    # Auto-switch to current stage if it's further ahead in the pipeline
    if active_stage in stage_map:
        new_idx = stage_map[active_stage]
        # Auto-advance if the detected stage is further ahead than our view
        if 0 <= new_idx > st.session_state.current_stage_idx:
            st.session_state.current_stage_idx = new_idx
            st.toast(f"Moving to {active_stage}...", icon="⏩")
        
    curr_active_idx = stage_map.get(active_stage, -1)

    nav_cols = st.columns([1, 10, 1])
    with nav_cols[1]:
        pills_html = '<div class="stage-nav">'
        for i, name in enumerate(STAGES):
            cls = "stage-pill"
            # Highlight as completed if it's before the current active stage
            # OR if it IS the active stage and it's marked as Completed
            if i < curr_active_idx or (i == curr_active_idx and status == "Completed"):
                cls += " completed"
                icon = "✓ "
            elif i == st.session_state.current_stage_idx:
                cls += " active"
                icon = ""
            else:
                icon = ""
            pills_html += f'<div class="{cls}">{icon}{name}</div>'
        pills_html += '</div>'
        st.markdown(pills_html, unsafe_allow_html=True)

    # Wrap index to ensure it's valid for display
    display_idx = max(0, min(st.session_state.current_stage_idx, len(STAGES) - 1))
    
    # Check if the displayed stage is completed
    # (either it is the active stage and status is Completed, OR an even later stage is active)
    is_completed = (active_stage == STAGES[display_idx] and status == "Completed") or (curr_active_idx > display_idx)

    # --- Main Dashboard Component ---
    header_status = ""
    if is_completed:
        header_status = f'<div style="background: var(--success-green); color: white; display: inline-block; padding: 4px 16px; border-radius: 20px; font-weight: bold; margin-bottom: 1rem;">✓ STAGE COMPLETE</div>'
    elif active_stage == STAGES[display_idx] and status == "Running":
        header_status = f'<div style="background: var(--pure-orange); color: white; display: inline-block; padding: 4px 16px; border-radius: 20px; font-weight: bold; margin-bottom: 1rem; animation: pulse 2s infinite;">● PROCESSING</div>'

    st.markdown(f"""
        <h1 style="font-weight: 300; margin-bottom: 0;">Stage {display_idx + 1}: <span style="color: var(--pure-orange); font-weight: 600;">{STAGES[display_idx]}</span></h1>
        <p style="color: var(--text-secondary);">{STAGES[display_idx]} phase metrics and status</p>
        {header_status}
    </div>
    """, unsafe_allow_html=True)

    # Main Grid
    col1, col2 = st.columns(2)

    # If stage is completed, we want to show it as 100% full even if telemetry is "Waiting" for next
    rows = stats.get("rows", 0)
    throughput = stats.get("throughput", 0)
    elapsed = stats.get("elapsed", 0.0)
    velocity = (throughput * 256) / (1024**3) if throughput > 0 else 0
    status_val = stats.get("status", "Idle")

    # If this specific stage is already finished, override with "final" feel
    if is_completed and active_stage != STAGES[display_idx]:
        # For historical stages, we don't have their final counts easily in the latest telemetry 
        # unless we parse the whole log. For now, let's at least show the bar as full.
        progress = 1.0
        display_rows = "Finalized"
    else:
        progress = min(rows / TOTAL_ROWS_TARGET, 1.0)
        display_rows = f"{rows:,}"

    if is_completed:
        progress = 1.0

    # Stage-specific Metric Labels
    if display_idx == 0: # Ingest
        m1_label, m2_label = "ROWS COLLECTED", "STREAM SPEED"
        m2_val = f"{throughput:,.0f} rows/s" if not is_completed else "Finished"
    elif display_idx == 1: # Prep
        m1_label, m2_label = "ROWS TRANSFORMED", "PREP VELOCITY"
        m2_val = f"{velocity:.2f} GB/s" if not is_completed else "Finished"
    elif display_idx == 2: # Train
        m1_label, m2_label = "SAMPLES TRAINED", "TRAINING STATUS"
        m2_val = status_val
    else: # Inference
        m1_label, m2_label = "INFERENCE SAMPLES", "THROUGHPUT"
        m2_val = f"{throughput:,.0f} samples/s" if not is_completed else f"Model Tested"

    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{m1_label}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{display_rows}</div>', unsafe_allow_html=True)
        st.progress(progress)
        
        if is_completed:
            display_text = f'<div style="display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.7rem; color: var(--success-green);"><span>100% complete</span><span>Finalized</span></div></div>'
        elif rows > TOTAL_ROWS_TARGET:
            display_text = f'<div style="display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.7rem; color: var(--text-secondary);"><span>Target exceeded</span><span>of {rows:,}</span></div></div>'
        else:
            display_text = f'<div style="display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.7rem; color: var(--text-secondary);"><span>{int(progress*100)}% complete</span><span>of {TOTAL_ROWS_TARGET:,}</span></div></div>'
        
        st.markdown(display_text, unsafe_allow_html=True)

    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{m2_label}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{m2_val}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="margin-top: 2rem;"><div class="metric-label">ELAPSED TIME</div><div class="metric-value" style="font-family: monospace;">{int(elapsed//60):02d}:{int(elapsed%60):02d}.{int((elapsed*10)%10)}</div></div></div>', unsafe_allow_html=True)

    # ROI banner removed as per user request

# Render the telemetry-driven part of the dashboard
render_dashboard()

# --- Control Bar ---
st.markdown('<div style="height: 150px;"></div>', unsafe_allow_html=True) # Spacer
st.markdown('<div class="control-bar">', unsafe_allow_html=True)

# Create three sections: left nav, center button, right nav
left_col, center_col, right_col = st.columns([1, 3, 1])

with left_col:
    if st.button("← Previous Stage"):
        st.session_state.current_stage_idx = max(0, st.session_state.current_stage_idx - 1)
        st.rerun()

with center_col:
    # Use nested columns to perfectly center the button
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        if st.button("🚀 RUN FULL PIPELINE", key="run_full_pipeline", help="Execute all stages sequentially", type="primary", use_container_width=True):
            trigger_stage("all")

with right_col:
    if st.button("Next Stage →"):
        st.session_state.current_stage_idx = min(len(STAGES) - 1, st.session_state.current_stage_idx + 1)
        st.rerun()
st.markdown('</div>', unsafe_allow_html=True)
