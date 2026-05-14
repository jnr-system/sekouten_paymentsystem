# sekouten_paymentsystem

施工店マスタ管理・支払通知書発行システム。Claude Codeへの実装指示書。このファイルを読んだ上でコーディングすること。

---

## システム概要

施工店のマスタデータをスプレッドシートで管理し、SQLite中間DBを経由して楽楽販売に同期する。
月次で楽楽販売の成約管理データと施工店マスタを結合し、支払通知書PDFを一括発行するWebツールを構築する。

---

## ディレクトリ構成

```
/root/project/sekouten_paymentsystem/
├── README.md                  # このファイル
├── .env                       # 環境変数（後述）
├── .env.example               # 環境変数のサンプル
├── requirements.txt           # Python依存パッケージ
│
├── sync/
│   ├── sync_contractor.py     # メイン同期スクリプト（systemdタイマーで実行）
│   ├── sheets_client.py       # Google Sheets API ラッパー
│   ├── rakuraku_client.py     # 楽楽販売API ラッパー
│   └── db.py                  # SQLite操作
│
├── api/
│   ├── main.py                # FastAPI エントリーポイント
│   ├── routers/
│   │   ├── contractors.py     # 施工店一覧・明細エンドポイント
│   │   └── notices.py         # 支払通知書発行エンドポイント
│   └── services/
│       ├── notice_generator.py # PDF生成ロジック
│       └── sender.py          # メール/LINE/FAX送信
│
├── frontend/
│   └── index.html             # 支払通知書発行UI（Webブラウザで動作・バニラJS）
│
├── systemd/
│   ├── contractor-api.service # FastAPI常時起動
│   ├── contractor-sync.service # 同期スクリプト実行unit
│   └── contractor-sync.timer  # 毎朝6時トリガー
│
└── db/
    └── contractor.db          # SQLiteデータベースファイル
```

---

## 環境変数（.env）

```env
# Google Sheets API
GOOGLE_CREDENTIALS_PATH=/root/project/sekouten_paymentsystem/credentials.json
SPREADSHEET_ID_BASIC=スプシのID（基本情報シート）
SPREADSHEET_ID_INVOICE=スプシのID（インボイスシート）
SPREADSHEET_ID_BANK=スプシのID（振込先シート）
SHEET_NAME_BASIC=基本情報シート
SHEET_NAME_INVOICE=インボイスシート
SHEET_NAME_BANK=振込先シート

# 楽楽販売API
RAKURAKU_API_BASE_URL=https://xxxxx.rakurakuhanbai.jp/api/v1
RAKURAKU_API_KEY=楽楽販売のAPIキー
RAKURAKU_CONTRACTOR_OBJECT_ID=施工店マスタのオブジェクトID
RAKURAKU_CONTRACT_OBJECT_ID=成約管理のオブジェクトID

# SQLite
SQLITE_DB_PATH=/root/project/sekouten_paymentsystem/db/contractor.db

# メール送信（Gmail SMTP）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=送信元メールアドレス
SMTP_PASSWORD=Gmailアプリパスワード
MAIL_FROM=送信元メールアドレス

# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN=LINEのチャネルアクセストークン

# FastAPI
API_HOST=0.0.0.0
API_PORT=8001
```

---

## データ設計

### SQLite テーブル定義

