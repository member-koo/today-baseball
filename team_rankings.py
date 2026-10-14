"""Parse verified KBO team standings without guessing missing values."""
from bs4 import BeautifulSoup

TEAM_NAMES = {
    "KIA": "KIA",
    "HANWHA": "한화",
    "한화": "한화",
    "LG": "LG",
    "DOOSAN": "두산",
    "두산": "두산",
    "SAMSUNG": "삼성",
    "삼성": "삼성",
    "LOTTE": "롯데",
    "롯데": "롯데",
    "SSG": "SSG",
    "NC": "NC",
    "KT": "KT",
    "KIWOOM": "키움",
    "키움": "키움",
}

EXPECTED_TEAMS = set(TEAM_NAMES.values())


def parse_standings(html):
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.select("table"):
        parsed = []

        for row in table.select("tr"):
            cells = row.find_all(
                ["th", "td"], recursive=False
            )
            values = [
                cell.get_text(" ", strip=True)
                for cell in cells
            ]

            if len(values) < 7:
                continue

            if not values[0].isdigit():
                continue

            raw_team = values[1].strip().upper()
            team = TEAM_NAMES.get(raw_team)

            if team is None:
                continue

            try:
                rank = int(values[0])
                played = int(values[2])
                wins = int(values[3])
                losses = int(values[4])
                draws = int(values[5])
                pct = float(values[6])
            except (ValueError, TypeError):
                continue

            if not (1 <= rank <= 10):
                continue

            if played != wins + losses + draws:
                continue

            if not (0 <= pct <= 1):
                continue

            if wins + losses > 0:
                expected_pct = wins / (wins + losses)
                if abs(pct - expected_pct) > 0.002:
                    continue

            parsed.append({
                "rank": rank,
                "team": team,
                "games": played,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_pct": pct,
            })

        if len(parsed) != 10:
            continue

        if {item["team"] for item in parsed} != EXPECTED_TEAMS:
            continue

        if {item["rank"] for item in parsed} != set(range(1, 11)):
            continue

        return sorted(
            parsed,
            key=lambda item: item["rank"],
        )

    return []
