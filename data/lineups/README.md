# 라인업 데이터

이 디렉터리는 검증된 출처에서 수집한 날짜별 라인업 JSON을 위한 자리입니다.
`YYYY-MM-DD.json` 파일에 `date`, `games`를 기록합니다. 경기 키는 `원정-홈`입니다.
`status`는 `official`(공식 확인) 또는 `projected`(예상)이며, 반드시 `source_url`과 `checked_at`이 있어야 합니다.
각 팀 `away`/`home`은 `{ "name": "...", "position": "..." }` 9개 항목이 필요합니다.
아직 실제 데이터 공급자가 연동되지 않았으므로 임의의 라인업 파일은 생성하지 않습니다.
