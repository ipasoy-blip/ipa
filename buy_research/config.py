"""API 키 설정: 환경 변수 또는 프로젝트 루트의 .env 파일에서 읽는다."""

import os
from pathlib import Path

import anthropic

KEY_VAR = "BUY_RESEARCH_API_KEY"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def make_client() -> anthropic.AsyncAnthropic:
    _load_env_file()
    api_key = os.environ.get(KEY_VAR)
    if api_key:
        # 전용 키가 있으면 다른 환경 설정(ANTHROPIC_BASE_URL 등)과 섞이지 않게 공식 엔드포인트로 고정
        return anthropic.AsyncAnthropic(api_key=api_key, base_url="https://api.anthropic.com")
    return anthropic.AsyncAnthropic()
