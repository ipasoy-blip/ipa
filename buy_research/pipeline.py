"""오케스트레이터: 후보 발굴 → 사이트별 에이전트 병렬 조사 → 비교표 종합."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import anthropic

from . import prompts
from .agents import BudgetExceeded, CostTracker, parse_structured, run_research_agent
from .config import make_client
from .models import CandidateList, ComparisonReport


@dataclass(frozen=True)
class Models:
    research: str  # 웹을 읽는 에이전트 (토큰을 가장 많이 씀)
    synthesis: str  # 메모 정리·비교표 작성


ECONOMY = Models(research="claude-haiku-5-5", synthesis="claude-sonnet-5-5")
DEEP = Models(research="claude-sonnet-5-5", synthesis="claude-opus-5-5")


def _log(msg: str) -> None:
    print(f"[buy-research] {msg}", flush=True)


async def research(
    query: str,
    tracker: CostTracker,
    *,
    max_price: int | None = None,
    models: Models = ECONOMY,
    max_searches: int = 5,
    notes_path: Path | None = None,
) -> ComparisonReport:
    client = make_client()

    # 1) 플래너: 조건에 맞는 후보 제품과 구매 링크
    _log(f"플래너 에이전트: 후보 제품 탐색 중 ({models.research})")
    planner_notes = await run_research_agent(
        client,
        tracker,
        agent="planner",
        model=models.research,
        system=prompts.PLANNER,
        task=prompts.planner_task(query, max_price),
        max_uses=max_searches,
    )
    candidates = await parse_structured(
        client,
        tracker,
        agent="planner",
        model=models.synthesis,
        instruction="다음 조사 메모에서 후보 제품 목록을 추출하세요.",
        material=planner_notes,
        schema=CandidateList,
    )
    if max_price:
        candidates.candidates = [c for c in candidates.candidates if c.price_krw == 0 or c.price_krw < max_price]
    if not candidates.candidates:
        raise RuntimeError("조건에 맞는 후보를 찾지 못했습니다.")
    candidates_text = "\n".join(
        f"- {c.name} ({c.variant}) {c.price_krw:,}원 | {c.key_specs} | {c.buy_url}" for c in candidates.candidates
    )
    _log(f"후보 {len(candidates.candidates)}개 (지금까지 ${tracker.spent_usd:.2f}):\n{candidates_text}")

    # 2) 사이트별 에이전트를 병렬로 실행 (각자 자기 도메인만 검색)
    _log("클리앙·뽐뿌·다나와 에이전트 병렬 실행 중")
    site_names = list(prompts.SITE_ROLES)
    results = await asyncio.gather(
        *(
            run_research_agent(
                client,
                tracker,
                agent=site,
                model=models.research,
                system=prompts.COMMON + "\n\n" + role,
                task=prompts.site_task(query, candidates_text),
                allowed_domains=domains,
                max_uses=max_searches,
            )
            for site, (domains, role) in prompts.SITE_ROLES.items()
        ),
        return_exceptions=True,
    )
    site_notes = []
    for site, result in zip(site_names, results):
        if isinstance(result, Exception):
            _log(f"{site} 에이전트 실패: {result}")
            result = f"(조사 실패: {result})"
        site_notes.append(f"## {site}\n{result}")

    material = f"사용자 요구: {query} / 예산: {max_price or '제한 없음'}\n\n# 후보\n{candidates_text}\n\n" + "\n\n".join(
        site_notes
    )
    # 비용을 들여 모은 조사 메모는 종합 단계가 실패해도 남도록 먼저 저장
    if notes_path:
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(material, encoding="utf-8")
        _log(f"조사 메모 저장: {notes_path}")

    # 결제·인증 오류와 비용 상한 초과는 종합 단계로 넘어가지 않음
    fatal = next(
        (
            r
            for r in results
            if isinstance(r, (anthropic.AuthenticationError, anthropic.PermissionDeniedError, BudgetExceeded))
            or (isinstance(r, anthropic.BadRequestError) and "credit balance" in str(r))
        ),
        None,
    )
    if fatal:
        raise fatal

    # 3) 종합: 구조화된 비교표
    _log(f"종합 에이전트: 비교표 작성 중 ({models.synthesis})")
    report = await parse_structured(
        client,
        tracker,
        agent="synthesizer",
        model=models.synthesis,
        instruction=prompts.SYNTHESIZER,
        material=material,
        schema=ComparisonReport,
        effort="medium",
    )
    report.rows.sort(key=lambda r: r.fit_score, reverse=True)
    return report
