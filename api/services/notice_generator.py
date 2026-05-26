from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
from datetime import date
from html import escape

import weasyprint
from weasyprint.text.fonts import FontConfiguration

logger = logging.getLogger(__name__)

INVOICE_NUMBER_RE = re.compile(r"^T\d{13}$")

COMPANY_NAME    = os.environ.get("COMPANY_NAME", "")
COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "")

# モジュールレベルでキャッシュ（起動時1回だけ初期化）
_font_config = FontConfiguration()
_css_font = weasyprint.CSS(string="""
@font-face {
    font-family: NotoJP;
    src: url('/usr/local/share/fonts/noto-jp/NotoSansJP.ttf');
}
""", font_config=_font_config)


def _next_month_end(month: str) -> str:
    year, mon = map(int, month.split("-"))
    mon += 1
    if mon > 12:
        year, mon = year + 1, 1
    return f"{year}年{mon}月末"


def _month_label(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year}年{mon}月分"


_CSS = """
@page {
    size: A4;
    margin: 18mm 20mm 18mm 20mm;
    @bottom-center {
        content: "- " counter(page) " -";
        font-family: NotoJP, sans-serif;
        font-size: 9pt;
        color: #1a3a5c;
    }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: NotoJP, sans-serif;
    font-size: 10pt;
    color: #1e1e1e;
    line-height: 1.5;
}
.issue-date { text-align: right; font-size: 10pt; margin-bottom: 4mm; }
.title { text-align: center; font-size: 18pt; font-weight: bold; margin-bottom: 6mm; }
.header { display: flex; gap: 10mm; margin-bottom: 5mm; }
.recipient { flex: 1; }
.recipient-name {
    font-size: 14pt; font-weight: bold; margin-bottom: 2mm;
    border-bottom: 1.5px solid #000; padding-bottom: 2mm;
}
.recipient-sub { font-size: 10pt; color: #334155; margin-top: 3mm; }
.issuer { flex: 1; font-size: 10pt; color: #334155; padding-top: 1mm; }
.notice-box { border: 1.5px solid #dc2626; margin-bottom: 4mm; }
.notice-title {
    background: #fff1f2; color: #dc2626; font-size: 10pt; font-weight: bold;
    padding: 5px 10px; border-bottom: 0.5px solid #fca5a5;
}
.notice-body { background: #fffbfb; font-size: 9pt; padding: 5px 10px; }
.bank-box { display: inline-block; border: 0.5px solid #1a3a5c; margin-bottom: 5mm; min-width: 80mm; }
.bank-title { background: #1a3a5c; color: #fff; font-size: 9pt; text-align: center; padding: 4px 8px; }
.bank-body { font-size: 10pt; padding: 5px 8px; line-height: 1.7; }
.summary-bar {
    display: flex; align-items: baseline; gap: 6mm;
    border-bottom: 1px solid #1a3a5c; padding-bottom: 6px; margin-bottom: 4mm;
}
.summary-label { font-size: 10pt; color: #475569; }
.summary-value { font-size: 15pt; font-weight: bold; color: #1a3a5c; }
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
thead th {
    background: #1a3a5c; color: #fff; padding: 6px; text-align: center;
    font-weight: bold; font-size: 10pt;
}
tbody tr { page-break-inside: avoid; break-inside: avoid; }
tbody tr:nth-child(even) td { background: #f8fafc; }
tbody td { padding: 6px; border: 0.5px solid #cbd5e1; vertical-align: middle; }
.col-no   { width: 8mm;  text-align: center; }
.col-arr  { width: 32mm; }
.col-work { width: 68mm; }
.col-date { width: 24mm; text-align: center; }
.col-amt  { width: 28mm; text-align: right; }
.foot-row { page-break-inside: avoid; }
.foot-row td { border: 0.5px solid #94a3b8; padding: 5px 8px; font-size: 10pt; }
.foot-row td:first-child { border: none; background: none; }
.foot-label { text-align: center; background: #e2e8f0; }
.foot-value { text-align: right; }
.foot-total td { font-weight: bold; }
"""


