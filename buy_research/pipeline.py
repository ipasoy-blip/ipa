"""오케스트레이터: 후보 발굴 → 사이트별 에이전트 병렬 조사 → 비교표 종합."""

import asyncio

from . import prompts
from .agents import parse_structured, run_research_agent
from .config import make_client
from .models import CandidateList, ComparisonReport


def _log(msg: str) -> None:
    print(f"[buy-research] {msg}", flush=True)


async def research(query: str, max_price: int | None = None) -> ComparisonReport:
    client = make_client()

    # 1) 플래너: 조건에 맞는 후보 제품과 구매 링크
    _log("플래너 에이전트: 후보 제품 탐색 중")
    planner_notes = await run_research_agent(
        client, system=prompts.PLANNER, task=prompts.planner_task(query, max_price)
    )
    candidates = await parse_structured(
        client,
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
    _log(f"후보 {len(candidates.candidates)}개:\n{candidates_text}")

    # 2) 사이트별 에이전트를 병렬로 실행 (각자 자기 도메인만 검색)
    _log("클리앙·뽐뿌·다나와 에이전트 병렬 실행 중")
    site_names = list(prompts.SITE_ROLES)
    results = await asyncio.gather(
        *(
            run_research_agent(
                client,
                system=prompts.COMMON + "\n\n" + role,
                task=prompts.site_task(query, candidates_text),
                allowed_domains=domains,
            )
            for domains, role in prompts.SITE_ROLES.values()
        ),
        return_exceptions=True,
    )
    site_notes = []
    for site, result in zip(site_names, results):
        if isinstance(result, Exception):
            _log(f"{site} 에이전트 실패: {result}")
            result = f"(조사 실패: {result})"
        site_notes.append(f"## {site}\n{result}")

    # 3) 종합: 구조화된 비교표
    _log("종합 에이전트: 비교표 작성 중")
    material = f"사용자 요구: {query} / 예산: {max_price or '제한 없음'}\n\n# 후보\n{candidates_text}\n\n" + "\n\n".join(
        site_notes
    )
    report = await parse_structured(
        client, instruction=prompts.SYNTHESIZER, material=material, schema=ComparisonReport, effort="high"
    )
    report.rows.sort(key=lambda r: r.fit_score, reverse=True)
    return report
