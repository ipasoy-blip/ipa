"""개별 에이전트 실행기: 웹 검색·페치 서버 툴을 쓰는 리서치 에이전트와 구조화 파서."""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
MAX_CONTINUATIONS = 5

T = TypeVar("T", bound=BaseModel)


def web_tools(allowed_domains: list[str] | None, max_uses: int) -> list[dict]:
    search = {"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}
    fetch = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_uses}
    if allowed_domains:
        search["allowed_domains"] = allowed_domains
        fetch["allowed_domains"] = allowed_domains
    # 한국 사이트 검색 품질을 위해 위치를 서울로 지정
    search["user_location"] = {"type": "approximate", "country": "KR", "city": "Seoul", "timezone": "Asia/Seoul"}
    return [search, fetch]


def _text_of(content) -> str:
    return "\n".join(b.text for b in content if b.type == "text").strip()


async def run_research_agent(
    client: anthropic.AsyncAnthropic,
    *,
    system: str,
    task: str,
    allowed_domains: list[str] | None = None,
    max_uses: int = 12,
    effort: str = "medium",
) -> str:
    """웹을 조사해 근거 URL이 붙은 메모를 텍스트로 돌려준다."""
    messages: list[dict] = [{"role": "user", "content": task}]
    tools = web_tools(allowed_domains, max_uses)

    for _ in range(MAX_CONTINUATIONS):
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return "(이 에이전트는 응답을 거부했습니다 — 결과 없음)"
        if response.stop_reason != "pause_turn":
            return _text_of(response.content)
        # 서버 측 검색 루프가 한도에 걸리면 같은 대화를 다시 보내 이어서 진행
        messages = [messages[0], {"role": "assistant", "content": response.content}]

    return _text_of(response.content) + "\n(조사 시간이 길어 중간에 멈췄습니다)"


async def parse_structured(
    client: anthropic.AsyncAnthropic,
    *,
    instruction: str,
    material: str,
    schema: type[T],
    effort: str = "low",
) -> T:
    """자유 텍스트 메모를 지정한 스키마로 변환한다."""
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": f"{instruction}\n\n<material>\n{material}\n</material>"}],
        output_format=schema,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"구조화 변환 실패: stop_reason={response.stop_reason}")
    return response.parsed_output
