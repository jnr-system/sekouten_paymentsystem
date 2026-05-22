import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# 1スプレッドシート・1シート構成
# A=施工店ID, B=取引先コード, C=取引先名, D=インボイス登録番号,
# E=郵便番号, F=住所１, G=金融機関, H=支店名, I=口座種別, J=口座番号, K=口座名義

_SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
_PLACEHOLDER = {"スプシのID", ""}

_USE_DUMMY = _SPREADSHEET_ID in _PLACEHOLDER

if not _USE_DUMMY:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    _CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "google_secret.json")
    _SHEET_NAME = os.environ["SHEET_NAME"]

    def _build_service():
        creds = service_account.Credentials.from_service_account_file(
            _CREDENTIALS_PATH, scopes=SCOPES
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


def get_master_rows() -> list[list]:
    """施工店マスタシートを全件取得する。"""
    if _USE_DUMMY:
        logger.info("[ダミー] マスタシートをスキップ")
        return []
    return _fetch_rows(_SPREADSHEET_ID, _SHEET_NAME)


if __name__ == "__main__":
    if _USE_DUMMY:
        print("ダミーモード: .env に SPREADSHEET_ID を設定すると本番モードになります")
    else:
        print(f"マスタ: {len(get_master_rows())} 行")
