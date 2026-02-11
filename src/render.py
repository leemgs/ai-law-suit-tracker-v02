from __future__ import annotations
from typing import List
from collections import Counter
from .extract import Lawsuit
from .courtlistener import CLDocument, CLCaseSummary


def _esc(s: str) -> str:
    s = str(s or "").strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("```", "&#96;&#96;&#96;")
    s = s.replace("~~~", "&#126;&#126;&#126;")
    s = s.replace("|", "\\|")
    s = s.replace("\n", "<br>")
    return s


def _md_sep(col_count: int) -> str:
    return "|" + "---| " * col_count


def _mdlink(label: str, url: str) -> str:
    label = _esc(label)
    url = (url or "").strip()
    if not url:
        return label
    return f"[{label}]({url})"


def _short(val: str, limit: int = 140) -> str:
    val = val or ""
    if len(val) <= limit:
        return _esc(val)
    return f"<details><summary>내용 펼치기</summary>{_esc(val)}</details>"


# =====================================================
# 🔥 위험도 점수 계산
# =====================================================
def calculate_news_risk_score(title: str, reason: str) -> int:
    score = 0
    text = f"{title or ''} {reason or ''}".lower()

    if any(k in text for k in ["scrape", "crawl", "unauthorised", "unauthorized"]):
        score += 30
    if any(k in text for k in ["train", "training", "model", "llm"]):
        score += 30
    if any(k in text for k in ["copyright", "dmca", "infringement"]):
        score += 20
    if "class action" in text:
        score += 10
    if any(k in text for k in ["billion", "$"]):
        score += 10

    return min(score, 100)


def format_risk(score: int) -> str:
    if score >= 80:
        return f"🔥 {score}"
    if score >= 60:
        return f"⚠️ {score}"
    if score >= 40:
        return f"🟡 {score}"
    return f"🟢 {score}"


# =====================================================
# 🔥 RECAP 위험도
# =====================================================
def calculate_case_risk_score(case: CLCaseSummary) -> int:
    score = 0
    text = f"{case.extracted_ai_snippet or ''} {case.extracted_causes or ''}".lower()

    if any(k in text for k in ["scrape", "crawl", "ingest", "harvest"]):
        score += 30
    if any(k in text for k in ["train", "training", "model", "llm", "neural"]):
        score += 30
    if any(k in text for k in ["commercial", "profit"]):
        score += 15
    if case.nature_of_suit and "820" in case.nature_of_suit:
        score += 15
    if "class action" in text:
        score += 10

    return min(score, 100)


# =====================================================
# 🔥 메인 렌더
# =====================================================
def render_markdown(
    lawsuits: List[Lawsuit],
    cl_docs: List[CLDocument],
    cl_cases: List[CLCaseSummary],
    lookback_days: int = 3,
) -> str:

    lines: List[str] = []

    # 📊 KPI
    lines.append(f"## 📊 최근 {lookback_days}일 요약\n")
    lines.append("| 구분 | 건수 |")
    lines.append("|---|---|")
    lines.append(f"| 📰 뉴스 수집 | **{len(lawsuits)}** |")
    lines.append(f"| ⚖️ RECAP 사건 | **{len(cl_cases)}** |")
    lines.append(f"| 📄 RECAP 문서 | **{len(cl_docs)}** |\n")

    # 📊 Nature 통계
    if cl_cases:
        counter = Counter([c.nature_of_suit or "미확인" for c in cl_cases])
        lines.append("## 📊 Nature of Suit 통계\n")
        lines.append("| Nature of Suit | 건수 |")
        lines.append("|---|---|")
        for k, v in counter.most_common(10):
            lines.append(f"| {_esc(k)} | **{v}** |")
        lines.append("")

    # 🧠 AI Top3
    if cl_cases:
        lines.append("## 🧠 AI 핵심 요약 (Top 3)\n")
        top_cases = sorted(cl_cases, key=lambda x: x.date_filed, reverse=True)[:3]
        for c in top_cases:
            lines.append(f"> **{_esc(c.case_name)}**")
            lines.append(f"> {_short(c.extracted_ai_snippet, 120)}\n")

    # 📰 뉴스 테이블 (기존 + 위험도 추가)
    if lawsuits:
        lines.append("## 📰 뉴스/RSS 기반 소송 요약")
        lines.append("| 일자 | 제목 | 소송번호 | 사유 | 위험도 예측 점수 |")
        lines.append(_md_sep(5))

        for s in lawsuits:
            article_url = s.article_urls[0] if getattr(s, "article_urls", None) else ""
            title_cell = _mdlink(s.article_title or s.case_title, article_url)

            risk_score = calculate_news_risk_score(
                s.article_title or s.case_title, s.reason
            )

            lines.append(
                f"| {_esc(s.update_or_filed_date)} | "
                f"{title_cell} | "
                f"{_esc(s.case_number)} | "
                f"{_short(s.reason)} | "
                f"{format_risk(risk_score)} |"
            )

        lines.append("")

    # 📘 위험도 평가 척도
    lines.append("<details>")
    lines.append("<summary><strong>📘 AI 학습 위험도 점수(0~100) 평가 척도</strong></summary>\n")
    lines.append("- 0~39 🟢 : 간접 연관")
    lines.append("- 40~59 🟡 : 학습 쟁점 존재")
    lines.append("- 60~79 ⚠️ : 모델 학습 직접 언급")
    lines.append("- 80~100 🔥 : 무단 수집 + 학습 + 상업적 사용 고위험")
    lines.append("</details>\n")

    # 🔥 820
    if cl_cases:
        lines.append("## 🔥 820 Copyright\n")
        lines.append("| 상태 | 케이스명 | 도켓번호 | Nature | 위험도 |")
        lines.append(_md_sep(5))

        for c in cl_cases:
            if "820" in (c.nature_of_suit or ""):
                docket_url = f"https://www.courtlistener.com/docket/{c.docket_id}/"
                score = calculate_case_risk_score(c)
                lines.append(
                    f"| {_esc(c.status)} | "
                    f"{_mdlink(c.case_name, docket_url)} | "
                    f"{_mdlink(c.docket_number, docket_url)} | "
                    f"{_esc(c.nature_of_suit)} | "
                    f"{format_risk(score)} |"
                )

    # 📄 RECAP 문서
    if cl_docs:
        lines.append("## 📄 RECAP 문서 기반 (Complaint/Petition 우선)")
        lines.append("| 제출일 | 케이스 | 문서유형 | 문서 |")
        lines.append(_md_sep(4))
        for d in cl_docs:
            link = d.document_url or d.pdf_url
            lines.append(
                f"| {_esc(d.date_filed)} | {_esc(d.case_name)} | "
                f"{_esc(d.doc_type)} | {_mdlink('Document', link)} |"
            )

    # 📰 기사 주소 fold
    if lawsuits:
        lines.append("<details>")
        lines.append("<summary><strong>📰 기사 주소</strong></summary>\n")
        for s in lawsuits:
            lines.append(f"### {_esc(s.article_title or s.case_title)}")
            for u in s.article_urls:
                lines.append(f"- {u}")
        lines.append("</details>\n")

    return "\n".join(lines)
