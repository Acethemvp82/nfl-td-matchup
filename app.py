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

    # Use the week after the latest completed PBP week
    # Automatically determine the active NFL week
    now = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=4)
    
    reg_schedule = schedule[
        schedule["game_type"] == "REG"
    ].copy()
    
    reg_schedule["game_date"] = pd.to_datetime(
        reg_schedule["gameday"]
    ).dt.date
    
    today = now.date()
    
    active_games = reg_schedule[
        reg_schedule["gameday"].notna()
    ].copy()
    
    # Stay on the current PBP week while that week's schedule is active.
    # Advance only after its games are finished.
    current_week_games = active_games[
        active_games["week"] == current_week
    ]
    
    week_end = pd.to_datetime(
        current_week_games["gameday"]
    ).max().date()
    
    if today > week_end:
        next_week = current_week + 1
    else:
        next_week = current_week

    next_games = schedule[
        (schedule["game_type"] == "REG") &
        (schedule["week"] == next_week)
    ].copy()
    # ------------------------------
    # SLATE FILTER
    # ------------------------------
    next_games["Game_Hour"] = pd.to_datetime(
        next_games["gametime"],
        format="%H:%M",
        errors="coerce"
    ).dt.hour

    if slate == "Thursday":
        next_games = next_games[
            next_games["weekday"] == "Thursday"
        ].copy()

    elif slate == "Sunday Early":
        next_games = next_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] < 16)
        ].copy()

    elif slate == "Sunday Late":
        next_games = next_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] >= 16) &
            (next_games["Game_Hour"] < 20)
        ].copy()

    elif slate == "Sunday Night":
        next_games = next_games[
            (next_games["weekday"] == "Sunday") &
            (next_games["Game_Hour"] >= 20)
        ].copy()

    elif slate == "Monday Night":
        next_games = next_games[
            next_games["weekday"] == "Monday"
       ].copy()
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
    # TD RESULTS TRACKER
    # -----------------------------
    st.divider()
    st.subheader("📈 TD Results Tracking")
    st.caption("Save a pregame snapshot as CSV, then upload it after games finish to score the original predictions. Snapshots are not automatically stored on Streamlit Community Cloud.")

    # The selected slate is already represented by next_games.
    snapshot_games = next_games[["game_id", "gameday", "gametime", "home_team", "away_team"]].copy()
    snapshot_games["kickoff_et"] = pd.to_datetime(
        snapshot_games["gameday"].astype(str) + " " + snapshot_games["gametime"].astype(str),
        errors="coerce"
    ).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    now_et = pd.Timestamp.now(tz="America/New_York")
    future_games = snapshot_games.loc[snapshot_games["kickoff_et"] > now_et].copy()
    future_team_games = pd.concat([
        future_games[["game_id", "home_team"]].rename(columns={"home_team": "Team"}),
        future_games[["game_id", "away_team"]].rename(columns={"away_team": "Team"})
    ], ignore_index=True)
    snapshot_cols = ["game_id", "Player_ID", "Player", "Team", "Opp", "Position",
                     "TD_Rank", "Team_Rank", "TD_Match", "RZ_Share", "Bet_Tier"]
    snapshot = td_match.merge(future_team_games, on="Team", how="inner")
    snapshot = snapshot[snapshot_cols].copy()
    snapshot.insert(0, "Snapshot_UTC", pd.Timestamp.now(tz="UTC").isoformat())
    snapshot.insert(1, "Season", 2026)
    snapshot.insert(2, "Week", next_week)

    if snapshot.empty:
        st.info("No unstarted games in this slate. Select an upcoming slate to save pregame rankings.")
    else:
        st.download_button(
            "💾 Save pregame TD rankings (CSV)",
            data=snapshot.to_csv(index=False).encode("utf-8"),
            file_name=f"nfl_td_pregame_week_{next_week}_{slate.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            help="Save before kickoff. Keep this file to evaluate predictions after games."
        )

    uploaded = st.file_uploader("Upload a saved pregame snapshot to check results", type=["csv"], key="td_results_csv")
    if uploaded is not None:
        historical = pd.read_csv(uploaded, dtype={"Player_ID": str, "game_id": str})
        required = set(snapshot_cols)
        if not required.issubset(historical.columns):
            st.error("This CSV is missing required pregame tracker columns.")
        else:
            # Count unique scoring plays per player and game, avoiding duplicate PBP rows.
            rushing_scores = rush.loc[rush["Rush_TD"].eq(1),
                ["game_id", "play_id", "rusher_player_id"]].rename(
                columns={"rusher_player_id": "Player_ID"})
            receiving_scores = targets.loc[targets["Rec_TD"].eq(1),
                ["game_id", "play_id", "receiver_player_id"]].rename(
                columns={"receiver_player_id": "Player_ID"})
            scores = pd.concat([rushing_scores, receiving_scores], ignore_index=True)
            scores = scores.drop_duplicates(["game_id", "play_id", "Player_ID"])
            scores["game_id"] = scores["game_id"].astype(str)
            scores["Player_ID"] = scores["Player_ID"].astype(str)
            td_counts = scores.groupby(["game_id", "Player_ID"]).size().rename("Actual_TDs").reset_index()

            # Only grade completed games present in PBP. Future/in-progress games stay pending.
            completed_ids = set(schedule.loc[
                schedule["result"].notna() & schedule["result"].astype(str).ne(""),
                "game_id"
            ].astype(str))
            historical["game_id"] = historical["game_id"].astype(str)
            historical["Player_ID"] = historical["Player_ID"].astype(str)
            results = historical.merge(td_counts, on=["game_id", "Player_ID"], how="left")
            results["Status"] = results["game_id"].apply(
                lambda g: "Final" if g in completed_ids else "Pending"
            )
            results["Actual_TDs"] = results["Actual_TDs"].fillna(0).astype(int)
            results["Scored_TD"] = results["Actual_TDs"].gt(0)
            results.loc[results["Status"] != "Final", "Scored_TD"] = pd.NA
            graded = results[results["Status"] == "Final"].copy()
            if graded.empty:
                st.info("No completed games from this snapshot are available in the loaded play-by-play yet.")
            else:
                by_tier = graded.groupby("Bet_Tier", dropna=False).agg(
                    Picks=("Player_ID", "size"),
                    Scorers=("Scored_TD", "sum")
                ).reset_index()
                by_tier["Hit_Rate"] = (100 * by_tier["Scorers"] / by_tier["Picks"]).round(1)
                st.markdown("**Completed-game results by bet tier**")
                st.dataframe(by_tier, hide_index=True, use_container_width=True)
            st.markdown("**Pregame rankings vs. actual touchdowns**")
            st.dataframe(
                results[["Status", "Player", "Team", "Opp", "TD_Rank", "Team_Rank",
                         "TD_Match", "RZ_Share", "Bet_Tier", "Actual_TDs", "Scored_TD"]],
                hide_index=True, use_container_width=True
            )
            st.download_button("Download scored results", results.to_csv(index=False).encode("utf-8"),
                               file_name="nfl_td_results.csv", mime="text/csv")

except Exception as e:
    st.error("NFL TD opportunity calculation failed.")
    st.exception(e) 
