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
st.caption("Building the offensive opportunity side of the TD Matchup model.")

st.divider()

# -----------------------------
# LOAD NFL DATA
# -----------------------------
@st.cache_data(ttl=3600)
def load_pbp():
    return nfl.load_pbp([2026]).to_pandas()

try:
    with st.spinner("Loading 2026 NFL play-by-play..."):
        pbp = load_pbp()

    st.success("✅ NFL play-by-play connected")

    # Clean week display
    current_week = int(pbp["week"].dropna().max())

    st.write(
        f"**2026 plays loaded:** {len(pbp):,}  |  "
        f"**Latest week in data:** {current_week}"
    )

    # -----------------------------
    # RUSHING OPPORTUNITIES
    # -----------------------------
    rush = pbp[
        (pbp["rush_attempt"] == 1) &
        (pbp["rusher_player_name"].notna())
    ].copy()

    rush["RZ"] = (rush["yardline_100"] <= 20).astype(int)
    rush["I10"] = (rush["yardline_100"] <= 10).astype(int)
    rush["I5"] = (rush["yardline_100"] <= 5).astype(int)
    rush["Rush_TD"] = (rush["touchdown"] == 1).astype(int)
    rush_summary = (
        rush.groupby(
            ["rusher_player_name", "posteam"],
            dropna=False
        )
        .agg(
            Rush_Att=("rush_attempt", "sum"),
            RZ_Rush=("RZ", "sum"),
            I10_Rush=("I10", "sum"),
            I5_Rush=("I5", "sum"),
            Rush_TD=("Rush_TD", "sum")
        )
        .reset_index()
        .rename(columns={
            "rusher_player_name": "Player",
            "posteam": "Team"
        })
    )

    # -----------------------------
    # RECEIVING OPPORTUNITIES
    # -----------------------------
    targets = pbp[
        (pbp["receiver_player_name"].notna()) &
        (pbp["pass_attempt"] == 1)
    ].copy()

    targets["RZ"] = (targets["yardline_100"] <= 20).astype(int)
    targets["I10"] = (targets["yardline_100"] <= 10).astype(int)
    targets["I5"] = (targets["yardline_100"] <= 5).astype(int)
    targets["Rec_TD"] = (targets["touchdown"] == 1).astype(int)
    rec_summary = (
        targets.groupby(
            ["receiver_player_name", "posteam"],
            dropna=False
        )
        .agg(
            Targets=("receiver_player_name", "count"),
            RZ_Tgt=("RZ", "sum"),
            I10_Tgt=("I10", "sum"),
            I5_Tgt=("I5", "sum"),
            Rec_TD=("Rec_TD", "sum")
        )
        .reset_index()
        .rename(columns={
            "receiver_player_name": "Player",
            "posteam": "Team"
        })
    )

    # -----------------------------
    # COMBINE RUSH + RECEIVING
    # -----------------------------
    board = pd.merge(
        rush_summary,
        rec_summary,
        on=["Player", "Team"],
        how="outer"
    ).fillna(0)

    numeric_cols = [
        "Rush_Att",
        "RZ_Rush",
        "I10_Rush",
        "I5_Rush",
        "Rush_TD",
        "Targets",
        "RZ_Tgt",
        "I10_Tgt",
        "I5_Tgt",
        "Rec_TD"
    ]

    for col in numeric_cols:
        board[col] = board[col].astype(int)

    # -----------------------------
    # TOTAL TD OPPORTUNITIES
    # -----------------------------
    board["RZ_Opp"] = board["RZ_Rush"] + board["RZ_Tgt"]
    board["I10_Opp"] = board["I10_Rush"] + board["I10_Tgt"]
    board["I5_Opp"] = board["I5_Rush"] + board["I5_Tgt"]

    board["TDs"] = board["Rush_TD"] + board["Rec_TD"]

    # -----------------------------
    # TEAM RED-ZONE SHARE
    # -----------------------------
    team_rz = (
        board.groupby("Team")["RZ_Opp"]
        .sum()
        .rename("Team_RZ_Opp")
    )

    board = board.merge(
        team_rz,
        on="Team",
        how="left"
    )

    board["RZ_Share"] = (
        board["RZ_Opp"] /
        board["Team_RZ_Opp"].replace(0, pd.NA)
    )

    board["RZ_Share"] = (
        board["RZ_Share"]
        .fillna(0)
        .mul(100)
        .round(1)
    )

    # -----------------------------
    # FILTER OUT NON-SKILL PLAYERS
    # -----------------------------
    board = board[
        (board["Rush_Att"] > 0) |
        (board["Targets"] > 0)
    ].copy()

    # Rank by high-value TD opportunities
    board = board.sort_values(
        by=["I5_Opp", "I10_Opp", "RZ_Opp"],
        ascending=False
    )

    board.insert(
        0,
        "Rank",
        range(1, len(board) + 1)
    )

    # -----------------------------
    # DISPLAY
    # -----------------------------
    st.subheader("🎯 Offensive TD Opportunity Board")

    display_cols = [
        "Rank",
        "Player",
        "Team",
        "RZ_Opp",
        "RZ_Share",
        "I10_Opp",
        "I5_Opp",
        "Rush_TD",
        "Rec_TD",
        "TDs"
    ]

    st.dataframe(
        board[display_cols],
        hide_index=True,
        use_container_width=True
    )

except Exception as e:
    st.error("NFL TD opportunity calculation failed.")
    st.exception(e) 
