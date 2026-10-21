"""CLI: python -m buy_research "이케아 겨울 이불" --max-price 100000"""

import argparse
import asyncio
import re
from datetime import date
from pathlib import Path

from .pipeline import research
from .render import to_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="클리앙·뽐뿌·다나와 리뷰 기반 구매 비교 멀티에이전트")
    parser.add_argument("query", help='찾는 제품, 예: "이케아 겨울 이불"')
    parser.add_argument("--max-price", type=int, help="예산 상한(원, 미만)")
    parser.add_argument("--out", default="out", help="결과 저장 폴더")
    args = parser.parse_args()

    report = asyncio.run(research(args.query, args.max_price))
    markdown = to_markdown(report)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w가-힣]+", "-", args.query).strip("-")
    path = out_dir / f"{date.today()}-{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    (out_dir / f"{date.today()}-{slug}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(markdown)
    print(f"\n저장됨: {path}")


if __name__ == "__main__":
    main()
