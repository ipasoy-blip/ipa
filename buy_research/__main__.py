"""CLI: python -m buy_research "이케아 겨울 이불" --max-price 100000"""

import argparse
import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

from .agents import BudgetExceeded, CostTracker
from .pipeline import DEEP, ECONOMY, research
from .render import to_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="클리앙·뽐뿌·다나와 리뷰 기반 구매 비교 멀티에이전트")
    parser.add_argument("query", help='찾는 제품, 예: "이케아 겨울 이불"')
    parser.add_argument("--max-price", type=int, help="예산 상한(원, 미만)")
    parser.add_argument("--budget", type=float, default=1.0, help="API 비용 상한(달러, 기본 1.0). 넘으면 멈춤")
    parser.add_argument("--max-searches", type=int, default=5, help="에이전트당 웹 검색 최대 횟수 (기본 5)")
    parser.add_argument("--deep", action="store_true", help="더 비싼 모델(Sonnet·Opus)로 깊게 조사")
    parser.add_argument("--out", default="out", help="결과 저장 폴더")
    args = parser.parse_args()

    out_dir = Path(args.out)
    slug = re.sub(r"[^\w가-힣]+", "-", args.query).strip("-")
    base = out_dir / f"{date.today()}-{slug}"
    tracker = CostTracker(budget_usd=args.budget)

    try:
        report = asyncio.run(
            research(
                args.query,
                tracker,
                max_price=args.max_price,
                models=DEEP if args.deep else ECONOMY,
                max_searches=args.max_searches,
                notes_path=base.with_suffix(".notes.md"),
            )
        )
    except BudgetExceeded as e:
        sys.exit(f"{e}. 조사 메모는 {out_dir}/ 에 저장된 만큼 남아 있습니다. --budget 을 올려 다시 실행하세요.")
    except anthropic.AuthenticationError:
        sys.exit("API 키가 올바르지 않습니다. .env의 BUY_RESEARCH_API_KEY를 확인하세요.")
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e):
            sys.exit("API 크레딧이 부족합니다. console.anthropic.com → Settings → Billing에서 충전 후 다시 실행하세요.")
        raise
    finally:
        detail = ", ".join(f"{k} ${v:.2f}" for k, v in tracker.by_agent.items())
        print(f"\n[buy-research] 예상 API 비용: ${tracker.spent_usd:.2f} ({detail})", file=sys.stderr)

    markdown = to_markdown(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = base.with_suffix(".md")
    path.write_text(markdown, encoding="utf-8")
    base.with_suffix(".json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(markdown)
    print(f"\n저장됨: {path}")


if __name__ == "__main__":
    main()
