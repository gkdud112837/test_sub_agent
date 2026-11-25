# 상품 데이터 관리
실제 상품 자료가 없어 CSV에는 비실재 자리표시자 한 행만 수록했다. 빈 값은 미확인이다. 상품별 공식 자료 또는 승인 패키지 이미지 경로와 출처를 입력하고 record_status=VERIFIED, approval_status=APPROVED 상태를 담당자가 부여한 뒤 사용한다. 효능/인증/가격은 개별 근거를 확보한다. placeholder 행은 실제 상품 입력 후 삭제한다. CSV는 UTF-8 BOM 인코딩이다.
