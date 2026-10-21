"""개별 에이전트 실행기: 웹 검색·페치 서버 툴을 쓰는 리서치 에이전트와 구조화 파서."""

from dataclasses import dataclass, field
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MAX_CONTINUATIONS = 2

# 100만 토큰당 달러 (입력, 출력). Haiku 5.5는 프롬프트 10만 토큰 초과분 단가가 다름
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
HAIKU_LONG_PROMPT_PRICES = (0.50, 2.50)
WEB_SEARCH_COST = 0.01  # 검색 1회당 달러
# 동적 필터링 웹 툴(_20260209)을 지원하는 모델. 나머지는 기본 웹 툴을 쓴다
DYNAMIC_WEB_TOOL_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CostTracker:
    budget_usd: float
    spent_usd: float = 0.0
    by_agent: dict[str, float] = field(default_factory=dict)

    def add(self, agent: str, model: str, usage) -> None:
        price_in, price_out = PRICES[model]
        if model == "claude-haiku-5-5" and usage.input_tokens > 100_000:
            price_in, price_out = HAIKU_LONG_PROMPT_PRICES
        cost = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
        if usage.server_tool_use:
            cost += usage.server_tool_use.web_search_requests * WEB_SEARCH_COST
        self.spent_usd += cost
        self.by_agent[agent] = self.by_agent.get(agent, 0.0) + cost

    def check(self) -> None:
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"비용 상한 ${self.budget_usd:.2f} 도달 (사용 ${self.spent_usd:.2f})")


def web_tools(model: str, allowed_domains: list[str] | None, max_uses: int) -> list[dict]:
    dynamic = model in DYNAMIC_WEB_TOOL_MODELS
    search = {"type": "web_search_20260209" if dynamic else "web_search_20250305", "name": "web_search", "max_uses": max_uses}
    # 페이지 하나가 컨텍스트를 다 차지하지 않도록 본문 길이를 제한
    fetch = {
        "type": "web_fetch_20260209" if dynamic else "web_fetch_20250910",
        "name": "web_fetch",
        "max_uses": max_uses,
        "max_content_tokens": 8000,
    }
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
    tracker: CostTracker,
    *,
    agent: str,
    model: str,
    system: str,
    task: str,
    allowed_domains: list[str] | None = None,
    max_uses: int = 5,
    effort: str = "low",
) -> str:
    """웹을 조사해 근거 URL이 붙은 메모를 텍스트로 돌려준다."""
    messages: list[dict] = [{"role": "user", "content": task}]
    tools = web_tools(model, allowed_domains, max_uses)
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if model in FALLBACK_MODELS else {}

    for _ in range(MAX_CONTINUATIONS + 1):
        tracker.check()
        response = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": effort},
            **extra,
        )
        tracker.add(agent, model, response.usage)
        if response.stop_reason == "refusal":
            return "(이 에이전트는 응답을 거부했습니다 — 결과 없음)"
        if response.stop_reason != "pause_turn":
            return _text_of(response.content)
        # 서버 측 검색 루프가 한도에 걸리면 같은 대화를 다시 보내 이어서 진행 (이전 내용 전체가 다시 과금됨)
        messages = [messages[0], {"role": "assistant", "content": response.content}]

    return _text_of(response.content) + "\n(조사 시간이 길어 중간에 멈췄습니다)"


async def parse_structured(
    client: anthropic.AsyncAnthropic,
    tracker: CostTracker,
    *,
    agent: str,
    model: str,
    instruction: str,
    material: str,
    schema: type[T],
    effort: str = "low",
) -> T:
    """자유 텍스트 메모를 지정한 스키마로 변환한다."""
    tracker.check()
    response = await client.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": f"{instruction}\n\n<material>\n{material}\n</material>"}],
        output_format=schema,
    )
    tracker.add(agent, model, response.usage)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"구조화 변환 실패: stop_reason={response.stop_reason}")
    return response.parsed_output
