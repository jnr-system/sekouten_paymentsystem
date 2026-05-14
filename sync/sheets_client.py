import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "google_secret.json")
SPREADSHEET_ID_BASIC   = os.environ["SPREADSHEET_ID_BASIC"]
SPREADSHEET_ID_INVOICE = os.environ["SPREADSHEET_ID_INVOICE"]
SPREADSHEET_ID_BANK    = os.environ["SPREADSHEET_ID_BANK"]
SHEET_NAME_BASIC   = os.environ["SHEET_NAME_BASIC"]
SHEET_NAME_INVOICE = os.environ["SHEET_NAME_INVOICE"]
SHEET_NAME_BANK    = os.environ["SHEET_NAME_BANK"]

# カラム定義（仕様確認用）
# 基本情報: A=施工店ID, B=施工店名, C=郵便番号, D=住所, E=電話番号, F=FAX番号, G=契約状態, H=メールアドレス
# インボイス: A=施工店ID, B=インボイス登録番号, C=登録日
# 振込先: A=施工店ID, B=銀行名, C=支店名, D=口座種別, E=口座番号, F=口座名義


def _build_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def _fetch_rows(spreadsheet_id: str, sheet_name: str) -> list[list]:
    service = _build_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name)
        .execute()
    )
    rows = result.get("values", [])
    return rows[1:]  # ヘッダー行を除く


def get_basic_rows() -> list[list]:
    return _fetch_rows(SPREADSHEET_ID_BASIC, SHEET_NAME_BASIC)


def get_invoice_rows() -> list[list]:
    return _fetch_rows(SPREADSHEET_ID_INVOICE, SHEET_NAME_INVOICE)


def get_bank_rows() -> list[list]:
    return _fetch_rows(SPREADSHEET_ID_BANK, SHEET_NAME_BANK)


if __name__ == "__main__":
    print(f"基本情報: {len(get_basic_rows())} 行")
    print(f"インボイス: {len(get_invoice_rows())} 行")
    print(f"振込先: {len(get_bank_rows())} 行")
