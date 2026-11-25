# 럭셔리 피콕 브랜드 제작 패키지
첨부 캐릭터셋과 원본 PNG를 기반으로 구성한 Claude Code 프로젝트 초안이다.

## 시작하기
ZIP을 풀고 프로젝트 루트를 Claude Code에서 열어 `CLAUDE.md`와 각 규격서를 적용한다. 예시 요청: “brand-storyboard와 brand-character 규칙을 적용하여 S01~S05 키프레임 프롬프트를 작성하고 brand-qa 기준으로 검수해 주세요.” 이미지/영상 생성 도구 연결은 별도이며 이 패키지는 제작 지침과 기획 파일이다.

## 구성
- brand/character/fixed.md: 첨부 원문 전체 및 원본 참조 경로/해시.
- brand/character/reference/: 첨부 PNG 원본 복사본.
- brand/visual/visual_rules.md: 영상 색상, 타이포, 모션 제안.
- .claude/skills/: 캐릭터, 비주얼, 상품, 스토리보드, QA 스킬 5종.
- data/products_vision.csv: 상품 등록용 스키마(실제 상품 없음).
- storyboard_v1.md / teaser_plan.md: 신규 캐릭터 중심 15초 티저 초안.

확정 전 확인: 브랜드명, 상품, 기존 스토리보드, 로고, 공개일, 폰트/음원/원본 이용권. 원본 규격의 [추정] 항목은 승인되지 않았다. Claude Code 실행 및 실제 렌더 검수는 수행하지 않았다.
