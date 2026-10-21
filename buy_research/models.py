"""에이전트 사이에 주고받는 구조화 데이터."""

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    name: str = Field(description="제품명 (브랜드 + 모델명 + 옵션)")
    variant: str = Field(description="사이즈·등급 등 옵션, 없으면 빈 문자열")
    price_krw: int = Field(description="현재 판매가(원). 모르면 0")
    buy_url: str = Field(description="공식몰 또는 최저가 구매 링크")
    key_specs: str = Field(description="핵심 스펙 한 줄 (소재, 충전재, 보온 등급 등)")


class CandidateList(BaseModel):
    candidates: list[Candidate]


class SiteVerdict(BaseModel):
    site: str = Field(description="clien / ppomppu / danawa")
    summary: str = Field(description="해당 사이트 여론 한두 문장, 근거 없으면 '언급 없음'")
    source_urls: list[str]


class ComparisonRow(BaseModel):
    name: str
    variant: str
    price_krw: int
    buy_url: str
    key_specs: str
    pros: list[str]
    cons_from_low_ratings: list[str] = Field(description="별점 낮은 리뷰·부정 댓글에서 나온 단점")
    site_verdicts: list[SiteVerdict]
    fit_score: int = Field(description="사용자 조건 적합도 1~10")
    who_should_buy: str = Field(description="이런 사람에게 맞음 한 줄")


class ComparisonReport(BaseModel):
    query: str
    rows: list[ComparisonRow]
    recommendation: str = Field(description="최종 추천과 이유 2~4문장. 결정은 사용자가 한다는 전제")
    caveats: list[str] = Field(description="데이터 한계, 가격 변동, 확인 못 한 항목")
