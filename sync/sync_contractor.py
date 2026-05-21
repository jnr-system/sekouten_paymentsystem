import hashlib
import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import db
import sheets_client
import rakuraku_client

# ログ設定
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"sync_{datetime.now():%Y%m%d}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def compute_row_hash(row: list) -> str:
    return hashlib.md5(
        json.dumps(row, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _pad(row: list, length: int) -> list:
    """列数が足りない行を空文字でパディングする"""
    return row + [""] * (length - len(row))


def sync_basic_rows() -> int:
    rows = sheets_client.get_basic_rows()
    upserted = 0
    for raw in rows:
        row = _pad(raw, 8)
        # A=施工店ID, B=施工店名, C=取引状況, D=代表者名, E=電話①, F=郵便番号, G=住所, H=インボイス番号
        contractor_id = row[0].strip()
        if not contractor_id:
            continue
        status = row[2].strip()
        if status != "継続中":
            continue
        new_hash = compute_row_hash(row)
        existing = db.get_contractor(contractor_id)
        if existing.get("row_hash") == new_hash:
            continue
        db.upsert_contractor_basic({
            "contractor_id": contractor_id,
            "name":          row[1],
            "status":        row[2] or "継続中",
            "phone":         row[4],
            "postal_code":   row[5],
            "address":       row[6],
            "fax":           "",
            "email":         "",
            "line_user_id":  existing.get("line_user_id"),
            "send_method":   existing.get("send_method", "email"),
            "rakuraku_id":   existing.get("rakuraku_id"),
            "row_hash":      new_hash,
            "synced_at":     None,
        })
        # インボイス番号も同じ行から取得してinvoiceテーブルへ
        invoice_number = row[7].strip()
        if invoice_number:
            db.upsert_contractor_invoice({
                "contractor_id":   contractor_id,
                "invoice_number":  invoice_number,
                "registered_date": None,
                "row_hash":        new_hash,
                "synced_at":       None,
            })
        upserted += 1
    return upserted


def sync_bank_rows() -> int:
    rows = sheets_client.get_bank_rows()
    upserted = 0
    for raw in rows:
        row = _pad(raw, 8)
        # A=施工店ID, B=奉行コード, C=銀行名, D=支店名, E=預金種別, F=口座番号, G=施工店名, H=口座名
        contractor_id = row[0].strip()
        if not contractor_id:
            continue
        if not row[2].strip():
            continue
        new_hash = compute_row_hash(row)
        existing = db.get_contractor(contractor_id)
        if existing.get("row_hash") == new_hash:
            continue
        db.upsert_contractor_bank({
            "contractor_id":  contractor_id,
            "bank_name":      row[2],
            "branch_name":    row[3],
            "account_type":   row[4],
            "account_number": row[5],
            "account_holder": row[7],
            "row_hash":       new_hash,
            "synced_at":      None,
        })
        upserted += 1
    return upserted


def sync_to_rakuraku() -> tuple[int, int]:
    """未同期レコードを楽楽販売APIにPOST/PATCHし、成功件数と失敗件数を返す"""
    unsynced = db.get_unsynced_contractors()
    ok = 0
    ng = 0
    for contractor in unsynced:
        contractor_id = contractor["contractor_id"]
        rakuraku_id   = contractor.get("rakuraku_id")
        data = {
            "contractor_id": contractor_id,
            "name":          contractor.get("name"),
            "postal_code":   contractor.get("postal_code"),
            "address":       contractor.get("address"),
            "phone":         contractor.get("phone"),
            "fax":           contractor.get("fax"),
            "email":         contractor.get("email"),
            "status":        contractor.get("status"),
        }
        try:
            returned_id = rakuraku_client.upsert_contractor(
                contractor_id, data, rakuraku_id
            )
            # 新規POSTで楽楽IDが採番された場合はDBに保存
            if not rakuraku_id and returned_id:
                existing = db.get_contractor(contractor_id)
                db.upsert_contractor_basic({**existing, "rakuraku_id": returned_id})
            db.mark_synced(contractor_id, "contractor_basic")
            logger.info(f"Synced contractor {contractor_id} (rakuraku_id={returned_id})")
            ok += 1
        except Exception as e:
            logger.error(f"Failed to sync contractor {contractor_id}: {e}")
            ng += 1
    return ok, ng


def main() -> None:
    logger.info("=== sync_contractor 開始 ===")

    # 1. Google Sheetsから取得してSQLiteへ差分Upsert
    try:
        b = sync_basic_rows()
        logger.info(f"基本情報（インボイス含む） upsert: {b} 件")
    except Exception as e:
        logger.error(f"基本情報シート取得失敗: {e}")

    try:
        k = sync_bank_rows()
        logger.info(f"口座情報 upsert: {k} 件")
    except Exception as e:
        logger.error(f"口座情報シート取得失敗: {e}")

    # 2. 未同期レコードを楽楽販売APIへ反映
    ok, ng = sync_to_rakuraku()
    logger.info(f"楽楽販売 同期: 成功 {ok} 件 / 失敗 {ng} 件")

    logger.info("=== sync_contractor 完了 ===")


if __name__ == "__main__":
    main()
