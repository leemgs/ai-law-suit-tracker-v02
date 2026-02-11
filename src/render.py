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


def _details(summary: str, body: str) -> str:
    body = body or ""
    if not body or body == "미확인":
        return "미확인"
    return f"<details><summary>{summary}</summary>{_esc(body)}</details>"


def _short(val: str, limit: int = 140) -> str:
    val = val or ""
    if len(val) <= limit:
        return _esc(val)
    return _details("내용 펼치기", val)


def render_markdown(
    lawsuits: List[Lawsuit],
    cl_docs: List[CLDocument],
    cl_cases: List[CLCaseSummary],
    lookback_days: int = 3,
) -> str:

    lines: List[str] = []

    # =====================================================
    # 📊 KPI 카드형 요약
    # =====================================================
    lines.append(f"## 📊 최근 {lookback_days}일 요약\n")
    lines.append("| 구분 | 건수 |")
    lines.append("|---|---|")
    lines.append(f"| 📰 뉴스 수집 | **{len(lawsuits)}** |")
    lines.append(f"| ⚖️ RECAP 사건 | **{len(cl_cases)}** |")
    lines.append(f"| 📄 RECAP 문서 | **{len(cl_docs)}** |\n")

    # =====================================================
    # 📊 Nature of Suit 통계
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
    # 🧠 AI 요약 3줄 하이라이트
    # =====================================================
    if cl_cases:
        lines.append("## 🧠 AI 핵심 요약 (Top 3)\n")
        top_cases = sorted(cl_cases, key=lambda x: x.date_filed, reverse=True)[:3]
        for c in top_cases:
            snippet = _short(c.extracted_ai_snippet, 120)
            lines.append(f"> **{_esc(c.case_name)}**")
            lines.append(f"> {snippet}\n")

    # =====================================================
    # 📰 뉴스 요약
    # =====================================================
    if lawsuits:
        lines.append("## 📰 뉴스/RSS 기반 소송 요약")
        lines.append("| 일자 | 제목 | 소송번호 | 사유 |")
        lines.append(_md_sep(4))

        for s in lawsuits:
            if (s.case_title and s.case_title != "미확인") and (
                s.article_title and s.article_title != s.case_title
            ):
                display_title = f"{s.case_title} / {s.article_title}"
            elif s.case_title and s.case_title != "미확인":
                display_title = s.case_title
            else:
                display_title = s.article_title or s.case_title

            article_url = s.article_urls[0] if getattr(s, "article_urls", None) else ""
            title_cell = _mdlink(display_title, article_url)

            lines.append(
                f"| {_esc(s.update_or_filed_date)} | {title_cell} | {_esc(s.case_number)} | {_short(s.reason)} |"
            )

        lines.append("\n---\n")

    # =====================================================
    # ⚖️ RECAP 케이스 분리
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

        def render_table(cases):
            lines.append("| 상태 | 접수일 | 케이스명 | Nature | Complaint |")
            lines.append(_md_sep(5))
            for c in sorted(cases, key=lambda x: x.date_filed, reverse=True)[:25]:
                lines.append(
                    f"| {_esc(c.status)} | "
                    f"{_esc(c.date_filed)} | "
                    f"{_mdlink(c.case_name, f'https://www.courtlistener.com/docket/{c.docket_id}/')} | "
                    f"{_esc(c.nature_of_suit)} | "
                    f"{_mdlink('Complaint', c.complaint_link)} |"
                )

        # 🔥 820
        lines.append("## 🔥 820 Copyright\n")
        if copyright_cases:
            render_table(copyright_cases)
        else:
            lines.append("820 사건 없음\n")

        # 📁 Others (동일 크기 + fold)
        lines.append("\n<details>")
        lines.append("<summary><strong>📁 Others</strong></summary>\n")

        if other_cases:
            render_table(other_cases)
        else:
            lines.append("Others 사건 없음\n")

        lines.append("</details>\n")

    # =====================================================
    # 📄 RECAP 문서
    # =====================================================
    if cl_docs:
        lines.append("## 📄 RECAP 문서 기반 (Complaint/Petition 우선)")
        lines.append("| 제출일 | 케이스 | 문서유형 | 문서 |")
        lines.append(_md_sep(4))

        for d in sorted(cl_docs, key=lambda x: x.date_filed, reverse=True)[:20]:
            link = d.document_url or d.pdf_url
            lines.append(
                f"| {_esc(d.date_filed)} | {_esc(d.case_name)} | {_esc(d.doc_type)} | {_mdlink('Document', link)} |"
            )

        lines.append("")

    # =====================================================
    # 📰 기사 주소 (Fold 처리)
    # =====================================================
    if lawsuits:
        lines.append("<details>")
        lines.append("<summary><strong>📰 기사 주소</strong></summary>\n")

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
