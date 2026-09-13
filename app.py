import streamlit as st
import pandas as pd
import nflreadpy as nfl

# -----------------------------
# PAGE SETUP
# -----------------------------
st.set_page_config(
    page_title="NFL TD Matchup",
    page_icon="🏈",
    layout="wide"
)

st.title("🏈 NFL Anytime TD Matchup")
st.caption("Finding the best touchdown opportunities through usage, scoring role, and matchup.")

st.divider()

# -----------------------------
# LOAD NFL PLAY-BY-PLAY
# -----------------------------
@st.cache_data(ttl=3600)
def load_pbp():
    pbp = nfl.load_pbp([2026])
    return pbp.to_pandas()

try:
    with st.spinner("Loading 2026 NFL data..."):
        pbp = load_pbp()

    st.success("✅ 2026 NFL data connected!")

    st.subheader("🏈 NFL Data Test")

    st.write(f"Play-by-play rows loaded: **{len(pbp):,}**")

    # Show available weeks
    if "week" in pbp.columns:
        weeks = sorted(pbp["week"].dropna().unique())
        st.write("Weeks available:", weeks)

    # Find players with rushing or receiving opportunities
    rushers = pd.DataFrame()
    receivers = pd.DataFrame()

    if "rusher_player_name" in pbp.columns:
        rushers = (
            pbp["rusher_player_name"]
            .dropna()
            .value_counts()
            .head(25)
            .reset_index()
        )
        rushers.columns = ["Player", "Rush Plays"]

    if "receiver_player_name" in pbp.columns:
        receivers = (
            pbp["receiver_player_name"]
            .dropna()
            .value_counts()
            .head(25)
            .reset_index()
        )
        receivers.columns = ["Player", "Target Plays"]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top Rushers")
        st.dataframe(rushers, hide_index=True, use_container_width=True)

    with col2:
        st.subheader("Top Targeted Players")
        st.dataframe(receivers, hide_index=True, use_container_width=True)

except Exception as e:
    st.error("NFL data did not load.")
    st.exception(e)
