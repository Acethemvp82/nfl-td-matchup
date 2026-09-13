import streamlit as st
import pandas as pd

# -----------------------------
# PAGE SETUP
# -----------------------------
st.set_page_config(
    page_title="NFL TD Matchup",
    page_icon="🏈",
    layout="wide"
)

# -----------------------------
# TITLE
# -----------------------------
st.title("🏈 NFL Anytime TD Matchup")
st.caption("Finding the best touchdown opportunities through usage, scoring role, and matchup.")

st.divider()

# -----------------------------
# SIDEBAR
# -----------------------------
st.sidebar.header("TD Matchup Settings")

position = st.sidebar.multiselect(
    "Positions",
    ["RB", "WR", "TE"],
    default=["RB", "WR", "TE"]
)

st.sidebar.info(
    "TD Matchup will evaluate red-zone usage, "
    "goal-line opportunities, team scoring environment, "
    "player usage, and opponent TD vulnerability."
)

# -----------------------------
# TD MATCHUP BOARD
# -----------------------------
st.subheader("🎯 TD Matchup Board")

st.info(
    "NFL data connection coming next. "
    "This board will rank the strongest Anytime TD matchups."
)

# Temporary test table
test_data = pd.DataFrame({
    "Rank": [1, 2, 3],
    "Player": ["Test Player A", "Test Player B", "Test Player C"],
    "Pos": ["RB", "WR", "TE"],
    "Team": ["BUF", "DET", "PHI"],
    "Opp": ["NYJ", "CHI", "DAL"],
    "TD Match": [88, 79, 71]
})

st.dataframe(
    test_data,
    hide_index=True,
    use_container_width=True
)
