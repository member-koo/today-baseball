"""Fetch verified KBO schedule data; preserve existing data on failure."""
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from team_rankings import parse_standings
from lineup import load_lineups
from data_quality import assess
from preview_rules import validate_games
from prediction_model import attach_predictions
from insight_engine import build_insights
from head_to_head import collect

URL = "https://eng.koreabaseball.com/Schedule/DailySchedule.aspx"
STANDINGS_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRankDaily.aspx"
ROOT = Path(__file__).parent

TEAMS = {
    "KIA": "KIA", "한화": "한화", "HANWHA": "한화",
    "LG": "LG", "두산": "두산", "DOOSAN": "두산",
    "삼성": "삼성", "SAMSUNG": "삼성",
    "롯데": "롯데", "LOTTE": "롯데",
    "SSG": "SSG", "NC": "NC", "KT": "KT",
    "키움": "키움", "KIWOOM": "키움",
}
VENUES = {
    "JAMSIL": "잠실", "GOCHEOKSKY": "고척",
    "MUNHAK": "문학", "SUWON": "수원",
    "DAEJEON": "대전", "GWANGJU": "광주",
    "DAEGU": "대구", "SAJIK": "사직",
    "CHANGWON": "창원", "ULSAN": "울산",
    "POHANG": "포항", "CHEONGJU": "청주",
}
KOREAN_VENUES = set(VENUES.values())
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?:\([^)]*\))?")
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")
MONTH_RE = re.compile(r"\b(20\d{2})\s*\.\s*(\d{1,2})\b")
TEAM_RE = re.compile(
    r"(?<![A-Za-z가-힣])("
    + "|".join(re.escape(x) for x in sorted(TEAMS, key=len, reverse=True))
    + r")(?![A-Za-z가-힣])",
    re.IGNORECASE,
)


def extract(html, target):
    soup = BeautifulSoup(html, "html.parser")
    games = []

    for table in soup.select("table"):
        active_date = None

        for tr in table.select("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            values = [c.get_text(" ", strip=True) for c in cells]
            if not values:
                continue

            first = values[0]
            date_match = DATE_RE.search(first)
            if date_match:
                active_date = (
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                )

            if active_date != (target.month, target.day):
                continue

            joined = " ".join(values)
            time_match = TIME_RE.search(joined)
            if not time_match:
                continue

            names = [
                TEAMS[m.group(1).upper()]
                if m.group(1).upper() in TEAMS
                else TEAMS[m.group(1)]
                for m in TEAM_RE.finditer(joined)
            ]

            if len(names) != 2 or names[0] == names[1]:
                continue

            venue = "미확인"
            for value in values:
                upper = value.upper().strip()
                if upper in VENUES:
                    venue = VENUES[upper]
                    break
                if value.strip() in KOREAN_VENUES:
                    venue = value.strip()
                    break

            game = {
                "time": time_match.group(),
                "away": names[0],
                "home": names[1],
                "venue": venue,
                "starting_pitchers": None,
                "lineups": None,
                "prediction": None,
            }

            if game not in games:
                games.append(game)

    return games


def selected_standings_year(html):
    """Return the explicitly selected season, never infer from a year list."""
    soup = BeautifulSoup(html, "html.parser")
    years = set()

    for option in soup.select("select option[selected]"):
        value = option.get("value", "").strip()
        label = option.get_text(" ", strip=True)
        for candidate in (value, label):
            if re.fullmatch(r"20\d{2}", candidate):
                years.add(int(candidate))

    if len(years) == 1:
        return years.pop()

    return None


def get_standings(year):
    response = requests.get(
        STANDINGS_URL,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # The Korean official page states the standings reference date.
    matches = re.findall(
        r"(20\d{2})\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일\s*기준",
        text,
    )

    verified_years = {int(value) for value in matches}
    print(f"DIAG standings_verified_years={sorted(verified_years)}")

    if verified_years != {year}:
        print("WARN standings year unverified; not publishing standings")
        return []

    standings = parse_standings(response.text)
    print(f"DIAG standings_found={len(standings)}")
    return standings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, default Korea today")
    parser.add_argument("--fixture", help="Local HTML for offline tests")
    parser.add_argument("--skip-head-to-head", action="store_true")
    args = parser.parse_args()

    today = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    )
    path = ROOT / "data" / "today.json"

    # Season data updates independently, even if today's schedule fails.
    if not args.fixture and not args.skip_head_to_head:
        try:
            collect(today, ROOT / "data")
        except Exception as err:
            print(f"WARN head-to-head unavailable; previous data preserved: {err}")

    try:
        if args.fixture:
            html = Path(args.fixture).read_text(encoding="utf-8")
            source = "local fixture"
        else:
            response = requests.get(
                URL,
                timeout=25,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            html = response.text
            source = response.url

            page_text = BeautifulSoup(
                html, "html.parser"
            ).get_text(" ", strip=True)
            months = MONTH_RE.findall(page_text)

            if months and not any(
                int(year) == today.year and int(month) == today.month
                for year, month in months
            ):
                raise ValueError(
                    "공식 일정표의 연도 또는 월이 다릅니다."
                )

        games = extract(html, today)

        print(f"DIAG requested_date={today.isoformat()}")
        print(f"DIAG source={source}")
        print(f"DIAG games_found={len(games)}")

        if not games:
            raise ValueError(
                "확인된 경기 행이 없습니다. 휴식일인지 수집 오류인지 "
                "확인할 수 없어 기존 데이터를 보존합니다."
            )

        validate_games(games)

        games = load_lineups(
            ROOT / "data" / "lineups" / f"{today.isoformat()}.json",
            today.isoformat(),
            games,
        )

        try:
            attach_predictions(
                games, today, ROOT / "data" / "team_stats.json"
            )
        except (
            ValueError, KeyError, TypeError, json.JSONDecodeError
        ) as err:
            print(f"WARN prediction unavailable: {err}")

        for game in games:
            game["insights"] = build_insights(game)

        standings = []
        standings_status = "순위 데이터 확인 불가"

        if not args.fixture:
            try:
                standings = get_standings(today.year)
                if standings:
                    standings_status = (
                        f"{today.year}년 KBO 공식 순위 확인"
                    )
            except requests.RequestException as err:
                print(f"WARN standings unavailable: {err}")

        result = {
            "standings": standings,
            "standings_status": standings_status,
            "status": (
                "KBO 공식 경기 일정 확인 · "
                "라인업은 출처 확인 시 표시"
            ),
            "title": f"{today.isoformat()} KBO 경기 일정",
            "game_date": today.isoformat(),
            "updated_at": dt.datetime.now(
                ZoneInfo("Asia/Seoul")
            ).isoformat(timespec="minutes"),
            "source": source,
            "games": games,
            "note": (
                "일정은 KBO 공식 자료를 기준으로 합니다. "
                "예측은 검증된 기록이 있을 때만 표시합니다. "
                "포스트시즌 조건부 경기는 개최 여부를 "
                "별도로 확인해야 합니다."
            ),
        }

        check = assess(result)
        if not check["publishable"]:
            raise ValueError(check["reason"])

        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"OK {today}: {len(games)} games")

    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
