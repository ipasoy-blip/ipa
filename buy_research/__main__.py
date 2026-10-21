"""CLI: python -m buy_research "이케아 겨울 이불" --max-price 100000"""

import argparse
import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

from .pipeline import research
from .render import to_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="클리앙·뽐뿌·다나와 리뷰 기반 구매 비교 멀티에이전트")
    parser.add_argument("query", help='찾는 제품, 예: "이케아 겨울 이불"')
    parser.add_argument("--max-price", type=int, help="예산 상한(원, 미만)")
    parser.add_argument("--out", default="out", help="결과 저장 폴더")
    args = parser.parse_args()

    out_dir = Path(args.out)
    slug = re.sub(r"[^\w가-힣]+", "-", args.query).strip("-")
    base = out_dir / f"{date.today()}-{slug}"

    try:
        report = asyncio.run(research(args.query, args.max_price, notes_path=base.with_suffix(".notes.md")))
    except anthropic.AuthenticationError:
        sys.exit("API 키가 올바르지 않습니다. .env의 BUY_RESEARCH_API_KEY를 확인하세요.")
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e):
            sys.exit("API 크레딧이 부족합니다. console.anthropic.com → Settings → Billing에서 충전 후 다시 실행하세요.")
        raise

    markdown = to_markdown(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = base.with_suffix(".md")
    path.write_text(markdown, encoding="utf-8")
    base.with_suffix(".json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(markdown)
    print(f"\n저장됨: {path}")


if __name__ == "__main__":
    main()
