# 산업리포트 에이전트 (1123test)

SK증권 「IT 하드웨어 2027 연간전망」과 같은 구성의 리포트를 Gemini 에이전트 팀이 작성한다.
구조는 [agent_architecture.html](agent_architecture.html), 결정 근거는 [decision_log.md](decision_log.md).

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env        # 처음 한 번. GEMINI_API_KEY를 채운다
python serve.py             # 로컬 웹 화면 → http://127.0.0.1:8770
python run.py --dry-run     # 터미널에서 가짜 응답으로 흐름만 확인
python run.py               # 터미널에서 Gemini로 실제 실행
python -m pytest -q         # 테스트 (API 키 불필요)
```

키가 없으면 웹 화면에서 dry-run만 켜진다. 로컬 전용이라 `WEB_HOST`는 127.0.0.1/localhost만 허용한다.

## 흐름

| 페이즈 | 누가 | 동시 실행 |
|---|---|---|
| P0 범위 | 메인 세션(코드) — `data/brief.md`를 배치 | |
| P1 분석 | market-reviewer · demand-analyst · lta-analyst · inflation-analyst · valuation-analyst | 5개 |
| P2 작성 | report-writer · chart-maker | 2개 |
| P3 검토 | fact-checker · logic-reviewer (초안을 고치지 않고 지적만) | 2개 |
| P4 발간 | 메인 세션(코드) — 차트 끼워 넣기, [확인필요] 목록 | |

되돌아가는 경로는 다섯 가지다. 같은 경로로는 최대 `MAX_REWORK`번까지 다시 돌고, 그래도 안 풀리면 [확인필요]로 남긴다.
- R1 검토 → writer
- R2 검토 → chart
- R3 검토 → 분석
- R4 writer → 분석
- R5 분석 → 메인 세션

## 파일 위치

| 무엇 | 어디 |
|---|---|
| 설정값 (키·모델·경로·포트) | `.env` |
| 작업 지시서 (목적·범위) | `data/brief.md` |
| 에이전트 구성·섹션·할 일 | `config/agents.json` |
| 시스템 지시문 · 메시지 틀 | `config/prompts/*.md`, `config/prompts/messages.json` |
| 응답 스키마 | `config/schemas/*.json` |
| 출력 문구 · 차트 스타일 | `config/output_text.json`, `config/chart_style.json` |
| dry-run 가짜 응답 | `fixtures/dry_run.json` |
| 실행 결과 (공유 작업 공간) | `workspace/run-*/` — `00_brief` · `10_analysis/<에이전트>` · `20_draft` · `30_review` · `40_final` · `run_log.json` |
| 코드 | `report_agents/` (오케스트레이터 · LLM 래퍼 · 서버), `web/` (화면) |