```sql
-- 施工店基本情報
CREATE TABLE IF NOT EXISTS contractor_basic (
    contractor_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    postal_code     TEXT,
    address         TEXT,
    phone           TEXT,
    fax             TEXT,
    email           TEXT,
    line_user_id    TEXT,
    send_method     TEXT DEFAULT 'email',  -- 'email' | 'line' | 'fax' | 'manual'
    status          TEXT DEFAULT '継続中', -- '継続中' | '終了'
    rakuraku_id     TEXT,                  -- 楽楽販売側のレコードID
    row_hash        TEXT,                  -- 差分検知用ハッシュ
    synced_at       DATETIME,             -- 楽楽販売への最終同期日時
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- インボイス情報
CREATE TABLE IF NOT EXISTS contractor_invoice (
    contractor_id   TEXT PRIMARY KEY,
    invoice_number  TEXT,                  -- T + 12桁
    registered_date DATE,
    row_hash        TEXT,
    synced_at       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contractor_id) REFERENCES contractor_basic(contractor_id)
);

-- 振込先情報
CREATE TABLE IF NOT EXISTS contractor_bank (
    contractor_id   TEXT PRIMARY KEY,
    bank_name       TEXT,
    branch_name     TEXT,
    account_type    TEXT,                  -- '普通' | '当座'
    account_number  TEXT,
    account_holder  TEXT,
    row_hash        TEXT,
    synced_at       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contractor_id) REFERENCES contractor_basic(contractor_id)
);

-- 案件除外管理（持ち越し・確認中）
CREATE TABLE IF NOT EXISTS excluded_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,         -- 楽楽販売の案件レコードID
    contractor_id   TEXT NOT NULL,
    exclude_reason  TEXT,                  -- 'carry_over' | 'checking' | 'not_billed'
    memo            TEXT,
    target_month    TEXT,                  -- 除外対象月 YYYY-MM
    carry_to_month  TEXT,                  -- 持ち越し先月 YYYY-MM（carry_overのみ）
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### スプレッドシートのカラム定義

**基本情報シート（A列〜）**

| 列 | 項目名 |
|---|---|
| A | 施工店ID |
| B | 施工店名 |
| C | 郵便番号 |
| D | 住所 |
| E | 電話番号 |
| F | FAX番号 |
| G | 契約状態（継続中 / 終了） |
| H | メールアドレス |

**インボイスシート（A列〜）**

| 列 | 項目名 |
|---|---|
| A | 施工店ID |
| B | インボイス登録番号（T+12桁） |
| C | 登録日 |

**振込先シート（A列〜）**

| 列 | 項目名 |
|---|---|
| A | 施工店ID |
| B | 銀行名 |
| C | 支店名 |
| D | 口座種別（普通 / 当座） |
| E | 口座番号 |
| F | 口座名義 |

---

## 同期スクリプト（sync/sync_contractor.py）

### 処理フロー

```
1. Google Sheets APIでスプシ3シートを全件取得
2. 各行をrow_hash（MD5）で差分検知
3. 差分行だけSQLiteにUpsert
4. SQLiteの未同期レコード（synced_at IS NULL または updated_at > synced_at）を楽楽販売APIにPATCH/POST
5. 同期成功したレコードのsynced_atを更新
6. 実行ログをファイル出力
```

### 差分検知ロジック

```python
import hashlib, json

def row_hash(row: list) -> str:
    """行データをMD5ハッシュ化して差分検知に使う"""
    return hashlib.md5(
        json.dumps(row, ensure_ascii=False, default=str).encode()
    ).hexdigest()

# SQLiteの既存ハッシュと比較し、変わっていた行だけUpsert対象にする
```

### systemdタイマーの設定

同期スクリプトはsystemdタイマーで毎朝6時に実行する。`systemd/` ディレクトリに以下の2ファイルを配置し、`/etc/systemd/system/` にコピーして有効化すること。

```ini
# systemd/contractor-sync.service
[Unit]
Description=Contractor Sync Script
After=network.target

[Service]
User=root
WorkingDirectory=/root/project/sekouten_paymentsystem
ExecStart=/usr/bin/python3 sync/sync_contractor.py
EnvironmentFile=/root/project/sekouten_paymentsystem/.env
StandardOutput=journal
StandardError=journal
```

```ini
# systemd/contractor-sync.timer
[Unit]
Description=Run Contractor Sync daily at 6am

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# 有効化手順
cp systemd/contractor-sync.service /etc/systemd/system/
cp systemd/contractor-sync.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable contractor-sync.timer
systemctl start contractor-sync.timer

# 動作確認
systemctl list-timers | grep contractor
journalctl -u contractor-sync --since today
```

---

## APIエンドポイント（api/main.py）

FastAPI で実装。ポート8001で起動。

### エンドポイント一覧

```
GET  /api/contractors?month=2025-05
  → 対象月に施工実績のある施工店一覧を返す
  → 楽楽販売の成約管理DBから対象月の案件を取得し施工店IDでグループ化
  → 持ち越し案件がある場合はcarried_over=trueフラグを付与

