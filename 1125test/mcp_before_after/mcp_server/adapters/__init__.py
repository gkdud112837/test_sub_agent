"""외부 연결 어댑터. 각 모듈의 fetch()는 정리된 dict를 돌려주고, 실패하면 ValueError/RuntimeError를 던진다."""

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
