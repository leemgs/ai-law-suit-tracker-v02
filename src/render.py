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
# 🔥 AI 학습 위험도 점수 계산
# =====================================================
def calculate_ai_risk_score(case: CLCaseSummary) -> int:
    score = 0
    text = f"{case.extracted_ai_snippet or ''} {case.extracted_causes or ''}".lower()

    if any(k in text for k in ["scrape", "crawl", "ingest", "harvest"]):
        score += 30

    if any(k in text for k in ["train", "training", "model", "llm", "neural"]):
        score += 30

    if any(k in text for k in ["commercial", "profit", "monetize"]):
        score += 15

    if case.nature_of_suit and "820" in case.nature_of_suit:
        score += 15

    if "class action" in text:
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


def classify_data_type(text: str) -> str:
    text = (text or "").lower()
    if any(k in text for k in ["book", "text", "novel"]):
        return "텍스트/도서"
    if any(k in text for k in ["image", "photo", "picture"]):
        return "이미지"
    if any(k in text for k in ["code", "repository", "github"]):
        return "소스코드"
    if any(k in text for k in ["music", "audio"]):
        return "음원"
    return "미확인"


def render_markdown(
    lawsuits: List[Lawsuit],
    cl_docs: List[CLDocument],
    cl_cases: List[CLCaseSummary],
    lookback_days: int = 3,
) -> str:

    lines: List[str] = []

    # =====================================================
    # 📊 KPI 요약
    # =====================================================
    lines.append(f"## 📊 최근 {lookback_days}일 요약\n")
    lines.append("| 구분 | 건수 |")
    lines.append("|---|---|")
    lines.append(f"| 📰 뉴스 수집 | **{len(lawsuits)}** |")
    lines.append(f"| ⚖️ RECAP 사건 | **{len(cl_cases)}** |")
    lines.append(f"| 📄 RECAP 문서 | **{len(cl_docs)}** |\n")

    # =====================================================
    # 📊 Nature 통계
    # =====================================================
    if cl_cases:
        counter = Counter([c.nature_of_suit or "미확인" for c in cl_cases])
        lines.append("## 📊 Nature of Suit 통계\n")
        lines.append("| Nature of Suit | 건수 |")
        lines.append("|---|---|")
        for k, v in counter.most_common(10):
            lines.append(f"| {_esc(k)} | **{v}** |")
        lines.append("")

    # =====================================================
    # ⚖️ RECAP 케이스
    # =====================================================
    if cl_cases:

        copyright_cases = []
        other_cases = []

        for c in cl_cases:
            nature = (c.nature_of_suit or "").lower()
            if "820" in nature and "copyright" in nature:
                copyright_cases.append(c)
            else:
                other_cases.append(c)

        def render_ai_table(cases):
            lines.append("| 상태 | 케이스명 | 도켓번호 | 데이터 유형 | AI 학습 핵심 주장 | 법적 근거 | 위험도 | 판사 | 법원 |")
            lines.append(_md_sep(9))

            for c in sorted(cases, key=lambda x: x.date_filed, reverse=True)[:25]:

                docket_url = f"https://www.courtlistener.com/docket/{c.docket_id}/"
                score = calculate_ai_risk_score(c)
                risk_display = format_risk(score)
                data_type = classify_data_type(c.extracted_ai_snippet)

                lines.append(
                    f"| {_esc(c.status)} | "
                    f"{_mdlink(c.case_name, docket_url)} | "
                    f"{_mdlink(c.docket_number, docket_url)} | "
                    f"{data_type} | "
                    f"{_short(c.extracted_ai_snippet, 120)} | "
                    f"{_esc(c.cause)} | "
                    f"{risk_display} | "
                    f"{_esc(c.judge)} | "
                    f"{_esc(c.court)} |"
                )

        # 🔥 820
        lines.append("## 🔥 820 Copyright (AI 학습 쟁점 중심)\n")
        if copyright_cases:
            render_ai_table(copyright_cases)
        else:
            lines.append("820 사건 없음\n")

        # 📁 Others
        lines.append("\n<details>")
        lines.append(
            '<summary><span style="font-size:1.5em; font-weight:bold;">📁 Others</span></summary>\n'
        )

        if other_cases:
            render_ai_table(other_cases)
        else:
            lines.append("Others 사건 없음\n")

        lines.append("</details>\n")

    # =====================================================
    # 📰 기사 주소
    # =====================================================
    if lawsuits:
        lines.append("<details>")
        lines.append(
            '<summary><span style="font-size:1.5em; font-weight:bold;">📰 기사 주소</span></summary>\n'
        )

        for s in lawsuits:
            if (s.case_title and s.case_title != "미확인") and (
                s.article_title and s.article_title != s.case_title
            ):
                header_title = f"{s.case_title} / {s.article_title}"
            elif s.case_title and s.case_title != "미확인":
                header_title = s.case_title
            else:
                header_title = s.article_title or s.case_title

            lines.append(f"### {_esc(header_title)}")
            for u in s.article_urls:
                lines.append(f"- {u}")
            lines.append("")

        lines.append("</details>\n")

    return "\n".join(lines)
