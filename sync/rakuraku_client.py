import os
import csv
import io
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

_DOMAIN = os.environ.get("RAKURAKU_DOMAIN", "")
_TOKEN  = os.environ.get("RAKURAKU_API_TOKEN", "")

_SCHEMA_ID = "101185"
_SEARCH_ID = "108005"
_LIST_ID   = "101543"


def _fetch_csv(search_id: str = _SEARCH_ID) -> list[list[str]]:
    url = f"https://{_DOMAIN}/mspy4wa/api/csvexport/version/v1"
    headers = {"Content-Type": "application/json; charset=utf-8", "X-HD-apitoken": _TOKEN}
    payload = {"dbSchemaId": _SCHEMA_ID, "listId": _LIST_ID, "searchId": search_id, "limit": 1000}
    res = requests.post(url, headers=headers, json=payload, timeout=30)
    res.raise_for_status()
    text = res.content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    return rows[1:] if rows else []  # ヘッダー行を除く



def get_contracts_by_month(month: str) -> list[dict]:
    """対象月の案件一覧を楽楽販売CSVエクスポートから取得して返す。"""
    rows = _fetch_csv()
    # month = "2026-05" → 施工日が "2026/05/xx" の行を抽出
    year, mon = month.split("-")
    prefix = f"{year}/{mon}/"

    contracts = []
    for row in rows:
        if len(row) < 8:
            continue
        case_id             = row[0].strip()
        arrangement_number  = row[1].strip()
        contractor_id       = row[2].strip()
        contractor_name     = row[3].strip()
        case_name           = row[4].strip()
        construction_date   = row[5].strip()
        recipient_name      = row[6].strip() if len(row) > 6 else ""
        amount_with_tax     = int(row[7].strip().replace(",", "") or 0)

        if not construction_date.startswith(prefix):
            continue

        # 施工金額（税込）から逆算して税額・税抜を算出（10%想定）
        amount = int(amount_with_tax / 1.1)
        tax    = amount_with_tax - amount

        contracts.append({
            "case_id":              case_id,
            "arrangement_number":   arrangement_number,
            "contractor_id":        contractor_id,
            "contractor_name":      contractor_name,
            "case_name":            case_name,
            "case_name_recipient":  recipient_name,
            "construction_date":    construction_date.replace("/", "-"),
            "amount":               amount,
            "tax":                  tax,
            "amount_with_tax":      amount_with_tax,
        })

    return contracts


def upsert_contractor(contractor_id: str, data: dict, rakuraku_id: str = None) -> str:
    raise NotImplementedError("楽楽販売への施工店登録はCSV方式では未対応")


if __name__ == "__main__":
    contracts = get_contracts_by_month("2026-05")
    print(f"案件一覧: {len(contracts)} 件")
    for c in contracts[:5]:
        print(c)
