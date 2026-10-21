"""비교 결과를 마크다운 표로 출력한다."""

from .models import ComparisonReport

SITE_LABELS = {"clien": "클리앙", "ppomppu": "뽐뿌", "danawa": "다나와"}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(report: ComparisonReport) -> str:
    lines = [f"# 구매 비교: {report.query}", "", "## 비교표", ""]
    lines.append("| 순위 | 제품 | 가격 | 핵심 스펙 | 장점 | 낮은 별점·부정 댓글 단점 | 적합도 | 구매 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(report.rows, 1):
        price = f"{r.price_krw:,}원" if r.price_krw else "확인 필요"
        lines.append(
            f"| {i} | **{_cell(r.name)}** {_cell(r.variant)} | {price} | {_cell(r.key_specs)} | "
            f"{_cell('; '.join(r.pros))} | {_cell('; '.join(r.cons_from_low_ratings))} | {r.fit_score}/10 | "
            f"[구매]({r.buy_url}) |"
        )

    lines += ["", "## 사이트별 여론", ""]
    for r in report.rows:
        lines.append(f"### {r.name} {r.variant}")
        lines.append(f"- 추천 대상: {r.who_should_buy}")
        for v in r.site_verdicts:
            links = " ".join(f"[{n}]({u})" for n, u in enumerate(v.source_urls, 1))
            lines.append(f"- **{SITE_LABELS.get(v.site, v.site)}**: {v.summary} {links}".rstrip())
        lines.append("")

    lines += ["## 추천", "", report.recommendation, "", "## 주의사항", ""]
    lines += [f"- {c}" for c in report.caveats]
    return "\n".join(lines) + "\n"
