import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL          = os.environ["RAKURAKU_API_BASE_URL"].rstrip("/")
API_KEY           = os.environ["RAKURAKU_API_KEY"]
CONTRACTOR_OBJ_ID = os.environ["RAKURAKU_CONTRACTOR_OBJECT_ID"]
CONTRACT_OBJ_ID   = os.environ["RAKURAKU_CONTRACT_OBJECT_ID"]

HEADERS = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}


def _get(path: str, params: dict = None) -> dict:
    resp = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: dict) -> dict:
    resp = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _patch(path: str, data: dict) -> dict:
    resp = requests.patch(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_contractors() -> list[dict]:
    result = _get(f"/objects/{CONTRACTOR_OBJ_ID}/records")
    return result.get("records", [])


def get_contracts_by_month(month: str) -> list[dict]:
    # month: YYYY-MM 形式で対象月を指定
    result = _get(
        f"/objects/{CONTRACT_OBJ_ID}/records",
        params={"filter[target_month]": month},
    )
    return result.get("records", [])


def upsert_contractor(contractor_id: str, data: dict, rakuraku_id: str = None) -> str:
    if rakuraku_id:
        result = _patch(
            f"/objects/{CONTRACTOR_OBJ_ID}/records/{rakuraku_id}",
            data,
        )
        return str(rakuraku_id)
    else:
        result = _post(f"/objects/{CONTRACTOR_OBJ_ID}/records", data)
        # 楽楽販売APIのレスポンスからIDを取得（キー名は実APIに合わせて調整）
        return str(result.get("id") or result.get("record_id", ""))


if __name__ == "__main__":
    contractors = get_contractors()
    print(f"施工店一覧: {len(contractors)} 件")