def generate_notice_pdf(contractor: dict, cases: list, month: str, output_path: str = None) -> bytes:
    invoice_number = contractor.get("invoice_number", "") or ""
    if invoice_number and not INVOICE_NUMBER_RE.match(invoice_number):
        logger.warning("インボイス登録番号が不正のためスキップ: %r", invoice_number)
        invoice_number = ""

    tax_total = sum(c.get("tax", 0) for c in cases)
    total     = sum(c.get("amount_with_tax", 0) for c in cases)

    issue_date  = date.today().strftime("%Y年%m月%d日")
    payment_due = _next_month_end(month)

    addr_parts = re.split(r'\s+', COMPANY_ADDRESS, maxsplit=2)
    issuer_addr_html = "<br>".join(escape(p) for p in addr_parts if p)

    postal = contractor.get("postal_code", "") or ""
    postal_html = f"〒{escape(postal)}<br>" if postal else ""
    address_html = escape(contractor.get("address", "") or "")
    invoice_html = (
        f"<br>インボイス登録番号: {escape(invoice_number)}"
        if invoice_number else "<br>免税事業者"
    )

    bank_name      = contractor.get("bank_name", "") or ""
    branch_name    = contractor.get("branch_name", "") or ""
    account_type   = contractor.get("account_type", "") or ""
    account_num    = contractor.get("account_number", "") or ""
    account_holder = contractor.get("account_holder", "") or ""
    bank_html = ""
    if any([bank_name, branch_name, account_num, account_holder]):
        bank_html = f"""
        <div class="bank-box">
          <div class="bank-title">振込先口座</div>
          <div class="bank-body">
            {escape(bank_name)}　{escape(branch_name)}<br>
            {escape(account_type)}　{escape(account_num)}<br>
            口座名義：{escape(account_holder)}
          </div>
        </div>
        """

    cases_sorted = sorted(cases, key=lambda c: (c.get("construction_date") or "", c.get("arrangement_number") or ""))
    rows_html = ""
    for i, c in enumerate(cases_sorted, start=1):
        work = escape(c.get("case_name_recipient", "") or "") + " 様"
        arr  = escape(c.get("arrangement_number", "") or "")
        dt   = escape(c.get("construction_date", "") or "")
        amt  = f"{c.get('amount_with_tax', 0):,}"
        rows_html += f"""
        <tr>
          <td class="col-no">{i}</td>
          <td class="col-arr">{arr}</td>
          <td class="col-work">{work}</td>
          <td class="col-date">{dt}</td>
          <td class="col-amt">{amt}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8">
<style>{_CSS}</style>
</head>
<body>
  <div class="issue-date">発行日: {escape(issue_date)}</div>
  <div class="title">支払通知書（仕入明細書）</div>

  <div class="header">
    <div class="recipient">
      <div class="recipient-name">{escape(contractor.get('name',''))} 御中</div>
      <div class="recipient-sub">
        {postal_html}{address_html}{invoice_html}
      </div>
    </div>
    <div class="issuer">
      発行者: {escape(COMPANY_NAME)}<br>
      {issuer_addr_html}
    </div>
  </div>

  <div class="notice-box">
    <div class="notice-title">【重要】内容確認のお願い</div>
    <div class="notice-body">
      本通知書の内容に相違がある場合は、<strong>発行日より5営業日以内</strong>に必ずご連絡ください。
      期日を過ぎた場合、内容をご確認いただいたものとみなし、記載金額にて振込処理を行います。
    </div>
  </div>

  {bank_html}

  <div class="summary-bar">
    <span class="summary-label">合計金額</span>
    <span class="summary-value">¥{total:,}　（税込）</span>
    <span class="summary-label" style="margin-left:8mm">お支払予定日：</span>
    <span class="summary-value">{escape(payment_due)}</span>
  </div>

  <table>
    <thead>
      <tr>
        <th class="col-no">No.</th>
        <th class="col-arr">手配番号</th>
        <th class="col-work">工事内容</th>
        <th class="col-date">施工日</th>
        <th class="col-amt">施工費（税込）</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
      <tr class="foot-row">
        <td colspan="3"></td>
        <td class="foot-label">消費税(10%)</td>
        <td class="foot-value">¥{tax_total:,}</td>
      </tr>
      <tr class="foot-row foot-total">
        <td colspan="3"></td>
        <td class="foot-label">合計金額</td>
        <td class="foot-value">¥{total:,}</td>
      </tr>
    </tbody>
  </table>
</body>
</html>"""

    pdf_bytes = weasyprint.HTML(string=html).write_pdf(
        font_config=_font_config,
        stylesheets=[_css_font],
    )
    logger.info("PDF生成完了: %s", contractor.get("name", ""))
    return pdf_bytes
