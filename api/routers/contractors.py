from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from sync.rakuraku_client import get_contracts_by_month
from sync.db import get_contractor, get_excluded_cases, upsert_excluded_case

router = APIRouter()


@router.get("/api/contractors")
def list_contractors(month: str):
    contracts = get_contracts_by_month(month)
    excluded = get_excluded_cases(month)
    excluded_case_ids = {e["case_id"] for e in excluded}

    grouped: dict[str, dict] = {}
    for c in contracts:
        cid = c["contractor_id"]
        if cid not in grouped:
            contractor = get_contractor(cid)
            grouped[cid] = {
                "contractor_id": cid,
                "name": contractor["name"] if contractor else cid,
                "case_count": 0,
                "total_amount": 0,
                "carried_over": False,
            }
        grouped[cid]["case_count"] += 1
        grouped[cid]["total_amount"] += c.get("amount_with_tax", 0)
        if c["case_id"] in excluded_case_ids:
            grouped[cid]["carried_over"] = True

    return list(grouped.values())


@router.get("/api/contractors/{contractor_id}/cases")
def list_cases(contractor_id: str, month: str):
    contracts = get_contracts_by_month(month)
    excluded = get_excluded_cases(month)
    excluded_map = {e["case_id"]: e for e in excluded}

    cases = []
    for c in contracts:
        if c["contractor_id"] != contractor_id:
            continue
        ex = excluded_map.get(c["case_id"])
        cases.append({
            "case_id": c["case_id"],
            "case_name": c.get("case_name", ""),
            "construction_date": c.get("construction_date", ""),
            "amount": c.get("amount", 0),
            "tax": c.get("tax", 0),
            "amount_with_tax": c.get("amount_with_tax", 0),
            "excluded": ex is not None,
            "carried_over": ex["reason"] == "carry_over" if ex else False,
        })
    return cases


class ExcludeBody(BaseModel):
    contractor_id: str
    reason: str  # carry_over | checking | not_billed
    memo: Optional[str] = ""
    target_month: str
    carry_to_month: Optional[str] = None


@router.post("/api/cases/{case_id}/exclude")
def exclude_case(case_id: str, body: ExcludeBody):
    upsert_excluded_case(
        case_id=case_id,
        contractor_id=body.contractor_id,
        reason=body.reason,
        memo=body.memo or "",
        target_month=body.target_month,
        carry_to_month=body.carry_to_month,
    )
    return {"status": "ok"}
