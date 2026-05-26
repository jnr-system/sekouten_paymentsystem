from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List
from sync.rakuraku_client import get_contracts_by_month
from sync.db import get_contractor
from api.services.sender import send_notice

router = APIRouter()

# メモリ上のPDFキャッシュ: {notice_id: {"pdf": bytes, "name": str, "month": str}}
_pdf_cache: dict[str, dict] = {}


def _pdf_worker(contractor: dict, cases: list, month: str) -> dict:
    """別プロセスで実行: PDF生成 + 送付。結果をdictで返す（pickle可能な型のみ）。"""
    from api.services.notice_generator import generate_notice_pdf
    from api.services.sender import send_notice
    from io import BytesIO

    contractor_id = contractor["contractor_id"]
    try:
        pdf_bytes = generate_notice_pdf(contractor, cases, month)
        send_notice(contractor, BytesIO(pdf_bytes), month)
        return {
            "contractor_id": contractor_id,
            "name": contractor["name"],
            "status": "success",
            "pdf_bytes": pdf_bytes,
            "error_msg": None,
        }
    except Exception as e:
        return {
            "contractor_id": contractor_id,
            "name": contractor["name"],
            "status": "error",
            "pdf_bytes": None,
            "error_msg": str(e),
        }


class GenerateBody(BaseModel):
    month: str
    contractor_ids: List[str]
    excluded_case_ids: List[str] = []


@router.post("/api/notices/generate")
def generate_notices(body: GenerateBody):
    all_contracts = get_contracts_by_month(body.month)
    excluded_set = set(body.excluded_case_ids)

    # 各施工店のデータをメインプロセスで準備してワーカーに渡す
    tasks = []
    for cid in body.contractor_ids:
        contractor = get_contractor(cid)
        if not contractor:
            tasks.append((cid, None, None))
            continue
        cases = [c for c in all_contracts
                 if c["contractor_id"] == cid and c["case_id"] not in excluded_set]
        tasks.append((cid, contractor, cases))

    results_map = {}
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {}
        for cid, contractor, cases in tasks:
            if contractor is None:
                results_map[cid] = {
                    "contractor_id": cid, "name": "", "status": "error",
                    "pdf_url": None, "notice_id": None, "error_msg": "施工店が見つかりません",
                }
                continue
            futures[executor.submit(_pdf_worker, contractor, cases, body.month)] = cid

        for future in as_completed(futures):
            cid = futures[future]
            result = future.result()
            notice_id = f"{body.month}_{cid}"
            if result["status"] == "success":
                _pdf_cache[notice_id] = {
                    "pdf": result["pdf_bytes"],
                    "name": result["name"],
                    "month": body.month,
                }
                results_map[cid] = {
                    "contractor_id": cid,
                    "name": result["name"],
                    "status": "success",
                    "pdf_url": f"/api/notices/{notice_id}/pdf",
                    "notice_id": notice_id,
                    "error_msg": None,
                }
            else:
                results_map[cid] = {
                    "contractor_id": cid,
                    "name": result["name"],
                    "status": "error",
                    "pdf_url": None,
                    "notice_id": None,
                    "error_msg": result["error_msg"],
                }

    return {"results": [results_map[cid] for cid in body.contractor_ids]}


@router.get("/api/notices/{notice_id}/pdf")
def get_notice_pdf(notice_id: str):
    entry = _pdf_cache.get(notice_id)
    if not entry:
        raise HTTPException(status_code=404, detail="PDFが見つかりません。再度発行してください。")
    contractor_id = notice_id.split("_", 1)[-1]
    return Response(content=entry["pdf"], media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={contractor_id}.pdf"})


class DownloadBody(BaseModel):
    notice_ids: List[str]


@router.post("/api/notices/download")
def download_notices(body: DownloadBody):
    today = date.today().strftime("%Y%m%d")
    folder_name = f"施工店依頼書_{today}"

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for notice_id in body.notice_ids:
            entry = _pdf_cache.get(notice_id)
            if not entry:
                continue
            filename = f"{entry['name']}_{entry['month']}.pdf"
            zf.writestr(f"{folder_name}/{filename}", entry["pdf"])

    zip_bytes = zip_buffer.getvalue()
    zip_filename = f"{folder_name}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_filename)}"},
    )
