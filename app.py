import streamlit as st
import pandas as pd
import nflreadpy as nfl
import requests

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
@st.cache_data(ttl=3600)
def load_rosters():
    return nfl.load_rosters([2026]).to_pandas()
try:
    with st.spinner("Loading 2026 NFL play-by-play..."):
        pbp = load_pbp()
        rosters = load_rosters()
        
    st.success("✅ NFL play-by-play connected")

    # Clean week display
    current_week = int(pbp["week"].dropna().max())

    st.write(
        f"📊 **Model Data:** 2026 season through Week {current_week} | "
        f"**Plays loaded:** {len(pbp):,}"
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
    rush["GL"] = (rush["yardline_100"] <= 3).astype(int)
    rush["I5"] = (rush["yardline_100"] <= 5).astype(int)
    rush["Rush_TD"] = (rush["touchdown"] == 1).astype(int)
    rush_summary = (
        rush.groupby(
            ["rusher_player_id", "rusher_player_name", "posteam"],
            dropna=False
        )
        .agg(
            Rush_Att=("rush_attempt", "sum"),
            RZ_Rush=("RZ", "sum"),
            I10_Rush=("I10", "sum"),
            I5_Rush=("I5", "sum"),
            GL_Carries=("GL", "sum"),
            Rush_TD=("Rush_TD", "sum")
        )
        .reset_index()
        .rename(columns={
            "rusher_player_id": "Player_ID",
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
    targets["GL"] = (targets["yardline_100"] <= 3).astype(int)
    targets["Rec_TD"] = (targets["touchdown"] == 1).astype(int)
    rec_summary = (
        targets.groupby(
            ["receiver_player_id", "receiver_player_name", "posteam"],
            dropna=False
        )
        .agg(
            Targets=("receiver_player_name", "count"),
            RZ_Tgt=("RZ", "sum"),
            I10_Tgt=("I10", "sum"),
            I5_Tgt=("I5", "sum"),
            GL_Targets=("GL", "sum"),
            Rec_TD=("Rec_TD", "sum")
        )
        .reset_index()
        .rename(columns={
            "receiver_player_id": "Player_ID",
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
        how="outer",
        suffixes=("_rush", "_rec")
    )

    board["Player_ID"] = (
        board["Player_ID_rush"]
        .combine_first(board["Player_ID_rec"])
    )

    board = board.drop(
        columns=["Player_ID_rush", "Player_ID_rec"]
    ).fillna(0)
    # ------------------------------
    # PLAYER POSITION
    # ------------------------------
    # Use official roster positions
    roster_pos = (
        rosters[["gsis_id", "team", "position"]]
        .dropna(subset=["gsis_id"])
        .drop_duplicates(subset=["gsis_id"])
        .rename(columns={
            "gsis_id": "Player_ID",
            "team": "Team",
            "position": "Position"
        })
    )

    board = board.merge(
        roster_pos,
        on=["Player_ID", "Team"],
        how="left"
    )

    
  

    numeric_cols = [
        "Rush_Att",
        "RZ_Rush",
        "I10_Rush",
        "I5_Rush",
        "GL_Carries",
        "Rush_TD",
        "Targets",
        "RZ_Tgt",
        "I10_Tgt",
        "I5_Tgt",
        "GL_Targets",
        "Rec_TD"
    ]

    for col in numeric_cols:
        board[col] = board[col].astype(int)
    # ------------------------------
    # ------------------------------
    # QB RUSHING TD THREAT
    # ------------------------------
    def qb_rush_threat(row):
        if row["Position"] != "QB":
            return ""

        if (
            row["GL_Carries"] >= 1
            or row["I5_Rush"] >= 2
            or row["I10_Rush"] >= 3
        ):
            return "🔥🔥 HIGH"

        elif (
            row["I10_Rush"] >= 1
            or row["RZ_Rush"] >= 2
            or row["Rush_Att"] >= 5
        ):
            return "🔥 MEDIUM"

        else:
            return "LOW"

    board["QB_Rush_Threat"] = board.apply(qb_rush_threat, axis=1)
    # -----------------------------
    # TOTAL TD OPPORTUNITIES
    # -----------------------------
    board["RZ_Opp"] = board["RZ_Rush"] + board["RZ_Tgt"]
    board["I10_Opp"] = board["I10_Rush"] + board["I10_Tgt"]
    board["I5_Opp"] = board["I5_Rush"] + board["I5_Tgt"]
    board["GL_Opp"] = board["GL_Carries"] + board["GL_Targets"]

    board["TDs"] = board["Rush_TD"] + board["Rec_TD"]
    # ------------------------------
    # RUSH / RECEIVING TD SIGNALS
    # ------------------------------
    def rush_td_signal(row):
        if (
            row["GL_Carries"] >= 1
            or row["I5_Rush"] >= 2
            or row["I10_Rush"] >= 3
        ):
            return "HIGH"
        elif (
            row["I5_Rush"] >= 1
            or row["I10_Rush"] >= 1
            or row["RZ_Rush"] >= 2
        ):
            return "MEDIUM"
        else:
            return "LOW"

    def rec_td_signal(row):
        if (
            row["GL_Targets"] >= 1
            or row["I5_Tgt"] >= 2
            or row["I10_Tgt"] >= 3
        ):
            return "HIGH"
        elif (
            row["I5_Tgt"] >= 1
            or row["I10_Tgt"] >= 1
            or row["RZ_Tgt"] >= 2
        ):
            return "MEDIUM"
        else:
            return "LOW"

    board["Rush_TD_Signal"] = board.apply(rush_td_signal, axis=1)
    board["Rec_TD_Signal"] = board.apply(rec_td_signal, axis=1)
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
        "Position",
        "QB_Rush_Threat",
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
    # -----------------------------
    # DEFENSIVE TD VULNERABILITY
    # -----------------------------
    st.divider()
    st.subheader("🛡️ Opponent TD Vulnerability")

    # Rushing opportunities allowed
    def_rush = (
        rush.groupby("defteam")
        .agg(
            RZ_Rush_Allowed=("RZ", "sum"),
            I10_Rush_Allowed=("I10", "sum"),
            I5_Rush_Allowed=("I5", "sum"),
            Rush_TD_Allowed=("Rush_TD", "sum")
        )
        .reset_index()
        .rename(columns={"defteam": "Defense"})
    )

    # Receiving opportunities allowed
    def_rec = (
        targets.groupby("defteam")
        .agg(
            RZ_Tgt_Allowed=("RZ", "sum"),
            I10_Tgt_Allowed=("I10", "sum"),
            I5_Tgt_Allowed=("I5", "sum"),
            Rec_TD_Allowed=("Rec_TD", "sum")
        )
        .reset_index()
        .rename(columns={"defteam": "Defense"})
    )

    defense_board = pd.merge(
        def_rush,
        def_rec,
        on="Defense",
        how="outer"
    ).fillna(0)

    def_numeric = [
        "RZ_Rush_Allowed",
        "I10_Rush_Allowed",
        "I5_Rush_Allowed",
        "Rush_TD_Allowed",
        "RZ_Tgt_Allowed",
        "I10_Tgt_Allowed",
        "I5_Tgt_Allowed",
        "Rec_TD_Allowed"
    ]

    for col in def_numeric:
        defense_board[col] = defense_board[col].astype(int)

    # Total scoring-area opportunities allowed
    defense_board["RZ_Opp_Allowed"] = (
        defense_board["RZ_Rush_Allowed"] +
        defense_board["RZ_Tgt_Allowed"]
    )

    defense_board["I10_Opp_Allowed"] = (
        defense_board["I10_Rush_Allowed"] +
        defense_board["I10_Tgt_Allowed"]
    )

    defense_board["I5_Opp_Allowed"] = (
        defense_board["I5_Rush_Allowed"] +
        defense_board["I5_Tgt_Allowed"]
    )

    defense_board["TD_Allowed"] = (
        defense_board["Rush_TD_Allowed"] +
        defense_board["Rec_TD_Allowed"]
    )

    # Rank most vulnerable defenses first
    defense_board = defense_board.sort_values(
        by=[
            "I5_Opp_Allowed",
            "I10_Opp_Allowed",
            "RZ_Opp_Allowed"
        ],
        ascending=False
    )

    defense_board.insert(
        0,
        "Rank",
        range(1, len(defense_board) + 1)
    )

    defense_display = [
        "Rank",
        "Defense",
        "RZ_Opp_Allowed",
        "I10_Opp_Allowed",
        "I5_Opp_Allowed",
        "RZ_Rush_Allowed",
        "RZ_Tgt_Allowed",
        "Rush_TD_Allowed",
        "Rec_TD_Allowed",
        "TD_Allowed"
    ]

    st.dataframe(
        defense_board[defense_display],
        hide_index=True,
        use_container_width=True
    )
        # -----------------------------
    # UPCOMING MATCHUPS
    # -----------------------------
    st.divider()
    st.subheader("🎯 TD Match")
    slate = st.selectbox(
        "Select slate",
        [
            "All Games",
            "Thursday",
            "Sunday Early",
            "Sunday Late",
            "Sunday Night",
            "Monday Night"
        ]
    )
    @st.cache_data(ttl=3600)
    def load_schedule():
        return nfl.load_schedules([2026]).to_pandas()

    schedule = load_schedule()

    # Select the NFL week using scheduled game dates, not the latest
    # play-by-play week (which can lag while games are being played).
    now_et = pd.Timestamp.now(tz="America/New_York")
    reg_schedule = schedule.loc[schedule["game_type"] == "REG"].copy()
    reg_schedule["game_date"] = pd.to_datetime(
        reg_schedule["gameday"], errors="coerce"
    ).dt.date
    valid_games = reg_schedule.dropna(subset=["game_date"]).copy()
    if valid_games.empty:
        st.warning("NFL schedule dates are unavailable.")
        st.stop()

    week_dates = valid_games.groupby("week")["game_date"].agg(["min", "max"]).sort_index()
    today = now_et.date()
    # A week remains active through its last scheduled game. Between weeks,
    # show the next scheduled week rather than guessing from PBP coverage.
    active_weeks = week_dates.loc[week_dates["max"] >= today]
    next_week = int(active_weeks.index[0]) if not active_weeks.empty else int(week_dates.index[-1])
    next_games = reg_schedule.loc[reg_schedule["week"] == next_week].copy()
   # Create team -> opponent map
    matchup_rows = []

    for _, game in next_games.iterrows():
        matchup_rows.append({
            "Team": game["home_team"],
            "Opp": game["away_team"]
        })
        matchup_rows.append({
            "Team": game["away_team"],
            "Opp": game["home_team"]
        })

    matchup_map = pd.DataFrame(matchup_rows)

    # Add upcoming opponent to player board
    td_match = board.merge(
        matchup_map,
        on="Team",
        how="inner"
    )

    # Restrict TD Match to eligible offensive skill positions.
    td_match = td_match[td_match["Position"].isin(["QB", "RB", "WR", "TE"])].copy()

    # Add opponent defensive vulnerability
    td_match = td_match.merge(
        defense_board,
        left_on="Opp",
        right_on="Defense",
        how="left",
        suffixes=("", "_DEF")
    )

    # -----------------------------
    # PER-GAME OPPORTUNITY NORMALIZATION
    # Player games with an actual rush or target
    appearances = pd.concat([
        rush[["rusher_player_id", "posteam", "game_id"]].rename(columns={"rusher_player_id":"Player_ID","posteam":"Team"}),
        targets[["receiver_player_id", "posteam", "game_id"]].rename(columns={"receiver_player_id":"Player_ID","posteam":"Team"})
    ], ignore_index=True).dropna(subset=["Player_ID", "game_id"])
    player_games = appearances.groupby(["Player_ID","Team"])["game_id"].nunique().rename("Games_Played").reset_index()
    td_match = td_match.merge(player_games, on=["Player_ID","Team"], how="left")
    td_match["Games_Played"] = td_match["Games_Played"].fillna(1).clip(lower=1)
    defense_games = pbp[["defteam","game_id"]].dropna().drop_duplicates().groupby("defteam")["game_id"].nunique()
    td_match["Defense_Games"] = td_match["Opp"].map(defense_games).fillna(1).clip(lower=1)
    for col in ["RZ_Opp","I10_Opp","I5_Opp","GL_Opp"]:
        td_match[col+"_PG"] = td_match[col] / td_match["Games_Played"]
    for col in ["RZ_Opp_Allowed","I10_Opp_Allowed","I5_Opp_Allowed","TD_Allowed"]:
        td_match[col+"_PG"] = td_match[col].fillna(0) / td_match["Defense_Games"]

    # FIRST TD MATCH SCORE
    # -----------------------------
    # Offensive opportunity component
    # Shrink low-sample per-game rates toward the position group's
    # observed baseline; five games provides approximately 50% weight.
    rate_cols = ["RZ_Opp_PG", "I10_Opp_PG", "I5_Opp_PG", "GL_Opp_PG"]
    for col in rate_cols:
        baseline = td_match.groupby("Position")[col].transform("median").fillna(td_match[col].median())
        reliability = td_match["Games_Played"] / (td_match["Games_Played"] + 5)
        td_match[col + "_Adj"] = (
            reliability * td_match[col] + (1 - reliability) * baseline
        )
    td_match["Data_Weight"] = (
        100 * td_match["Games_Played"] / (td_match["Games_Played"] + 5)
    ).round(0).astype(int)

    # Position-specific opportunity score. Keep the existing model's
    # scoring scale while emphasizing each position's scoring path.
    td_match["Rush_Path"] = (
        td_match["I10_Rush"] / td_match["Games_Played"]
    ).clip(0, 2) / 2 * 25 + (
        td_match["I5_Rush"] / td_match["Games_Played"]
    ).clip(0, 1) * 35 + (
        td_match["GL_Carries"] / td_match["Games_Played"]
    ).clip(0, 0.6) / 0.6 * 40
    td_match["Rec_Path"] = (
        td_match["RZ_Tgt"] / td_match["Games_Played"]
    ).clip(0, 2) / 2 * 30 + (
        td_match["I10_Tgt"] / td_match["Games_Played"]
    ).clip(0, 1.2) / 1.2 * 30 + (
        td_match["I5_Tgt"] / td_match["Games_Played"]
    ).clip(0, 0.7) / 0.7 * 40
    # Smooth position paths for players with limited observed games.
    for col in ["Rush_Path", "Rec_Path"]:
        prior = td_match.groupby("Position")[col].transform("median").fillna(0)
        weight = td_match["Games_Played"] / (td_match["Games_Played"] + 5)
        td_match[col + "_Adj"] = weight * td_match[col] + (1 - weight) * prior

    td_match["Offense_Score"] = (
        td_match["RZ_Share"].clip(0, 70) / 70 * 20
        + td_match["I10_Opp_PG_Adj"].clip(0, 2) / 2 * 10
        + td_match["I5_Opp_PG_Adj"].clip(0, 1) / 1 * 20
        + td_match["GL_Opp_PG_Adj"].clip(0, 0.6) / 0.6 * 20
        + td_match["RZ_Opp_PG_Adj"].clip(0, 3) / 3 * 30
   )

    # Combine position pathways with the original opportunity score.
    # WR/TE are evaluated primarily on receiving chances; RB on rushing,
    # and QB on rushing while preserving the existing QB bonus.
    position_mix = {"RB": (0.70, 0.30), "WR": (0.10, 0.90),
                    "TE": (0.10, 0.90), "QB": (0.85, 0.15)}
    rush_weight = td_match["Position"].map(
        {pos: weights[0] for pos, weights in position_mix.items()}
    ).fillna(0.5)
    rec_weight = 1 - rush_weight
    td_match["Position_Score"] = (
        rush_weight * td_match["Rush_Path_Adj"]
        + rec_weight * td_match["Rec_Path_Adj"]
    )
    td_match["Offense_Score"] = (
        td_match["Offense_Score"] * 0.65
        + td_match["Position_Score"] * 0.35
    )

    # Defensive vulnerability component
    td_match["Defense_Score"] = (
        td_match["I5_Opp_Allowed_PG"].clip(0, 2) / 2 * 40
        + td_match["I10_Opp_Allowed_PG"].clip(0, 3) / 3 * 30
        + td_match["RZ_Opp_Allowed_PG"].clip(0, 5) / 5 * 20
        + td_match["TD_Allowed_PG"].clip(0, 3) / 3 * 10
    )

    # 65% player opportunity / 35% opponent vulnerability
    td_match["TD_Match"] = (
        td_match["Offense_Score"] * 0.65
        + td_match["Defense_Score"] * 0.35
    ).round(1)
    td_match["QB_Bonus"] = 0

    td_match.loc[
        td_match["QB_Rush_Threat"] == "🔥🔥 HIGH",
        "QB_Bonus"
    ] = 6

    td_match.loc[
        td_match["QB_Rush_Threat"] == "🔥 MEDIUM",
        "QB_Bonus"
    ] = 3

    td_match["TD_Match"] = (
        td_match["TD_Match"] + td_match["QB_Bonus"]
    ).clip(0, 100).round(1)
    td_match = td_match.sort_values(
        "TD_Match",
        ascending=False
    ).reset_index(drop=True)

    td_match.insert(
        0,
        "TD_Rank",
        range(1, len(td_match) + 1)
    )
    td_match.insert(1, "Team_Rank", td_match.groupby("Team").cumcount() + 1)
    td_match["TD_Grade"] = pd.cut(
    td_match["TD_Match"],
    bins=[-float("inf"), 45, 60, 75, 90, float("inf")],
    labels=[
        "WEAK",
        "MODERATE",
        "GOOD",
        "STRONG",
        "ELITE"
    ],
    right=False
) 
    # ------------------------------
    # FINAL ANYTIME TD BET TIER
    # ------------------------------
    def td_bet_tier(row):
        match = row["TD_Match"]
        grade = str(row["TD_Grade"])
        rush_sig = row["Rush_TD_Signal"]
        rec_sig = row["Rec_TD_Signal"]

        high_path = (
            rush_sig == "HIGH"
            or rec_sig == "HIGH"
            or row["QB_Rush_Threat"] == "🔥🔥 HIGH"
        )

        medium_path = (
            rush_sig == "MEDIUM"
            or rec_sig == "MEDIUM"
            or row["QB_Rush_Threat"] == "🔥 MEDIUM"
        )

        if match >= 90 and high_path and row["Games_Played"] >= 3:
            return "💎 TOP PLAY"

        elif match >= 75 and (high_path or medium_path) and row["Games_Played"] >= 2:
            return "STRONG BET"

        elif match >= 60 and high_path:
            return "✅ PLAYABLE"

        elif match >= 50 and (high_path or medium_path):
            return "👀 LEAN"

        else:
            return "PASS"


    td_match["Bet_Tier"] = td_match.apply(td_bet_tier, axis=1)
    td_match_display = [
        "TD_Rank",
        "Team_Rank",
        "Player",
        "Team",
        "Opp",
        "Position",
        "TD_Match",
        "RZ_Share",
        "Games_Played",
        "Data_Weight",
        "RZ_Opp_PG",
        "I5_Opp_PG",
        "TD_Grade",
        "Rush_TD_Signal",
        "Rec_TD_Signal",
        "Bet_Tier",
        "RZ_Opp",
        "QB_Rush_Threat",
        "I10_Opp",
        "I5_Opp",
        "GL_Opp",
        "I5_Opp_Allowed",
        "I10_Opp_Allowed",
        "TD_Allowed"
    ]    

    # Keep an all-games copy for results matching before applying the
    # viewer's slate selection to the visible prediction board.
    tracker_ratings = td_match.copy()
    slate_games = next_games.copy()
    # ------------------------------
    # SLATE FILTER
    # ------------------------------
    next_games["Game_Hour"] = pd.to_datetime(
        next_games["gametime"],
        format="%H:%M",
        errors="coerce"
    ).dt.hour

    if slate == "Thursday":
        slate_games = slate_games[
            next_games["weekday"] == "Thursday"
        ].copy()

    elif slate == "Sunday Early":
        slate_games = slate_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] < 16)
        ].copy()

    elif slate == "Sunday Late":
        slate_games = slate_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] >= 16) &
            (next_games["Game_Hour"] < 20)
        ].copy()

    elif slate == "Sunday Night":
        slate_games = slate_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] >= 20)
        ].copy()

    elif slate == "Monday Night":
        slate_games = slate_games[
            next_games["weekday"] == "Monday"
       ].copy()

    if slate != "All Games":
        visible_teams = set(slate_games["home_team"]).union(set(slate_games["away_team"]))
        td_match = td_match.loc[td_match["Team"].isin(visible_teams)].copy()

    st.write(f"**Upcoming week:** {next_week}")

    def color_td_match(val):
        try:
            val = float(val)

            if val >= 70:
                return "background-color: #0b6623; color: white; font-weight: bold;"
            elif val >= 60:
                return "background-color: #2e8b57; color: white; font-weight: bold;"
            elif val >= 50:
                return "background-color: #d4ac0d; color: black; font-weight: bold;"
            elif val >= 40:
                return "background-color: #d97706; color: white; font-weight: bold;"
            else:
                return "background-color: #9b1c1c; color: white; font-weight: bold;"
        except:
            return ""
    def color_rz_share(val):
        try:
            val = float(val)

            if val >= 50:
                return "background-color: #0b6623; color: white; font-weight: bold;"
            elif val >= 35:
                return "background-color: #2e8b57; color: white; font-weight: bold;"
            elif val >= 25:
                return "background-color: #d4ac0d; color: black; font-weight: bold;"
            elif val >= 15:
                return "background-color: #d97706; color: white; font-weight: bold;"
            else:
                return "background-color: #9b1c1c; color: white; font-weight: bold;"
        except:
            return ""
    def color_def_vulnerability(val):
        try:
            val = float(val)

            if val >= 8:
                return "background-color: #0b6623; color: white; font-weight: bold;"
            elif val >= 6:
                return "background-color: #2e8b57; color: white; font-weight: bold;"
            elif val >= 4:
               return "background-color: #d4ac0d; color: black; font-weight: bold;"
            elif val >= 2:
                return "background-color: #d97706; color: white; font-weight: bold;"
            else:
                return "background-color: #9b1c1c; color: white; font-weight: bold;"
        except:
            return ""
    styled_td = (
       td_match[td_match_display]
       .style
      .map(
          color_td_match,
          subset=["TD_Match"]
      )
      .map(
          color_rz_share,
          subset=["RZ_Share"]
    )
     .map(
         color_def_vulnerability,
         subset=["I5_Opp_Allowed", "I10_Opp_Allowed", "TD_Allowed"]
    )   
        .format({
          
          "TD_Match": "{:.1f}",
          "RZ_Share": "{:.1f}",
          "RZ_Opp_PG": "{:.2f}",
          "I5_Opp_PG": "{:.2f}",
          "I5_Opp_Allowed": "{:.0f}",
          "I10_Opp_Allowed": "{:.0f}",
          "TD_Allowed": "{:.0f}"
      })
  )

    st.dataframe(
        styled_td,
        hide_index=True,
        use_container_width=True
    )
  


    # -----------------------------
    # LIVE TD RESULTS TRACKER (ESPN game boxscores, independent of delayed PBP)
    # -----------------------------
    st.divider()
    st.subheader("🏈 Live TD Results")
    st.caption("Live game boxscores from ESPN; TD Match ratings are current, not saved pregame values.")

    @st.cache_data(ttl=60, show_spinner=False)
    def fetch_live_td_results(season, week):
        base = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; TDMatch/1.0)"})
        response = session.get(
            base + "/scoreboard",
            params={"season": season, "seasontype": 2, "week": week, "limit": 50},
            timeout=12,
        )
        response.raise_for_status()
        rows = []
        games_seen = 0
        for event in response.json().get("events", []):
            competition = (event.get("competitions") or [{}])[0]
            status = competition.get("status", {}).get("type", {})
            if status.get("name") == "STATUS_SCHEDULED":
                continue
            games_seen += 1
            try:
                game_response = session.get(
                    base + "/summary", params={"event": event["id"]}, timeout=12
                )
                game_response.raise_for_status()
                boxscore = game_response.json().get("boxscore", {})
                for team_entry in boxscore.get("players", []):
                    team = team_entry.get("team", {}).get("abbreviation", "")
                    for category in team_entry.get("statistics", []):
                        cat = category.get("name", "").lower()
                        if cat not in ("rushing", "receiving"):
                            continue
                        labels = [str(v).upper() for v in category.get("labels", [])]
                        if "TD" not in labels:
                            continue
                        td_index = labels.index("TD")
                        for athlete in category.get("athletes", []):
                            stats = athlete.get("stats", [])
                            if td_index >= len(stats):
                                continue
                            try:
                                td_count = int(float(stats[td_index]))
                            except (ValueError, TypeError):
                                continue
                            if td_count <= 0:
                                continue
                            player = athlete.get("athlete", {})
                            rows.append({
                                "Player": player.get("displayName", ""),
                                "Team": team,
                                "Actual_TDs": td_count,
                                "TD_Type": "Rush" if cat == "rushing" else "Receiving",
                                "ESPN_ID": str(player.get("id", "")),
                            })
            except (requests.RequestException, KeyError, ValueError):
                continue
        return rows, games_seen

    try:
        live_rows, live_games = fetch_live_td_results(2026, next_week)
        if not live_rows:
            st.info(
                "No rushing or receiving touchdowns available from ESPN yet. "
                "Games may not have started or the live feed may be delayed."
            )
        else:
            live_df = pd.DataFrame(live_rows)
            # One row per scorer; rushing + receiving TDs both count.
            live_df = live_df.groupby(["Player", "Team"], as_index=False).agg(
                Actual_TDs=("Actual_TDs", "sum"),
                TD_Types=("TD_Type", lambda x: ", ".join(sorted(set(x))))
            )
            # Resolve ESPN full names to nflverse/GSIS player IDs.
            # Normalize punctuation, suffixes, and common team aliases;
            # require unique matches so no player receives a false rank.
            import re
            import unicodedata

            def normalized_name(value):
                value = unicodedata.normalize("NFKD", str(value))
                value = "".join(c for c in value if not unicodedata.combining(c))
                parts = re.sub(r"[^a-z0-9 ]", " ", value.lower()).split()
                while parts and parts[-1] in {"jr", "sr", "ii", "iii", "iv", "v"}:
                    parts.pop()
                return " ".join(parts)

            def short_key(value):
                parts = normalized_name(value).split()
                return (parts[0][0] + " " + parts[-1]) if len(parts) >= 2 else ""

            team_aliases = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR"}
            live_df["Team"] = live_df["Team"].replace(team_aliases)
            ratings = tracker_ratings[[
                "Player_ID", "Player", "Team", "TD_Rank", "Team_Rank",
                "TD_Match", "RZ_Share", "Bet_Tier"
            ]].copy()
            ratings["Player_ID"] = ratings["Player_ID"].astype(str)
            name_field = next(
                (c for c in ("full_name", "player_name", "display_name", "football_name")
                 if c in rosters.columns), None
            )
            if name_field:
                roster_names = rosters[["gsis_id", name_field]].dropna().drop_duplicates("gsis_id")
                roster_names["gsis_id"] = roster_names["gsis_id"].astype(str)
                ratings = ratings.merge(
                    roster_names.rename(columns={"gsis_id": "Player_ID", name_field: "Roster_Name"}),
                    on="Player_ID", how="left"
                )
            else:
                ratings["Roster_Name"] = pd.NA

            ratings["Full_Key"] = ratings["Roster_Name"].fillna(ratings["Player"]).map(normalized_name)
            ratings["Short_Key"] = ratings["Roster_Name"].fillna(ratings["Player"]).map(short_key)
            # PBP names often use J.Chase; a dot must split initial/surname.
            no_roster = ratings["Roster_Name"].isna()
            ratings.loc[no_roster, "Short_Key"] = ratings.loc[no_roster, "Player"].map(
                lambda n: short_key(str(n).replace(".", " "))
            )
            live_df["Full_Key"] = live_df["Player"].map(normalized_name)
            live_df["Short_Key"] = live_df["Player"].map(short_key)
            rating_cols = ["TD_Rank", "Team_Rank", "TD_Match", "RZ_Share", "Bet_Tier"]

            # First attempt: exact full name + team.
            full_counts = ratings.groupby(["Team", "Full_Key"])["Player_ID"].transform("nunique")
            full_lookup = ratings.loc[
                (full_counts == 1) & (ratings["Full_Key"] != "")
            ].drop_duplicates(["Team", "Full_Key"])
            results = live_df.merge(
                full_lookup[["Team", "Full_Key"] + rating_cols],
                on=["Team", "Full_Key"], how="left", validate="many_to_one"
            )

            # Fallback: first initial + last name, only if unique on team.
            short_counts = ratings.groupby(["Team", "Short_Key"])["Player_ID"].transform("nunique")
            short_lookup = ratings.loc[
                (short_counts == 1) & (ratings["Short_Key"] != "")
            ].drop_duplicates(["Team", "Short_Key"])
            missing = results["TD_Match"].isna()
            if missing.any():
                unmatched = results.loc[missing, ["Team", "Short_Key"]].copy()
                unmatched["_original_index"] = unmatched.index
                matched = unmatched.merge(
                    short_lookup[["Team", "Short_Key"] + rating_cols],
                    on=["Team", "Short_Key"], how="left", validate="many_to_one"
                ).set_index("_original_index")
                for col in rating_cols:
                    results.loc[matched.index, col] = matched[col]
            results["Model_Status"] = results["TD_Match"].notna().map({
                True: "Current rating", False: "No matching rating"
            })
            results = results.sort_values(
                ["Actual_TDs", "Team", "Player"], ascending=[False, True, True]
            )
            st.metric("Recorded offensive TDs", int(results["Actual_TDs"].sum()))
            unmatched_count = int(results["TD_Match"].isna().sum())
            if unmatched_count:
                st.caption(f"{unmatched_count} scorer(s) have no current-week model ranking. Rankings are never guessed.")
            st.dataframe(results[[
                "Player", "Team", "Actual_TDs", "TD_Types", "TD_Rank",
                "Team_Rank", "TD_Match", "RZ_Share", "Bet_Tier", "Model_Status"
            ]], hide_index=True, use_container_width=True)
        st.caption(
            f"ESPN games started/completed: {live_games}. Results refresh when the "
            "app reruns, with a 60-second data cache. No manual upload needed."
        )
    except (requests.RequestException, ValueError, KeyError) as live_error:
        st.warning(f"Live ESPN results temporarily unavailable: {live_error}")

except Exception as e:
    st.error("NFL TD opportunity calculation failed.")
    st.exception(e) 
