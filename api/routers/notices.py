from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from sync.rakuraku_client import get_contracts_by_month
from sync.db import get_contractor
from api.services.notice_generator import generate_notice_pdf
from api.services.sender import send_notice

router = APIRouter()


class GenerateBody(BaseModel):
    month: str
    contractor_ids: List[str]
    excluded_case_ids: List[str] = []


@router.post("/api/notices/generate")
def generate_notices(body: GenerateBody):
    all_contracts = get_contracts_by_month(body.month)
    excluded_set = set(body.excluded_case_ids)

    results = []
    for contractor_id in body.contractor_ids:
        contractor = get_contractor(contractor_id)
        if not contractor:
            results.append({
                "contractor_id": contractor_id,
                "name": "",
                "status": "error",
                "pdf_url": None,
                "error_msg": "施工店が見つかりません",
            })
            continue

        cases = [
            c for c in all_contracts
            if c["contractor_id"] == contractor_id and c["case_id"] not in excluded_set
        ]

        output_dir = os.path.join("output", body.month)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{contractor_id}.pdf")

        try:
            pdf_path = generate_notice_pdf(contractor, cases, body.month, output_path)
            send_notice(contractor, pdf_path, body.month)
            notice_id = f"{body.month}_{contractor_id}"
            results.append({
                "contractor_id": contractor_id,
                "name": contractor["name"],
                "status": "success",
                "pdf_url": f"/api/notices/{notice_id}/pdf",
                "error_msg": None,
            })
        except Exception as e:
            results.append({
                "contractor_id": contractor_id,
                "name": contractor["name"],
                "status": "error",
                "pdf_url": None,
                "error_msg": str(e),
            })

    return {"results": results}


@router.get("/api/notices/{notice_id}/pdf")
def get_notice_pdf(notice_id: str):
    # notice_id format: {month}_{contractor_id}
    parts = notice_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="不正なnotice_id形式")
    month, contractor_id = parts
    pdf_path = os.path.join("output", month, f"{contractor_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDFが見つかりません")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{contractor_id}.pdf")