GET  /api/contractors/{contractor_id}/cases?month=2025-05
  → 施工店の月次案件明細を返す
  → 除外済み案件にはexcluded=trueフラグを付与
  → 持ち越し案件にはcarried_over=trueフラグを付与

POST /api/notices/generate
  → body: { month: "2025-05", contractor_ids: ["C001", "C002"], excluded_case_ids: ["case_001"] }
  → 選択施工店の支払通知書PDFを一括生成
  → 施工店マスタのsend_methodに応じてメール/LINE/FAX自動送付
  → レスポンス: { results: [{ contractor_id, status, pdf_url }] }

POST /api/cases/{case_id}/exclude
  → body: { contractor_id, reason: "carry_over"|"checking"|"not_billed", memo, target_month, carry_to_month }
  → 案件を除外テーブルに登録

GET  /api/notices/{notice_id}/pdf
  → 生成済みPDFをダウンロード
```

---

## 支払通知書PDF仕様（api/services/notice_generator.py）

### 使用ライブラリ

WeasyPrint（HTML→PDF変換）を使用。日本語フォントはNoto Sans JPを使うこと。

```bash
pip install weasyprint
apt-get install -y fonts-noto-cjk
```

### 書類タイトル

**「支払通知書（仕入明細書）」** と明記すること（インボイス制度対応）。

### 必須記載項目

```
・書類タイトル：支払通知書（仕入明細書）
・発行者名・住所（自社情報）
・発行日
・対象月：○○年○月分
・施工店名・住所
・施工店インボイス登録番号（T + 12桁）
・明細テーブル：No. / 工事内容 / 施工日 / 金額（税抜） / 消費税(10%) / 金額（税込）
・小計（税抜合計）
・消費税合計（10%）
・税込合計
・振込予定日
・確認期限の注記：「本通知書の内容に相違がある場合は○営業日以内にご連絡ください。ご連絡がない場合は内容確認済みとみなします。」
```

---

## 発行UI仕様（frontend/index.html）

Webブラウザ上で動作するSPA。バニラJS（フレームワークなし）で実装。FastAPI の `/frontend` でStaticFilesとしてマウントする。社内ネットワークからブラウザでアクセスして使用する。

### 画面仕様

```
1. ページ読み込み時に対象月を自動で「前月」にセット（プルダウンで変更可）

2. 対象月が確定したら GET /api/contractors?month=YYYY-MM を叩いて施工店一覧を表示

3. 施工店一覧の各行
   ☑ 施工店名   件数: N件   合計: ¥XXX,XXX   [明細を見る ▼]
   ・デフォルト全チェック
   ・チェックを外すと合計から除外

4. [明細を見る ▼] クリックで案件明細を展開
   ☑ 案件名   施工日   ¥XX,XXX
   ・案件単位でチェックを外して除外可能
   ・チェックを外したとき除外理由ダイアログを表示
     - 理由: 来月持ち越し / 確認中 / 請求不要
     - メモ欄（任意）
   ・除外すると施工店の合計金額がリアルタイム再計算

5. 持ち越し案件には「⚠ 持ち越し」バッジを表示

6. 画面下部に「全選択」「全解除」ボタン

7. 「支払通知書を発行」ボタン
   → POST /api/notices/generate を叩く
   → 発行中はローディング表示
   → 完了後に結果一覧（成功/失敗）を表示
