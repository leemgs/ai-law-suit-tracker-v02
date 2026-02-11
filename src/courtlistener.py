from __future__ import annotations

import os
import re
import requests
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from .pdf_text import extract_pdf_text
from .complaint_parse import (
    detect_causes,
    extract_ai_training_snippet,
    extract_parties_from_caption,
)

BASE = "https://www.courtlistener.com"
SEARCH_URL = BASE + "/api/rest/v4/search/"
DOCKET_URL = BASE + "/api/rest/v4/dockets/{id}/"
DOCKETS_LIST_URL = BASE + "/api/rest/v4/dockets/"
RECAP_DOCS_URL = BASE + "/api/rest/v4/recap-documents/"
PARTIES_URL = BASE + "/api/rest/v4/parties/"
DOCKET_ENTRIES_URL = BASE + "/api/rest/v4/docket-entries/"

COMPLAINT_KEYWORDS = [
    "complaint",
    "amended complaint",
    "petition",
    "class action complaint",
]

# =========================
# Dataclasses
# =========================

@dataclass
class CLDocument:
    docket_id: Optional[int]
    docket_number: str
    case_name: str
    court: str
    date_filed: str
    doc_type: str
    doc_number: str
    description: str
    document_url: str
    pdf_url: str
    pdf_text_snippet: str
    extracted_plaintiff: str
    extracted_defendant: str
    extracted_causes: str
    extracted_ai_snippet: str


@dataclass
class CLCaseSummary:
    docket_id: int
    case_name: str
    docket_number: str
    court: str
    court_short_name: str
    court_api_url: str
    date_filed: str
    status: str
    judge: str
    magistrate: str
    nature_of_suit: str
    cause: str
    parties: str
    complaint_doc_no: str
    complaint_link: str
    recent_updates: str
    extracted_causes: str
    extracted_ai_snippet: str
    docket_candidates: str = ""


# =========================
# Utility
# =========================

def _safe_str(x) -> str:
    return str(x).strip() if x is not None else ""


def _build_court_meta(court_raw: str) -> tuple[str, str]:
    court_raw = _safe_str(court_raw)
    if not court_raw or court_raw == "미확인":
        return "미확인", ""
    return court_raw, f"https://www.courtlistener.com/court/{court_raw}/"


def _headers() -> Dict[str, str]:
    token = os.getenv("COURTLISTENER_TOKEN", "").strip()
    headers = {
        "Accept": "application/json",
        "User-Agent": "ai-lawsuit-monitor/1.2",
    }
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers=_headers(), timeout=25)
        if r.status_code in (401, 403):
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _abs_url(u: str) -> str:
    if not u:
        return ""
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return u


# =========================
# Core API Helpers
# =========================

def fetch_docket(docket_id: int) -> Optional[dict]:
    return _get(DOCKET_URL.format(id=docket_id))


def list_parties(docket_id: int) -> List[dict]:
    data = _get(PARTIES_URL, params={"docket": docket_id, "page_size": 200})
    return data.get("results", []) if data else []


def list_recap_documents(docket_id: int) -> List[dict]:
    data = _get(RECAP_DOCS_URL, params={"docket": docket_id, "page_size": 50})
    return data.get("results", []) if data else []


def list_docket_entries(docket_id: int) -> List[dict]:
    data = _get(
        DOCKET_ENTRIES_URL,
        params={"docket": docket_id, "page_size": 20, "order_by": "-date_filed"},
    )
    return data.get("results", []) if data else []


# =========================
# Case Summary Builder
# =========================

def _format_parties(parties: List[dict]) -> str:
    names = []
    for p in parties[:12]:
        nm = _safe_str(p.get("name"))
        typ = _safe_str(p.get("role"))
        if nm:
            names.append(f"{nm}({typ})" if typ else nm)
    if not names:
        return "미확인"
    return "; ".join(names)


def _status_from_docket(docket: dict) -> str:
    term = _safe_str(docket.get("date_terminated"))
    if term:
        return f"종결({term[:10]})"
    return "진행중/미확인"


def build_case_summary_from_docket_id(docket_id: int) -> Optional[CLCaseSummary]:
    docket = fetch_docket(docket_id)
    if not docket:
        return None

    case_name = _safe_str(docket.get("case_name")) or "미확인"
    docket_number = _safe_str(docket.get("docket_number")) or "미확인"
    court = _safe_str(docket.get("court")) or "미확인"
    court_short_name, court_api_url = _build_court_meta(court)

    date_filed = _safe_str(docket.get("date_filed"))[:10] or "미확인"
    status = _status_from_docket(docket)

    judge = _safe_str(docket.get("assigned_to_str")) or "미확인"
    magistrate = _safe_str(docket.get("referred_to_str")) or "미확인"

    nature_of_suit = _safe_str(docket.get("nature_of_suit")) or "미확인"
    cause = _safe_str(docket.get("cause")) or "미확인"

    parties = _format_parties(list_parties(docket_id))

    recap_docs = list_recap_documents(docket_id)
    complaint_docs = [
        d for d in recap_docs
        if any(k in (_safe_str(d.get("description")).lower())
               for k in COMPLAINT_KEYWORDS)
    ]

    complaint_doc_no = "미확인"
    complaint_link = ""
    extracted_causes = "미확인"
    extracted_ai = ""

    if complaint_docs:
        d = complaint_docs[0]
        complaint_doc_no = _safe_str(d.get("document_number")) or "미확인"
        complaint_link = _abs_url(d.get("absolute_url") or "")
        pdf_url = _abs_url(d.get("filepath_local") or "")

        if pdf_url:
            snippet = extract_pdf_text(pdf_url, max_chars=4000)
            causes_list = detect_causes(snippet) or []
            extracted_causes = ", ".join(causes_list) if causes_list else "미확인"
            extracted_ai = extract_ai_training_snippet(snippet) or ""

    entries = list_docket_entries(docket_id)
    updates = []
    for e in entries[:3]:
        dt = _safe_str(e.get("date_filed"))[:10]
        desc = _safe_str(e.get("description"))
        if dt or desc:
            updates.append(f"{dt} {desc}".strip())
    recent_updates = " / ".join(updates) if updates else "미확인"

    return CLCaseSummary(
        docket_id=docket_id,
        case_name=case_name,
        docket_number=docket_number,
        court=court,
        court_short_name=court_short_name,
        court_api_url=court_api_url,
        date_filed=date_filed,
        status=status,
        judge=judge,
        magistrate=magistrate,
        nature_of_suit=nature_of_suit,
        cause=cause,
        parties=parties,
        complaint_doc_no=complaint_doc_no,
        complaint_link=complaint_link,
        recent_updates=recent_updates,
        extracted_causes=extracted_causes,
        extracted_ai_snippet=extracted_ai,
    )
