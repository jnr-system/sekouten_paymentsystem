import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# 2シート構成: 基本情報シート・口座情報シート
# 両方のIDが設定済みであれば本番モード
_SPREADSHEET_ID_BASIC = os.environ.get("SPREADSHEET_ID_BASIC", "")
_SPREADSHEET_ID_BANK  = os.environ.get("SPREADSHEET_ID_BANK", "")

_PLACEHOLDER = {"スプシのID（基本情報シート）", "スプシのID（口座情報シート）", ""}

_USE_DUMMY = (
    _SPREADSHEET_ID_BASIC in _PLACEHOLDER or
    _SPREADSHEET_ID_BANK  in _PLACEHOLDER
)

if not _USE_DUMMY:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    _CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "google_secret.json")
    _SHEET_NAME_BASIC = os.environ["SHEET_NAME_BASIC"]
    _SHEET_NAME_BANK  = os.environ["SHEET_NAME_BANK"]

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


# カラム定義
# 基本情報シート: A=施工店ID, B=施工店名, C=取引状況, D=代表者名, E=電話①, F=郵便番号, G=住所, H=インボイス番号
# 口座情報シート: A=施工店ID, B=奉行コード, C=銀行名, D=支店名, E=預金種別, F=口座番号, G=施工店名, H=口座名


def get_basic_rows() -> list[list]:
    if _USE_DUMMY:
        logger.info("[ダミー] 基本情報シートをスキップ")
        return []
    return _fetch_rows(_SPREADSHEET_ID_BASIC, _SHEET_NAME_BASIC)


def get_bank_rows() -> list[list]:
    if _USE_DUMMY:
        logger.info("[ダミー] 口座情報シートをスキップ")
        return []
    return _fetch_rows(_SPREADSHEET_ID_BANK, _SHEET_NAME_BANK)


if __name__ == "__main__":
    if _USE_DUMMY:
        print("ダミーモード: .env にスプレッドシートIDを設定すると本番モードになります")
    else:
        print(f"基本情報: {len(get_basic_rows())} 行")
        print(f"口座情報: {len(get_bank_rows())} 行")
