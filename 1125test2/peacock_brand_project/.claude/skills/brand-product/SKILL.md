---
name: brand-product
description: 화장품 상품 데이터 확인 및 광고 카피 제작에 사용한다.
---

# brand-product

1. `data/products_vision.csv`를 읽는다. record_status=VERIFIED이며 evidence_ref와 approval_status=APPROVED가 있는 행만 공개 제작에 사용한다.
2. 빈 셀은 미확인이다. 상품명, 용량, 가격, 성분, 효능, 인증, 패키지를 추정하지 않는다.
3. 상품 이미지의 텍스트/색/형태는 근거와 대조한다. 식별 불가 시 보류한다.
4. 출력: 상품 ID, 확인 정보, 근거, 미확인 항목, 승인 필요 카피. 유효 상품이 없으면 상품 없는 티저를 제안한다.

공통: 경로는 프로젝트 루트 기준. 확정 사실과 제안을 구분하며 누락된 자료를 임의 생성하지 않는다.
