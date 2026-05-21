import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "db", "contractor.db"))

DDL = """
CREATE TABLE IF NOT EXISTS contractor_basic (
    contractor_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    postal_code     TEXT,
    address         TEXT,
    phone           TEXT,
    fax             TEXT,
    email           TEXT,
    line_user_id    TEXT,
    send_method     TEXT DEFAULT 'email',
    status          TEXT DEFAULT '継続中',
    rakuraku_id     TEXT,
    row_hash        TEXT,
    synced_at       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contractor_invoice (
    contractor_id   TEXT PRIMARY KEY,
    invoice_number  TEXT,
    registered_date DATE,
    row_hash        TEXT,
    synced_at       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contractor_id) REFERENCES contractor_basic(contractor_id)
);

CREATE TABLE IF NOT EXISTS contractor_bank (
    contractor_id   TEXT PRIMARY KEY,
    bank_name       TEXT,
    branch_name     TEXT,
    account_type    TEXT,
    account_number  TEXT,
    account_holder  TEXT,
    row_hash        TEXT,
    synced_at       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contractor_id) REFERENCES contractor_basic(contractor_id)
);

CREATE TABLE IF NOT EXISTS excluded_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    contractor_id   TEXT NOT NULL,
    exclude_reason  TEXT,
    memo            TEXT,
    target_month    TEXT,
    carry_to_month  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(DDL)
    print(f"DB initialized: {DB_PATH}")


def get_contractor(contractor_id: str) -> dict:
    sql = """
        SELECT
            b.*,
            i.invoice_number, i.registered_date,
            k.bank_name, k.branch_name, k.account_type,
            k.account_number, k.account_holder
        FROM contractor_basic b
        LEFT JOIN contractor_invoice i USING (contractor_id)
        LEFT JOIN contractor_bank    k USING (contractor_id)
        WHERE b.contractor_id = ?
    """
    with _connect() as conn:
        row = conn.execute(sql, (contractor_id,)).fetchone()
        return dict(row) if row else {}


def get_contractor_by_name(name: str) -> dict:
    sql = """
        SELECT b.contractor_id
        FROM contractor_basic b
        WHERE b.name = ?
        LIMIT 1
    """
    with _connect() as conn:
        row = conn.execute(sql, (name,)).fetchone()
        return dict(row) if row else {}


def get_all_contractors() -> list[dict]:
    sql = """
        SELECT
            b.*,
            i.invoice_number, i.registered_date,
            k.bank_name, k.branch_name, k.account_type,
            k.account_number, k.account_holder
        FROM contractor_basic b
        LEFT JOIN contractor_invoice i USING (contractor_id)
        LEFT JOIN contractor_bank    k USING (contractor_id)
        WHERE b.status = '継続中'
    """
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_excluded_cases(month: str) -> list[dict]:
    sql = "SELECT * FROM excluded_cases WHERE target_month = ?"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, (month,)).fetchall()]


def upsert_excluded_case(
    case_id: str,
    contractor_id: str,
    reason: str,
    memo: str = "",
    target_month: str = "",
    carry_to_month: str = None,
) -> None:
    sql = """
        INSERT INTO excluded_cases
            (case_id, contractor_id, exclude_reason, memo, target_month, carry_to_month)
        VALUES
            (?, ?, ?, ?, ?, ?)
    """
    with _connect() as conn:
        conn.execute(sql, (case_id, contractor_id, reason, memo, target_month, carry_to_month))


def upsert_contractor_basic(row: dict) -> None:
    sql = """
        INSERT INTO contractor_basic
            (contractor_id, name, postal_code, address, phone, fax,
             email, line_user_id, send_method, status, rakuraku_id,
             row_hash, synced_at, updated_at)
        VALUES
            (:contractor_id, :name, :postal_code, :address, :phone, :fax,
             :email, :line_user_id, :send_method, :status, :rakuraku_id,
             :row_hash, :synced_at, CURRENT_TIMESTAMP)
        ON CONFLICT(contractor_id) DO UPDATE SET
            name          = excluded.name,
            postal_code   = excluded.postal_code,
            address       = excluded.address,
            phone         = excluded.phone,
            fax           = excluded.fax,
            email         = excluded.email,
            line_user_id  = excluded.line_user_id,
            send_method   = excluded.send_method,
            status        = excluded.status,
            rakuraku_id   = excluded.rakuraku_id,
            row_hash      = excluded.row_hash,
            synced_at     = excluded.synced_at,
            updated_at    = CURRENT_TIMESTAMP
    """
    with _connect() as conn:
        conn.execute(sql, row)


def upsert_contractor_invoice(row: dict) -> None:
    sql = """
        INSERT INTO contractor_invoice
            (contractor_id, invoice_number, registered_date, row_hash, synced_at, updated_at)
        VALUES
            (:contractor_id, :invoice_number, :registered_date, :row_hash, :synced_at, CURRENT_TIMESTAMP)
        ON CONFLICT(contractor_id) DO UPDATE SET
            invoice_number  = excluded.invoice_number,
            registered_date = excluded.registered_date,
            row_hash        = excluded.row_hash,
            synced_at       = excluded.synced_at,
            updated_at      = CURRENT_TIMESTAMP
    """
    with _connect() as conn:
        conn.execute(sql, row)


def upsert_contractor_bank(row: dict) -> None:
    sql = """
        INSERT INTO contractor_bank
            (contractor_id, bank_name, branch_name, account_type,
             account_number, account_holder, row_hash, synced_at, updated_at)
        VALUES
            (:contractor_id, :bank_name, :branch_name, :account_type,
             :account_number, :account_holder, :row_hash, :synced_at, CURRENT_TIMESTAMP)
        ON CONFLICT(contractor_id) DO UPDATE SET
            bank_name      = excluded.bank_name,
            branch_name    = excluded.branch_name,
            account_type   = excluded.account_type,
            account_number = excluded.account_number,
            account_holder = excluded.account_holder,
            row_hash       = excluded.row_hash,
            synced_at      = excluded.synced_at,
            updated_at     = CURRENT_TIMESTAMP
    """
    with _connect() as conn:
        conn.execute(sql, row)


def get_unsynced_contractors() -> list[dict]:
    # synced_at IS NULL: 一度も同期していない
    # updated_at > synced_at: 前回同期後に更新された
    sql = """
        SELECT * FROM contractor_basic
        WHERE synced_at IS NULL OR updated_at > synced_at
    """
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def mark_synced(contractor_id: str, table: str) -> None:
    allowed = {"contractor_basic", "contractor_invoice", "contractor_bank"}
    if table not in allowed:
        raise ValueError(f"Unknown table: {table}")
    sql = f"UPDATE {table} SET synced_at = CURRENT_TIMESTAMP WHERE contractor_id = ?"
    with _connect() as conn:
        conn.execute(sql, (contractor_id,))


if __name__ == "__main__":
    init_db()
