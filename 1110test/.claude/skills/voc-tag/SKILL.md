---
name: voc-tag
description: 서문시장 야시장 VOC 300건 전체를 painpoint_def.md 규칙으로 분류해 output/voc_tags.csv와 건수 요약을 만든다. "VOC 분류", "태깅", "voc-tag"를 요청받을 때 사용한다.
---

# VOC 일괄 분류

1. `archive-*/archive/` 아래 batch 폴더 목록을 확인한다 (batch1 · batch2 · batch3).
2. batch마다 `voc-tagger` 에이전트를 **한 메시지에서 병렬로** 실행한다. 프롬프트에 batch 폴더의 절대 경로와 painpoint_def.md 경로를 준다.
3. 돌아온 CSV를 voc_id 순으로 합쳐 `output/voc_tags.csv`(UTF-8 BOM, 헤더 한 번)로 저장한다.
4. 검증:
   - 행 수 = `metadata.csv`의 VOC 수(300)인지 확인한다.
   - tag가 허용 태그 7개(P1 · P2 · P3 · H1 · H2 · 해당없음 · 검토) 밖이면 그 행을 `검토`로 바꾸고 note에 "태그 오류"를 적는다.
   - quote가 15자를 넘거나 원문에 그대로 없으면 해당 행을 다시 판정한다.
5. CSV 열은 `voc_id,source,date,file,tag,quote,근거유무,note,원문` (CLAUDE.md 형식). 모든 행에 quote 필수.
6. `python -I -X utf8 tools/check_gates.py`로 관제 화면을 출력하고, `grader` 에이전트로 채점 세 묶음을 독립 채점한다.
7. CLAUDE.md 품질 게이트 1~6을 점검한다. FAIL이 있으면 고친 뒤 처음부터 다시 점검한다.
8. 관제 화면(검토 숫자 · 채점 채널 · 골든셋 · 승인 상태)을 보고하고 **사용자 승인을 기다린다.** 스스로 승인하지 않는다.
