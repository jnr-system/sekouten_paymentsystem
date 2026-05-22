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

# カラムインデックス（0始まり）
# A=施工店ID, B=取引先コード, C=取引先名, D=インボイス登録番号,
# E=郵便番号, F=住所１, G=金融機関, H=支店名, I=口座種別, J=口座番号, K=口座名義
_COL_ID       = 0
_COL_CODE     = 1
_COL_NAME     = 2
_COL_INVOICE  = 3
_COL_POSTAL   = 4
_COL_ADDRESS  = 5
_COL_BANK     = 6
_COL_BRANCH   = 7
_COL_ACCT_TYPE = 8
_COL_ACCT_NUM  = 9
_COL_ACCT_NAME = 10
_MASTER_COLS   = 11

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


def sync_master_rows() -> int:
    """マスタシート1枚から施工店基本情報・インボイス・口座情報をまとめてUpsertする。"""
    rows = sheets_client.get_master_rows()
    upserted = 0
    for raw in rows:
        row = _pad(raw, _MASTER_COLS)
        contractor_id = row[_COL_ID].strip()
        if not contractor_id:
            continue
        if not row[_COL_NAME].strip():
            continue

        new_hash = compute_row_hash(row)
        existing = db.get_contractor(contractor_id)
        if existing.get("row_hash") == new_hash:
            continue

        db.upsert_contractor_basic({
            "contractor_id": contractor_id,
            "name":          row[_COL_NAME].strip(),
            "status":        "継続中",
            "postal_code":   row[_COL_POSTAL].strip(),
            "address":       row[_COL_ADDRESS].strip(),
            "phone":         "",
            "fax":           "",
            "email":         existing.get("email", ""),
            "line_user_id":  existing.get("line_user_id"),
            "send_method":   existing.get("send_method", "email"),
            "rakuraku_id":   existing.get("rakuraku_id"),
            "row_hash":      new_hash,
            "synced_at":     None,
        })

        invoice_number = row[_COL_INVOICE].strip()
        if invoice_number:
            db.upsert_contractor_invoice({
                "contractor_id":   contractor_id,
                "invoice_number":  invoice_number,
                "registered_date": None,
                "row_hash":        new_hash,
                "synced_at":       None,
            })

        bank_name = row[_COL_BANK].strip()
        if bank_name:
            db.upsert_contractor_bank({
                "contractor_id":  contractor_id,
                "bank_name":      bank_name,
                "branch_name":    row[_COL_BRANCH].strip(),
                "account_type":   row[_COL_ACCT_TYPE].strip(),
                "account_number": row[_COL_ACCT_NUM].strip(),
                "account_holder": row[_COL_ACCT_NAME].strip(),
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
        n = sync_master_rows()
        logger.info(f"マスタシート upsert: {n} 件")
    except Exception as e:
        logger.error(f"マスタシート取得失敗: {e}")

    # 2. 未同期レコードを楽楽販売APIへ反映
    ok, ng = sync_to_rakuraku()
    logger.info(f"楽楽販売 同期: 成功 {ok} 件 / 失敗 {ng} 件")

    logger.info("=== sync_contractor 完了 ===")


if __name__ == "__main__":
    main()
