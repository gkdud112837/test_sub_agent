# board — VOC 분류 관제

| 파일 | 역할 |
|---|---|
| `control.py` | 관제 액션 실행: 게이트 1~7 점검 · 채점 채널(기계 점검 + 채점관 점수) · 골든셋 비교 · 훅 로그 집계 → `status.json` / `status.js` 생성, 실행 결과를 `events.jsonl`에 `ControlCheck`로 기록 |
| `index.html` | 관제 모니터링 화면. `status.js`를 3초마다 다시 읽어 갱신 (파일로 바로 열어도 동작) |
| `status.json` · `status.js` | `control.py`가 만드는 현재 상태 (직접 수정하지 않음) |

## 관제 서버 (실행 · 중지 버튼)
```
python -I -X utf8 board/server.py          # http://127.0.0.1:8765 자동으로 열림 (Ctrl+C 종료)
```
| 버튼 | 동작 |
|---|---|
| ▶ 실행 | part_1~3.csv · scorecard.md 백업(`board/runs/<시각>/backup`) → `review-tagger` 3개(묶음 1·2·3) 병렬 실행 → 각 part 100행 확인 → `review-grader` 채점 |
| ■ 중지 | 실행 중인 claude 프로세스 트리를 모두 종료(`taskkill /T /F`) → 백업으로 복원 |

- 각 에이전트는 `claude -p --agent <이름> --permission-mode acceptEdits` 로 별도 프로세스에서 돈다. 에이전트별 출력은 `board/runs/<시각>/*.log`.
- 실행 중에는 단계 1·2·3(분류), 5(채점)가 형광색으로 깜빡인다.
- 버튼은 서버로 연 화면(`http://127.0.0.1:8765`)에서만 동작한다. 파일로 직접 연 화면은 보기 전용.
- 사전 조건: 이 폴더에서 `claude` 를 한 번 대화형으로 실행해 "폴더 신뢰"를 승인해야 settings.json 허용 목록이 적용된다.

## 점검만 실행 (서버 없이)
```
python -I -X utf8 board/control.py --watch 5 --open   # 5초마다 점검 + 화면 열기 (Ctrl+C 종료)
python -I -X utf8 board/control.py                    # 1회 점검
python -I -X utf8 board/control.py --no-log           # events.jsonl 기록 없이 점검
```

## 읽는 데이터
| 데이터 | 경로 | 없을 때 |
|---|---|---|
| 허용 태그 | `painpoint-*/painpoint/painpoint_def.md` "허용 태그:" 줄 | 기본 7개 사용 |
| 원문 · ID 목록 | `archive-*/archive/batch*/r_*.md` · `metadata.csv` | 범위 점검 불가 |
| 분류 결과 | `ax/demo/parts/part_N.csv` | 게이트 1 대기 · 알림 |
| 채점관 점수 · 승인 | `ax/demo/scorecard.md` "관제 화면" 표 | 게이트 5 · 7 대기 |
| 골든셋 | `ax/demo/golden.csv` (`voc_id,tag` 10행) | 게이트 6 대기 |
| 훅 로그 | `.claude/logs/events.jsonl` | 이벤트 패널 비움 |

## 진행 중 표시 (형광색 깜빡임)
게이트 단계에 작업이 일어나면 그 행이 형광 초록으로 깜빡이고, 상단에 "● 진행 중: n.단계" 배지가 뜬다.

| 방법 | 동작 |
|---|---|
| 자동 감지 | 최근 15초 안의 훅 이벤트가 아래 대상을 건드리면 진행 중 |
| 직접 표시 | `python -I -X utf8 board/control.py --mark 5 start --note "채점 시작"` → `--mark 5 end`로 해제 (10분 지나면 자동 해제) |

| 단계 | 자동 감지 대상 |
|---|---|
| 1 ID 범위 | `batch*/r_*.md` · `metadata.csv` 읽기 |
| 2 근거 | `ax/demo/parts/part_N.csv` 쓰기 · 수정 |
| 3 태그 | `painpoint_def.md` 읽기 |
| 4 검토 비율 | `check_gates.py` 실행 |
| 5 채점 합격선 | `scorecard.md` · `review-grader` |
| 6 골든셋 | `golden.csv` |
| 7 승인 | "승인"이 들어간 프롬프트 · 명령 |

- 관제 자신(`board/control.py`) 실행은 감지에서 뺀다.
- 화면은 2초마다 갱신되므로 `--watch 2` 로 켜 두면 가장 빠르게 반응한다.
- 채점 이후 part 파일이 바뀌면 게이트 5를 다시 채점하라는 경고가 뜬다.
- `ControlCheck`는 상태가 바뀔 때만 기록한다 (watch 중 로그 폭주 방지).
