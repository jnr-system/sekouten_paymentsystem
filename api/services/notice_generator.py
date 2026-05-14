from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
from datetime import date, timedelta
import calendar

from weasyprint import HTML

logger = logging.getLogger(__name__)

INVOICE_NUMBER_RE = re.compile(r"^T\d{12}$")

COMPANY_NAME = os.environ.get("COMPANY_NAME", "")
COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "")


def _next_month_end(month: str) -> str:
    year, mon = map(int, month.split("-"))
    if mon == 12:
        year += 1
        mon = 1
    else:
        mon += 1
    last_day = calendar.monthrange(year, mon)[1]
    return f"{year}年{mon}月{last_day}日"


def _month_label(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year}年{mon}月分"


def generate_notice_pdf(
    contractor: dict,
    cases: list,
    month: str,
    output_path: str,
) -> str:
    invoice_number = contractor.get("invoice_number", "")
    if not INVOICE_NUMBER_RE.match(invoice_number or ""):
        logger.error("インボイス登録番号が不正: contractor_id=%s, invoice_number=%s", contractor.get("contractor_id"), invoice_number)
        raise ValueError(f"インボイス登録番号が不正です: {invoice_number}")

    subtotal = sum(c.get("amount", 0) for c in cases)
    tax_total = sum(c.get("tax", 0) for c in cases)
    total = sum(c.get("amount_with_tax", 0) for c in cases)
    issue_date = date.today().strftime("%Y年%-m月%-d日") if os.name != "nt" else date.today().strftime("%Y年%#m月%#d日")
    payment_due = _next_month_end(month)
    month_label = _month_label(month)

    rows = ""
    for i, c in enumerate(cases, start=1):
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{c.get('case_name', '')}</td>
            <td>{c.get('construction_date', '')}</td>
            <td class="num">{c.get('amount', 0):,}</td>
            <td class="num">{c.get('tax', 0):,}</td>
            <td class="num">{c.get('amount_with_tax', 0):,}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP&display=swap');
  body {{ font-family: 'Noto Sans JP', sans-serif; font-size: 11pt; margin: 30px; }}
  h1 {{ text-align: center; font-size: 16pt; }}
  .header-block {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
  .issuer, .recipient {{ width: 48%; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
  th, td {{ border: 1px solid #333; padding: 4px 8px; }}
  th {{ background: #f0f0f0; text-align: center; }}
  .num {{ text-align: right; }}
  .summary {{ margin-top: 16px; text-align: right; }}
  .note {{ margin-top: 24px; font-size: 9pt; border: 1px solid #999; padding: 8px; }}
</style>
</head>
<body>
<h1>支払通知書（仕入明細書）</h1>
<div class="header-block">
  <div class="recipient">
    <p><strong>{contractor.get('name', '')} 御中</strong></p>
    <p>{contractor.get('postal_code', '')}</p>
    <p>{contractor.get('address', '')}</p>
    <p>インボイス登録番号: {invoice_number}</p>
  </div>
  <div class="issuer">
    <p>発行者: {COMPANY_NAME}</p>
    <p>{COMPANY_ADDRESS}</p>
    <p>発行日: {issue_date}</p>
    <p>対象月: {month_label}</p>
  </div>
</div>
<table>
  <thead>
    <tr>
      <th>No.</th>
      <th>工事内容</th>
      <th>施工日</th>
      <th>金額（税抜）</th>
      <th>消費税(10%)</th>
      <th>金額（税込）</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
<div class="summary">
  <p>小計（税抜合計）: {subtotal:,} 円</p>
  <p>消費税合計（10%）: {tax_total:,} 円</p>
  <p><strong>税込合計: {total:,} 円</strong></p>
  <p>振込予定日: {payment_due}</p>
</div>
<div class="note">
  本通知書の内容に相違がある場合は5営業日以内にご連絡ください。ご連絡がない場合は内容確認済みとみなします。
</div>
</body>
</html>"""

    HTML(string=html).write_pdf(output_path)
    return output_path
