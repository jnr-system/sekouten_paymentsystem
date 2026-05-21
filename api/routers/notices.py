from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List
from sync.rakuraku_client import get_contracts_by_month
from sync.db import get_contractor
from api.services.notice_generator import generate_notice_pdf
from api.services.sender import send_notice

router = APIRouter()

# メモリ上のPDFキャッシュ: {notice_id: bytes}
_pdf_cache: dict[str, bytes] = {}


class GenerateBody(BaseModel):
    month: str
    contractor_ids: List[str]
    excluded_case_ids: List[str] = []


def _generate_one(contractor_id, all_contracts, excluded_set, month):
    contractor = get_contractor(contractor_id)
    if not contractor:
        return {"contractor_id": contractor_id, "name": "", "status": "error",
                "pdf_url": None, "error_msg": "施工店が見つかりません"}

    cases = [c for c in all_contracts
             if c["contractor_id"] == contractor_id and c["case_id"] not in excluded_set]

    try:
        pdf_bytes = generate_notice_pdf(contractor, cases, month)
        send_notice(contractor, BytesIO(pdf_bytes), month)
        notice_id = f"{month}_{contractor_id}"
        _pdf_cache[notice_id] = pdf_bytes
        return {"contractor_id": contractor_id, "name": contractor["name"],
                "status": "success", "pdf_url": f"/api/notices/{notice_id}/pdf", "error_msg": None}
    except Exception as e:
        return {"contractor_id": contractor_id, "name": contractor["name"],
                "status": "error", "pdf_url": None, "error_msg": str(e)}


@router.post("/api/notices/generate")
def generate_notices(body: GenerateBody):
    all_contracts = get_contracts_by_month(body.month)
    excluded_set = set(body.excluded_case_ids)

    results_map = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_generate_one, cid, all_contracts, excluded_set, body.month): cid
            for cid in body.contractor_ids
        }
        for future in as_completed(futures):
            cid = futures[future]
            results_map[cid] = future.result()

    return {"results": [results_map[cid] for cid in body.contractor_ids]}


@router.get("/api/notices/{notice_id}/pdf")
def get_notice_pdf(notice_id: str):
    pdf_bytes = _pdf_cache.get(notice_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDFが見つかりません。再度発行してください。")
    contractor_id = notice_id.split("_", 1)[-1]
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={contractor_id}.pdf"})