```

---

## 送付方法（api/services/sender.py）

施工店マスタの `send_method` フィールドで自動ルーティング。

| send_method | 処理 |
|---|---|
| email | Gmail SMTPでPDF添付メール送信 |
| line | LINE Messaging APIでPDFのDriveリンクを通知 |
| fax | 未実装（ログに「手動送付が必要」と出力してスキップ） |
| manual | PDFを `/root/project/sekouten_paymentsystem/output/` に保存してスキップ |

---

## Nginx設定（既存設定に追加）

```nginx
server {
    listen 443 ssl;
    server_name payment.l-stg.com;

    ssl_certificate     /etc/letsencrypt/live/payment.l-stg.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/payment.l-stg.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## systemd設定（FastAPI常時起動）

```ini
# systemd/contractor-api.service
[Unit]
Description=Contractor Payment Hub API
After=network.target

[Service]
User=root
WorkingDirectory=/root/project/sekouten_paymentsystem
ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8001
Restart=always
EnvironmentFile=/root/project/sekouten_paymentsystem/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# 有効化手順
cp systemd/contractor-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable contractor-api
systemctl start contractor-api

# 動作確認
systemctl status contractor-api
journalctl -u contractor-api -f
```

---

## requirements.txt

```
fastapi
uvicorn
python-dotenv
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
requests
weasyprint
line-bot-sdk
```

---

## マルチエージェント実装構成

このプロジェクトは4つのエージェントが並列で実装し、Orchestratorが統合する。
各エージェントはこのREADMEを共有コンテキストとして読み込んだ上で実装すること。

---

### Orchestrator（統合エージェント）

**役割**: 全エージェントの起動・進捗管理・統合・動作確認・調整

**起動手順**:

```bash
# 1. まずDBを初期化（全エージェントの前提）
python sync/db.py

# 2. 以下の4エージェントを並列起動
# Agent A: sync/
# Agent B: api/
# Agent C: services/（PDF生成・送付）
# Agent D: frontend/
```

**統合チェックリスト（全エージェント完了後に実施）**:

```
□ python sync/db.py → 4テーブルが作成されること
□ python sync/sync_contractor.py → SQLiteにデータが入ること
□ uvicorn api.main:app --port 8001 → 起動すること
□ GET /api/contractors?month=YYYY-MM → 施工店一覧が返ること
□ GET /api/contractors/{id}/cases?month=YYYY-MM → 案件明細が返ること
□ POST /api/notices/generate → PDFが生成されること
□ ブラウザで http://localhost:8001/frontend/ → UI が表示されること
□ 発行ボタン → PDF生成 + メール送信が実行されること
```

**統合時の調整ポイント**:
- Agent AのSQLiteスキーマとAgent BのDB参照が一致しているか確認
- Agent BのAPIレスポンス形式とAgent DのfetchコードのJSONキーが一致しているか確認
- Agent CのPDF生成関数のシグネチャとAgent Bの呼び出し方が一致しているか確認

---

### Agent A: 同期スクリプト（sync/）

**担当ディレクトリ**: `sync/`

**実装ファイルと順序**:

```
1. sync/db.py
   → SQLite接続・4テーブル作成・Upsert・クエリのユーティリティ関数
   → 完了確認: python sync/db.py でテーブルが作成されること

2. sync/sheets_client.py
   → Google Sheets APIのサービスアカウント認証
   → 3シート（基本情報・インボイス・振込先）の全件取得関数
   → 完了確認: 単体実行でスプシのデータがprintされること

3. sync/rakuraku_client.py
   → 楽楽販売APIの施工店マスタ GET/PATCH/POST
   → 完了確認: 単体実行でレコード一覧が取得できること

4. sync/sync_contractor.py
   → sheets_client → row_hashで差分検知 → SQLite Upsert → 楽楽販売同期
   → 完了確認: 実行後にSQLiteに正しくデータが入ること
```

**他エージェントへの提供インターフェース**:

```python
# Agent Bが使うDB参照関数（db.pyに実装すること）
get_contractor(contractor_id: str) -> dict
get_all_contractors() -> list[dict]
get_excluded_cases(month: str) -> list[dict]
upsert_excluded_case(case: dict) -> None
```

---

### Agent B: バックエンド（api/）

**担当ディレクトリ**: `api/`

**実装ファイルと順序**:

```
1. api/main.py
   → FastAPIアプリ初期化・ルーター登録・StaticFiles（/frontend）マウント
   → 完了確認: uvicorn api.main:app --port 8001 で起動すること

2. api/routers/contractors.py
   → GET /api/contractors?month=YYYY-MM
   → GET /api/contractors/{contractor_id}/cases?month=YYYY-MM
   → POST /api/cases/{case_id}/exclude
   → 楽楽販売APIから案件を取得してSQLiteの施工店マスタと結合

3. api/routers/notices.py
   → POST /api/notices/generate
   → GET /api/notices/{notice_id}/pdf
   → Agent C（notice_generator・sender）を呼び出す
```

**依存関係**:
- Agent AのDB関数（`sync/db.py`）をimportして使う
- Agent CのPDF生成・送付関数を呼び出す（関数シグネチャは下記参照）

**Agent Cへの期待インターフェース**:

```python
# api/services/notice_generator.py に実装されること
generate_notice_pdf(
    contractor: dict,      # 施工店マスタ情報
    cases: list[dict],     # 案件明細リスト
    month: str,            # 対象月 YYYY-MM
    output_path: str       # PDF保存先パス
) -> str                   # 生成したPDFのパスを返す

# api/services/sender.py に実装されること
send_notice(
    contractor: dict,      # 施工店マスタ情報（send_methodを参照）
    pdf_path: str,         # 送付するPDFのパス
    month: str             # 対象月
) -> bool                  # 送信成功/失敗
```

---

### Agent C: PDF生成・送付（api/services/）

**担当ディレクトリ**: `api/services/`

**実装ファイルと順序**:

```
1. api/services/notice_generator.py
   → WeasyPrintでHTML→PDF変換
   → 支払通知書（仕入明細書）のHTMLテンプレートを文字列で定義
   → インボイス番号バリデーション（^T\d{12}$）、なければエラーログ出してスキップ
   → 完了確認: 単体実行でサンプルPDFが生成されること

2. api/services/sender.py
   → send_methodに応じてメール/LINE/FAX/manualにルーティング
   → email: Gmail SMTPでPDF添付送信
   → line: LINE Messaging APIでDriveリンク通知
   → fax: ログ出力してスキップ（未実装）
   → manual: output/に保存してスキップ
   → 完了確認: emailでテスト送信できること
```

**Agent Bへの提供インターフェース**（上記Agent Bの期待シグネチャに合わせること）:

```python
generate_notice_pdf(contractor, cases, month, output_path) -> str
send_notice(contractor, pdf_path, month) -> bool
```

**PDF必須記載項目**（インボイス制度対応）:

```
・書類タイトル：支払通知書（仕入明細書）
・発行者名・住所（自社情報）・発行日・対象月
・施工店名・住所・インボイス登録番号
・明細テーブル：No./工事内容/施工日/金額(税抜)/消費税(10%)/金額(税込)
・小計・消費税合計・税込合計
・振込予定日・確認期限の注記
```

---

### Agent D: フロントエンド（frontend/）

**担当ディレクトリ**: `frontend/`

**実装ファイル**: `frontend/index.html`（バニラJS・CSS込み1ファイル）

**画面仕様**:

```
1. 対象月プルダウン（デフォルト: 前月）
   → 変更時に GET /api/contractors?month=YYYY-MM を叩いて施工店一覧を再描画

2. 施工店一覧（デフォルト全チェック）
   ☑ 施工店名   件数: N件   合計: ¥XXX,XXX   [明細 ▼]
   → チェックを外すと合計から除外

3. [明細 ▼] クリックで案件明細を展開
   ☑ 案件名   施工日   ¥XX,XXX
   → 案件チェックを外すと除外理由ダイアログを表示
     - 理由: 来月持ち越し / 確認中 / 請求不要
     - メモ欄（任意）
     - POST /api/cases/{case_id}/exclude を叩く
   → 除外すると施工店の合計をリアルタイム再計算

4. 持ち越し案件には「⚠ 持ち越し」バッジを表示

5. 「全選択」「全解除」ボタン

6. 「支払通知書を発行」ボタン
   → チェック済み施工店・除外案件IDを POST /api/notices/generate に送信
   → 発行中はローディング表示
   → 完了後に結果一覧（施工店名 / 成功・失敗）を表示
```

**依存関係**:
- Agent BのAPIが起動していること（`http://localhost:8001/api/`）
- fetchで同一オリジンのAPIを叩くだけなのでCORSは不要

---

## 注意事項

- 楽楽販売APIのオブジェクトID・フィールドIDは `.env` で管理し、ハードコードしないこと
- インボイス登録番号のバリデーション: `^T\d{12}$` の正規表現でチェック
- PDF生成時は必ず施工店インボイス番号が存在することを確認し、なければエラーログを出して該当施工店をスキップ
- Google Sheets APIの認証は サービスアカウントキー（credentials.json）を使うこと
- `.env` と `credentials.json` は `.gitignore` に必ず追加すること