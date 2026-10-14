"""Fetch KBO games from the official English daily schedule."""
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

URL = "https://eng.koreabaseball.com/Schedule/DailySchedule.aspx"
ROOT = Path(__file__).parent

TEAM_NAMES = {
    "KIA": "KIA",
    "HANWHA": "한화",
    "LG": "LG",
    "DOOSAN": "두산",
    "SAMSUNG": "삼성",
    "LOTTE": "롯데",
    "SSG": "SSG",
    "NC": "NC",
    "KT": "KT",
    "KIWOOM": "키움",
}
VENUES = {
    "JAMSIL": "잠실",
    "GOCHEOKSKY": "고척",
    "MUNHAK": "문학",
    "SUWON": "수원",
    "DAEJEON": "대전",
    "GWANGJU": "광주",
    "DAEGU": "대구",
    "SAJIK": "사직",
    "CHANGWON": "창원",
    "ULSAN": "울산",
    "POHANG": "포항",
    "CHEONGJU": "청주",
}
DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\s*\([A-Za-z]+\)")
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")
MONTH_RE = re.compile(r"\b(20\d{2})\s*\.\s*(\d{1,2})\b")


def extract(html, target):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    month_matches = MONTH_RE.findall(page_text)

    # Do not silently publish another month's schedule.
    if not any(
        int(year) == target.year and int(month) == target.month
        for year, month in month_matches
    ):
        raise ValueError(
            f"요청한 {target.year}년 {target.month}월 일정표를 확인하지 못했습니다."
        )

    games = []
    active_date = None

    for table in soup.select("table"):
        for tr in table.select("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            values = [cell.get_text(" ", strip=True) for cell in cells]
            joined = " ".join(values)
            date_match = DATE_RE.search(joined)

            if date_match:
                active_date = (
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                )

            if active_date != (target.month, target.day):
                continue

            time_match = TIME_RE.search(joined)
            if not time_match:
                continue

            # Team names must appear as distinct tokens.
            tokens = re.findall(r"[A-Za-z]+", joined.upper())
            teams = [token for token in tokens if token in TEAM_NAMES]

            if len(teams) != 2 or teams[0] == teams[1]:
                continue

            venue = next(
                (VENUES[token] for token in tokens if token in VENUES),
                "미확인",
            )

            game = {
                "time": time_match.group(),
                "away": TEAM_NAMES[teams[0]],
                "home": TEAM_NAMES[teams[1]],
                "venue": venue,
                "starting_pitchers": None,
                "lineups": None,
                "prediction": None,
            }

            if game not in games:
                games.append(game)

    return games


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, default Korea today")
    parser.add_argument("--fixture", help="Local HTML for offline tests")
    args = parser.parse_args()

    today = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    )

    path = ROOT / "data" / "today.json"

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

        games = extract(html, today)

        print(f"DIAG date={today.isoformat()}")
        print(f"DIAG source={source}")
        print(f"DIAG games_found={len(games)}")

        if not games:
            raise ValueError(
                "해당 날짜의 경기 행을 확인하지 못했습니다. "
                "경기 없음과 수집 오류를 아직 구분할 수 없어 "
                "기존 데이터를 보존합니다."
            )

        validate_games(games)

        games = load_lineups(
            ROOT / "data" / "lineups" / f"{today.isoformat()}.json",
            today.isoformat(),
            games,
        )

        try:
            attach_predictions(
                games,
                today,
                ROOT / "data" / "team_stats.json",
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            print(f"WARN prediction unavailable: {err}")

        for game in games:
            game["insights"] = build_insights(game)

        standings = []
        standings_status = "순위 데이터 확인 불가"

        try:
            if not args.fixture:
                response = requests.get(
                    "https://www.koreabaseball.com/",
                    timeout=25,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()
                response.encoding = response.apparent_encoding
                standings = parse_standings(response.text)

                if standings:
                    standings_status = "KBO 공식 순위 확인"

        except requests.RequestException as err:
            print(f"WARN standings unavailable: {err}")

        result = {
            "standings": standings,
            "standings_status": standings_status,
            "status": "KBO 공식 경기 일정 확인 · 라인업은 출처 확인 시 표시",
            "title": f"{today.isoformat()} KBO 경기 일정",
            "game_date": today.isoformat(),
            "updated_at": dt.datetime.now(
                ZoneInfo("Asia/Seoul")
            ).isoformat(timespec="minutes"),
            "source": source,
            "games": games,
            "note": (
                "경기 일정은 KBO 공식 사이트를 기준으로 합니다. "
                "예측은 검증된 팀 기록이 있을 때만 표시합니다. "
                "포스트시즌 조건부 경기는 실제 개최 여부를 별도로 확인해야 합니다."
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
        # Never overwrite the last valid data after a failed fetch.
        print(f"ERROR: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
