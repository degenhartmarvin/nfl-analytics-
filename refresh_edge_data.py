#!/usr/bin/env python3
"""Build a combined edge-rusher snapshot from nflverse PBP, PFR weekly defense and snap counts.

DE and OLB roster designations are grouped as Edge Rusher. Interior DT/NT players are excluded.
Unavailable charting metrics are kept null; they are never estimated from unrelated statistics.
"""
import csv, gzip, io, json, os, re, urllib.request, unicodedata
from html.parser import HTMLParser
from collections import defaultdict
from datetime import datetime, timezone

SEASON = int(os.environ.get("NFL_SEASON", "2026"))
PBP_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
DEF_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_{SEASON}.csv"
SNAPS_URL = f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{SEASON}.csv"
OUT = os.environ.get("NFL_EDGE_OUTPUT", "public/data/edge_players_2026.json")
SAVANT_URL = f"https://www.nflsavant.com/leaderboard?season={SEASON}&tab=pressure"
ESPN_WIN_RATE_URL = "https://nfllines.com/defensive-line-ratings/players/"

METRICS = [
 {"key":"sacks","label":"Sacks","category":"Pass-Rush-Produktion","format":"decimal","higher_is_better":True},
 {"key":"sack_rate","label":"Sack Rate (PFR Sacks / Savant Pass-Rush Snaps)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"sacks_per_defensive_snap","label":"Sacks / Defensive Snaps","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pressure_per_defensive_snap","label":"Pressure pro Defensive Snap","category":"Pressure & Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"PFR Pressures geteilt durch Defensive Snaps; kein Ersatz für Pressure Rate pro Pass-Rush-Snap."},
 {"key":"pass_rush_snaps","label":"Pass-Rush Snaps (NFL/Savant Top 20)","category":"Pass-Rush-Einsatz","format":"number","higher_is_better":True},
 {"key":"pressures","label":"Pressures","category":"Pressure & Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"hurries","label":"QB Hurries","category":"Pressure & Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"knockdowns","label":"QB Knockdowns","category":"Pressure & Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"blitzes","label":"Blitzes","category":"Pass-Rush-Einsatz","format":"number","higher_is_better":True},
 {"key":"pressure_rate","label":"Pressure Rate (PFR Pressures / Savant Pass-Rush Snaps)","category":"Pressure & Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"qb_hits","label":"QB Hits","category":"Pass-Rush-Produktion","format":"number","higher_is_better":True},
 {"key":"tfls","label":"Tackles for Loss (TFLs)","category":"Disruptive Plays","format":"number","higher_is_better":True},
 {"key":"forced_fumbles","label":"Forced Fumbles","category":"Disruptive Plays","format":"number","higher_is_better":True},
 {"key":"combined_tackles","label":"Combined Tackles","category":"Run Defense & Tackling","format":"number","higher_is_better":True},
 {"key":"missed_tackles","label":"Missed Tackles","category":"Run Defense & Tackling","format":"number","higher_is_better":False},
 {"key":"missed_tackle_rate","label":"Missed Tackle Rate (Missed / Tackle Attempts)","category":"Run Defense & Tackling","format":"percent","higher_is_better":False},
 {"key":"defensive_snaps","label":"Defensive Snaps","category":"Usage & Belastung","format":"number","higher_is_better":True},
 {"key":"defensive_snap_share","label":"Defensive Snap Share","category":"Usage & Belastung","format":"percent","higher_is_better":True},
 {"key":"sacks_per_game","label":"Sacks per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"pressures_per_game","label":"Pressures per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"tfls_per_game","label":"TFLs per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"quick_pressure_rate","label":"Quick Pressure Rate (unter 2,5 Sek.)","category":"Pressure & Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: die NFL Next Gen Stats Quick-Pressure-Ereignisse liegen nicht im genutzten PFR-Wochendatensatz."},
 {"key":"negative_plays_forced_rate","label":"Negative Plays Forced Rate (Sacks + TFLs je Defensive Snap)","category":"Disruptive Plays","format":"percent","higher_is_better":True},
 {"key":"double_team_rate","label":"Double-Team Rate","category":"Gegnerische Aufmerksamkeit","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: keine verlässlichen individuellen Double-Team-Snap-Zahlen im verwendeten öffentlichen Datensatz."},
 {"key":"pass_rush_win_rate","label":"Pass Rush Win Rate (ESPN, Top 20)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"ESPN veröffentlicht nur die Top 20 der Edge Rusher; Spieler außerhalb der Liste bleiben leer."},
 {"key":"run_stop_win_rate","label":"Run Stop Win Rate (ESPN, Top 10)","category":"Run Defense","format":"percent","higher_is_better":True,"availability_note":"ESPN veröffentlicht nur die Top 10 der Edge Rusher; Spieler außerhalb der Liste bleiben leer."}
]

def download(url):
    request = urllib.request.Request(url, headers={"User-Agent":"NFL-Analytics-Edge-refresh/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()

def parse(raw):
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


class StatTableParser(HTMLParser):
    """Small standard-library HTML table reader that safely ignores nested tables."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.heading = ""
        self.heading_parts = []
        self.in_heading = False
        self.table = None
        self.table_depth = 0
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = True
            self.heading_parts = []
        elif tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.table = {"heading": self.heading, "rows": []}
                self.tables.append(self.table)
        elif tag == "tr" and self.table is not None and self.table_depth == 1:
            self.row = []
        elif tag in ("td", "th") and self.row is not None and self.table_depth == 1:
            self.cell = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        if self.in_heading:
            self.heading_parts.append(value)
        if self.cell is not None and self.table_depth == 1:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.in_heading:
            self.heading = " ".join(self.heading_parts).strip()
            self.in_heading = False
        elif tag in ("td", "th") and self.cell is not None and self.row is not None and self.table_depth == 1:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None and self.table_depth == 1:
            if self.row:
                self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            if self.table_depth == 0:
                self.table = None

def normalize_name(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)

def parse_savant(raw):
    parser = StatTableParser()
    source_text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    parser.feed(source_text)
    print(f"NFL/Savant HTML diagnostic: tables={len(parser.tables)}, bytes={len(source_text)}")
    found = {}
    for table in parser.tables:
        for cells in table["rows"]:
            # NFL/Savant currently renders Pos + Team as one cell (e.g. EDGEBUF),
            # while older table layouts used separate Pos and Team cells.
            if len(cells) < 8 or not cells[0].strip().isdigit():
                continue
            rank = int(cells[0])
            if rank > 20:
                continue
            position = cells[2].upper().replace(" ", "")
            if not any(position.startswith(x) for x in ("EDGE", "DE", "OLB")):
                continue
            name = cells[1]
            # Current layout: rank, player, combined Pos+Team, pressure%,
            # pressures, sacks, QB hits, pass-rush snaps, snap%.
            # Older layout split Pos and Team into separate cells.
            rush_index = 7 if len(cells) == 9 else (6 if len(cells) == 8 else 8)
            rush_snaps = num(cells[rush_index].replace(",", ""))
            if rush_snaps is not None and rush_snaps > 0:
                found[normalize_name(name)] = {"pass_rush_snaps": rush_snaps}
    return found

def parse_espn_win_rates(raw):
    parser = StatTableParser()
    parser.feed(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    result = {"pass_rush_win_rate": {}, "run_stop_win_rate": {}}
    for table in parser.tables:
        heading = table["heading"].lower()
        if "edge rushers" not in heading:
            continue
        key = "pass_rush_win_rate" if "pass rush win rate" in heading else (
            "run_stop_win_rate" if "run stop win rate" in heading else None
        )
        if not key:
            continue
        for cells in table["rows"]:
            if len(cells) < 5 or not cells[0].strip().isdigit():
                continue
            name = cells[2] if len(cells) >= 6 else cells[1]
            rate_cell = cells[4] if len(cells) >= 6 else cells[3]
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", rate_cell)
            if match:
                result[key][normalize_name(name)] = float(match.group(1)) / 100
    return result

def optional_download(url):
    try:
        raw = download(url)
        preview = raw[:500].decode("utf-8", "replace").replace("\\n", " ")
        print(f"Optional source fetched: {url} | bytes={len(raw)} | prefix={preview[:300]!r}")
        return raw
    except Exception as exc:
        print(f"Optional advanced source unavailable ({url}): {exc}")
        return None


def num(value):
    try:
        if value is None or str(value).strip() in ("", "NA", "NaN"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def build(pbp, player_rows, defense_rows=(), snap_rows=(), savant_rows=None, espn_rows=None):
    savant_rows = savant_rows or {}
    espn_rows = espn_rows or {"pass_rush_win_rate": {}, "run_stop_win_rate": {}}
    roster = {}
    for player in player_rows:
        position = str(player.get("position") or "").upper().strip()
        pid = player.get("gsis_id") or player.get("player_id")
        if pid and position in {"DE", "OLB", "EDGE"}:
            roster[pid] = player
    pfr_to_gsis = {}
    for pid, player in roster.items():
        pfr_id = player.get("pfr_id") or player.get("player_pfr_id")
        if pfr_id:
            pfr_to_gsis[pfr_id] = pid

    snap_totals = defaultdict(float)
    player_teams = defaultdict(set)
    team_game_totals = {}
    games = defaultdict(set)
    for row in snap_rows:
        if str(row.get("season","")).strip() != str(SEASON) or str(row.get("game_type","REG")).upper() != "REG":
            continue
        pfr_id = row.get("pfr_player_id") or row.get("player_pfr_id")
        pid = pfr_to_gsis.get(pfr_id)
        snaps = num(row.get("defense_snaps"))
        pct = num(row.get("defense_pct"))
        team = row.get("team") or ""
        game = row.get("game_id") or row.get("pfr_game_id") or ""
        if pid and snaps is not None:
            snap_totals[pid] += snaps
            if team: player_teams[pid].add(team)
            if game and snaps > 0: games[pid].add(game)
        if team and game and snaps is not None and pct is not None and pct > 0:
            pct = pct / 100 if pct > 1 else pct
            team_game_totals[(team, game)] = max(team_game_totals.get((team, game), 0), snaps / pct)
    team_totals = defaultdict(float)
    for (team, _game), total in team_game_totals.items():
        team_totals[team] += total

    totals = defaultdict(lambda: defaultdict(float))
    negative_play_ids = defaultdict(set)
    teams = defaultdict(dict)

    def add(pid, key, amount=1, team=""):
        if pid not in roster:
            return
        totals[pid][key] += amount
        if team:
            teams[pid][team] = teams[pid].get(team, 0) + 1

    for row in pbp:
        if str(row.get("season", SEASON)).strip() != str(SEASON):
            continue
        if str(row.get("game_type","REG")).upper() != "REG":
            continue
        team = row.get("defteam") or ""
        game_id = row.get("game_id") or ""
        play_id = row.get("play_id") or ""
        for i in (1, 2):
            pid = row.get(f"qb_hit_{i}_player_id")
            add(pid, "qb_hits", team=team)
            pid = row.get(f"tackle_for_loss_{i}_player_id")
            add(pid, "tfls", team=team)
            if pid and game_id and play_id:
                negative_play_ids[pid].add((game_id, play_id))
        for i in (1, 2):
            forced_id = row.get(f"forced_fumble_player_{i}_player_id")
            add(forced_id, "forced_fumbles", team=team)
        sack_id = row.get("sack_player_id")
        if sack_id:
            add(sack_id, "sacks", 1, team)
            if game_id and play_id:
                negative_play_ids[sack_id].add((game_id, play_id))
        else:
            for i in (1, 2):
                pid = row.get(f"half_sack_{i}_player_id")
                if pid:
                    add(pid, "sacks", 0.5, team)
                    if game_id and play_id:
                        negative_play_ids[pid].add((game_id, play_id))

    pressures_by_id = defaultdict(float)
    pfr_totals = defaultdict(lambda: defaultdict(float))
    for row in defense_rows:
        if str(row.get("season","")).strip() != str(SEASON) or str(row.get("game_type","REG")).upper() != "REG":
            continue
        pid = pfr_to_gsis.get(row.get("pfr_player_id") or row.get("pfr_id"))
        if not pid:
            continue
        pressure = num(row.get("def_pressures"))
        if pressure is not None:
            pressures_by_id[pid] += pressure
        for source_key, target_key in (("def_sacks", "pfr_sacks"), ("def_times_hurried", "hurries"), ("def_times_hitqb", "knockdowns"), ("def_times_blitzed", "blitzes"), ("def_tackles_combined", "combined_tackles"), ("def_missed_tackles", "missed_tackles")):
            value = num(row.get(source_key))
            if value is not None:
                pfr_totals[pid][target_key] += value
        team = row.get("team") or ""
        if team:
            teams[pid][team] = teams[pid].get(team, 0) + 1

    output = []
    for pid, player in roster.items():
        s = totals[pid]
        snaps = int(snap_totals.get(pid, 0))
        if snaps <= 0 and not any(s.values()) and pressures_by_id.get(pid, 0) <= 0:
            continue
        team = max(teams[pid], key=teams[pid].get) if teams[pid] else (player.get("team") or "")
        name = player.get("display_name") or player.get("full_name") or player.get("name") or pid
        snap_denominator = sum(team_totals[t] for t in player_teams.get(pid, set()))
        pfr = pfr_totals[pid]
        sacks = pfr.get("pfr_sacks") if pfr.get("pfr_sacks") is not None else s["sacks"]
        tfls = s["tfls"]
        negative_plays = len(negative_play_ids[pid])
        combined_tackles = pfr.get("combined_tackles", 0)
        missed_tackles = pfr.get("missed_tackles", 0)
        tackle_attempts = combined_tackles + missed_tackles
        pressures = pressures_by_id.get(pid)
        row = {
            "player_id": pid, "player_name": name, "team": team,
            "roster_position": str(player.get("position") or "").upper(),
            "defensive_snaps": snaps,
            "defensive_snap_share": snaps / snap_denominator if snap_denominator > 0 else None,
            "games_played": len(games[pid]),
            "sacks": sacks, "pressures": pressures or None,
            "pass_rush_snaps": (savant_rows.get(normalize_name(name)) or {}).get("pass_rush_snaps"),
            "hurries": pfr.get("hurries") or None, "knockdowns": pfr.get("knockdowns") or None,
            "blitzes": pfr.get("blitzes") or None,
            "qb_hits": int(s["qb_hits"]), "tfls": int(tfls),
            "forced_fumbles": int(s["forced_fumbles"]),
            "combined_tackles": combined_tackles or None,
            "missed_tackles": missed_tackles if tackle_attempts > 0 else None,
            "missed_tackle_rate": missed_tackles / tackle_attempts if tackle_attempts > 0 else None,
            "sacks_per_game": sacks / len(games[pid]) if games[pid] else None,
            "sacks_per_defensive_snap": sacks / snaps if snaps > 0 else None,
            "sack_rate": sacks / (savant_rows.get(normalize_name(name)) or {}).get("pass_rush_snaps") if (savant_rows.get(normalize_name(name)) or {}).get("pass_rush_snaps", 0) > 0 else None,
            "pressure_rate": pressures / (savant_rows.get(normalize_name(name)) or {}).get("pass_rush_snaps") if pressures is not None and (savant_rows.get(normalize_name(name)) or {}).get("pass_rush_snaps", 0) > 0 else None,
            "pressure_per_defensive_snap": pressures / snaps if pressures is not None and snaps > 0 else None,
            "pass_rush_win_rate": espn_rows.get("pass_rush_win_rate", {}).get(normalize_name(name)),
            "run_stop_win_rate": espn_rows.get("run_stop_win_rate", {}).get(normalize_name(name)),
            "pressures_per_game": pressures / len(games[pid]) if pressures is not None and games[pid] else None,
            "tfls_per_game": tfls / len(games[pid]) if games[pid] else None,
            "negative_plays_forced": negative_plays,
            "negative_plays_forced_rate": negative_plays / snaps if snaps > 0 else None,
            # Do not invent denominators or charting values that are absent from source data.
            "quick_pressure_rate": None,
            "double_team_rate": None
        }
        output.append(row)

    for metric in METRICS:
        key = metric["key"]
        valid = [p for p in output if p.get(key) is not None]
        valid.sort(key=lambda p: p[key], reverse=metric["higher_is_better"])
        previous = object()
        rank = 0
        for index, player in enumerate(valid, 1):
            if player[key] != previous:
                rank = index
            player[key + "_rank"] = rank
            previous = player[key]
    return sorted(output, key=lambda p: (p.get("defensive_snaps") or 0), reverse=True)

def main():
    pbp = parse(download(PBP_URL))
    players = parse(download(PLAYERS_URL))
    defense = parse(download(DEF_URL))
    snaps = parse(download(SNAPS_URL))
    savant_raw = optional_download(SAVANT_URL)
    espn_raw = optional_download(ESPN_WIN_RATE_URL)
    savant_rows = parse_savant(savant_raw) if savant_raw else {}
    # Do not silently publish a snapshot with missing Savant denominator data.
    # The live leaderboard has a top-20 list; fewer than 10 parsed rows signals
    # a source/layout regression and should fail before the JSON snapshot is replaced.
    if len(savant_rows) < 10:
        raise RuntimeError(f"NFL/Savant pass-rush snap parser returned only {len(savant_rows)} rows; refusing to publish incomplete snap data.")
    espn_rows = parse_espn_win_rates(espn_raw) if espn_raw else {"pass_rush_win_rate": {}, "run_stop_win_rate": {}}
    data = build(pbp, players, defense, snaps, savant_rows, espn_rows)
    if not data:
        raise RuntimeError("No edge-rusher data produced; refusing to overwrite snapshot.")
    payload = {
        "season": SEASON,
        "source": "nflverse PFR weekly defense + PBP event stats + snap counts; NFL/Savant top-20 pass-rush snaps; ESPN win rates via NFL Lines",
        "advanced_sources": {"espn_win_rates": ESPN_WIN_RATE_URL},
        "source_url": DEF_URL, "snap_counts_url": SNAPS_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(data), "players": data, "metrics": METRICS,
        "limitations": [
            "The combined group uses the roster positions DE, OLB and EDGE; public roster data does not reliably identify each team's defensive front, so some 4-3 off-ball OLB designations may be included.",
            "Pass-Rush Snaps are imported only for NFL/Savant's top 20 edge-rusher leaderboard. PFR pressures and sacks are retained unchanged; Pressure Rate and Sack Rate divide those PFR totals by NFL/Savant pass-rush snaps. No Savant pressure or sack totals are used.",
            "Quick Pressure Rate and Double-Team Rate remain blank because no reproducible public player-level feed is integrated. ESPN Win Rates are imported from its published Edge top-20 (pass rush) and top-10 (run stop), republished by NFL Lines. No estimates are substituted.",
            "PFR pressure, sack, hurry and knockdown totals are aggregated from weekly PFR defensive advanced stats when the relevant columns are present. TFLs and forced fumbles remain player-attributed play-by-play events."
        ]
    }
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"Edge refresh OK: {len(pbp):,} plays + {len(defense):,} PFR rows + {len(snaps):,} snap rows, {len(data)} edge players saved.")

if __name__ == "__main__":
    main()
