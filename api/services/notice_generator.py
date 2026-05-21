from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
import calendar
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

INVOICE_NUMBER_RE = re.compile(r"^T\d{13}$")

COMPANY_NAME    = os.environ.get("COMPANY_NAME", "")
COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "")

_FONT_REGISTERED = False

def _ensure_font():
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    for path in [r"C:\Windows\Fonts\msgothic.ttc", r"C:\Windows\Fonts\YuGothM.ttc", r"C:\Windows\Fonts\meiryo.ttc"]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("JaFont", path))
                _FONT_REGISTERED = True
                return
            except Exception:
                continue
    _FONT_REGISTERED = True

def _font():
    return "JaFont" if _FONT_REGISTERED and "JaFont" in pdfmetrics.getRegisteredFontNames() else "Helvetica"

def _next_month_end(month: str) -> str:
    year, mon = map(int, month.split("-"))
    if mon == 12:
        year, mon = year + 1, 1
    else:
        mon += 1
    return f"{year}年{mon}月末"

def _month_label(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year}年{mon}月分"


def generate_notice_pdf(contractor: dict, cases: list, month: str, output_path: str) -> str:
    invoice_number = contractor.get("invoice_number", "") or ""
    if invoice_number and not INVOICE_NUMBER_RE.match(invoice_number):
        logger.warning("インボイス登録番号が不正のためスキップ: %r", invoice_number)
        invoice_number = ""

    _ensure_font()
    fn = _font()

    tax_total = sum(c.get("tax", 0) for c in cases)
    total     = sum(c.get("amount_with_tax", 0) for c in cases)

    issue_date  = date.today().strftime("%Y年%m月%d日")
    payment_due = _next_month_end(month)
    month_label = _month_label(month)

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # ページ余白
    LM = RM = 20*mm
    PAGE_W = A4[0] - LM - RM  # 有効幅 = 170mm

    def _add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont(fn, 9)
        canvas.setFillColor(colors.HexColor("#1a3a5c"))
        page_num = canvas.getPageNumber()
        canvas.drawCentredString(A4[0] / 2, 12*mm, f"- {page_num} -")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    # ---- スタイル ----
    def ps(name, **kw):
        return ParagraphStyle(name, fontName=fn, **kw)

    title_style  = ps("title",  fontSize=20, alignment=1, spaceAfter=6)
    body_style   = ps("body",   fontSize=10, leading=16)
    small_style  = ps("small",  fontSize=8,  leading=13, textColor=colors.grey)

    story = []

    # ======== 発行日（右上） ========
    issue_row = Table(
        [["", Paragraph(f"発行日: {issue_date}", ps("ir", fontSize=10, alignment=2))]],
        colWidths=[85*mm, 85*mm],
    )
    issue_row.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.append(issue_row)
    story.append(Spacer(1, 2*mm))

    # ======== タイトル ========
    story.append(Paragraph("支払通知書（仕入明細書）", title_style))
    story.append(Spacer(1, 7*mm))

    # ======== 発行者・受取人ヘッダー ========
    postal = contractor.get('postal_code', '')
    postal_display = f"〒{postal}" if postal else ""
    import re as _re
    # 〒000-0000 都道府県市区町村番地 ビル名 → 3行に分割
    _addr_parts = _re.split(r'\s+', COMPANY_ADDRESS, maxsplit=2)
    issuer_address = "<br/>".join(_addr_parts)
    issuer_text = (
        f"発行者: {COMPANY_NAME}<br/>"
        f"{issuer_address}"
    )

    recipient_cell = Table(
        [
            [Paragraph(f"<b>{contractor.get('name', '')} 御中</b>", ps("rn", fontSize=14, leading=20))],
            [Paragraph(
                f"{postal_display}<br/>{contractor.get('address', '')}"
                + (f"<br/>インボイス登録番号: {invoice_number}" if invoice_number else ""),
                ps("rs", fontSize=11, leading=17),
            )],
        ],
        colWidths=[75*mm],
    )
    recipient_cell.setStyle(TableStyle([
        ("LINEBELOW",     (0,0), (0,0), 1.0, colors.black),
        ("BOTTOMPADDING", (0,0), (0,0), 4),
        ("TOPPADDING",    (0,0), (0,0), 2),
        ("TOPPADDING",    (0,1), (0,1), 4),
    ]))

    hdr = Table(
        [[recipient_cell, Paragraph(issuer_text, ps("it", fontSize=11, leading=17, leftIndent=20))]],
        colWidths=[85*mm, 85*mm],
    )
    hdr.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(hdr)
    story.append(Spacer(1, 5*mm))

    # ======== 注意書き ========
    notice_content = Table(
        [
            [Paragraph("【重要】内容確認のお願い", ps("nt", fontSize=10, textColor=colors.HexColor("#dc2626"), spaceAfter=3))],
            [Paragraph(
                "本通知書の内容に相違がある場合は、<b>発行日より5営業日以内</b>に必ずご連絡ください。"
                "期日を過ぎた場合、内容をご確認いただいたものとみなし、記載金額にて振込処理を行います。",
                ps("nb", fontSize=9, textColor=colors.HexColor("#1e1e1e"), leading=15),
            )],
        ],
        colWidths=[170*mm],
    )
    notice_content.setStyle(TableStyle([
        ("BOX",           (0,0), (-1,-1), 1.5, colors.HexColor("#dc2626")),
        ("LINEBELOW",     (0,0), (-1,0),  0.5, colors.HexColor("#fca5a5")),
        ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#fff1f2")),
        ("BACKGROUND",    (0,1), (-1,-1), colors.HexColor("#fffbfb")),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(notice_content)
    story.append(Spacer(1, 4*mm))

    # ======== 振込先口座 ========
    bank_name      = contractor.get("bank_name", "")
    branch_name    = contractor.get("branch_name", "")
    account_type   = contractor.get("account_type", "")
    account_num    = contractor.get("account_number", "")
    account_holder = contractor.get("account_holder", "")

    if any([bank_name, branch_name, account_num, account_holder]):
        bank_text = (
            f"{bank_name}　{branch_name}<br/>"
            f"{account_type}　{account_num}<br/>"
            f"口座名義：{account_holder}"
        )
        bank_inner = Table(
            [
                [Paragraph("振込先口座", ps("bl", fontSize=9, textColor=colors.white))],
                [Paragraph(bank_text,    ps("bb", fontSize=10, leading=17))],
            ],
            colWidths=[80*mm],
        )
        bank_inner.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1a3a5c")),
            ("ALIGN",         (0,0), (-1,0), "CENTER"),
            ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#1a3a5c")),
            ("LINEBELOW",     (0,0), (-1,0),  0.5, colors.HexColor("#1a3a5c")),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ]))
        bank_outer = Table([[bank_inner, ""]], colWidths=[85*mm, 85*mm])
        bank_outer.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
        story.append(bank_outer)
        story.append(Spacer(1, 5*mm))

    # ======== 合計バー（明細の上） ========
    bar_label = ps("bar_l", fontSize=10, textColor=colors.HexColor("#475569"))
    bar_value = ps("bar_v", fontSize=16, textColor=colors.HexColor("#1a3a5c"))

    top_bar = Table(
        [[
            Paragraph("合計金額", bar_label),
            Paragraph(f"¥{total:,}　（税込）", bar_value),
            Paragraph("お支払予定日：", bar_label),
            Paragraph(payment_due, bar_value),
        ]],
        colWidths=[22*mm, 78*mm, 28*mm, 42*mm],
    )
    top_bar.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW",     (0,0), (-1,-1), 0.8, colors.HexColor("#1a3a5c")),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 2),
        ("RIGHTPADDING",  (0,0), (-1,-1), 2),
    ]))
    story.append(top_bar)
    story.append(Spacer(1, 4*mm))

    # ======== 明細テーブル（消費税・合計行を末尾に統合） ========
    # 列幅: No.10 + 手配番号35 + 工事内容70 + 施工日27 + 施工費28 = 170mm
    COL_W = [10*mm, 35*mm, 70*mm, 27*mm, 28*mm]

    cases = sorted(cases, key=lambda c: c.get("construction_date") or "")

    cell_style = ps("cell", fontSize=11, leading=15, wordWrap="CJK", splitLongWords=1)

    detail_data = [["No.", "手配番号", "工事内容", "施工日", "施工費（税込）"]]
    for i, c in enumerate(cases, start=1):
        work_text = (
            c.get("case_name_recipient", "")
            + ("　" if c.get("case_name_recipient") else "")
            + c.get("case_name", "").lstrip("・").split("\t")[0]
            + "の交換工事"
        )
        num_style  = ps(f"num{i}",  fontSize=11, leading=15, alignment=1)
        date_style = ps(f"date{i}", fontSize=11, leading=15, alignment=1)
        amt_style  = ps(f"amt{i}",  fontSize=11, leading=15, alignment=2)
        detail_data.append([
            Paragraph(str(i), num_style),
            Paragraph(c.get("arrangement_number", ""), cell_style),
            Paragraph(work_text, cell_style),
            Paragraph(c.get("construction_date", ""), date_style),
            Paragraph(f"{c.get('amount_with_tax', 0):,}", amt_style),
        ])

    # 消費税・合計行を末尾に追加
    n_detail = len(detail_data)  # ヘッダー含む行数
    detail_data.append(["", "", "", "消費税(10%)", f"¥{tax_total:,}"])
    detail_data.append(["", "", "", "合計金額",    f"¥{total:,}"])
    n_tax_row   = n_detail      # 消費税行インデックス
    n_total_row = n_detail + 1  # 合計行インデックス

    detail_table = Table(detail_data, colWidths=COL_W, repeatRows=1)
    detail_table.setStyle(TableStyle([
        ("FONTNAME",       (0,0),  (-1,-1),           fn),
        ("FONTSIZE",       (0,0),  (-1,-1),           11),
        # ヘッダー行
        ("BACKGROUND",     (0,0),  (-1,0),            colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",      (0,0),  (-1,0),            colors.white),
        ("ALIGN",          (0,0),  (-1,0),            "CENTER"),
        # 明細行
        ("ALIGN",          (3,1),  (3,n_detail-1),    "CENTER"),
        ("ALIGN",          (4,1),  (4,n_detail-1),    "RIGHT"),
        ("GRID",           (0,0),  (-1,n_detail-1),   0.5, colors.grey),
        ("ROWBACKGROUNDS", (0,1),  (-1,n_detail-1),   [colors.white, colors.HexColor("#f8fafc")]),
        # 消費税行
        ("ALIGN",          (3,n_tax_row),   (3,n_tax_row),    "CENTER"),
        ("ALIGN",          (4,n_tax_row),   (4,n_tax_row),    "RIGHT"),
        ("BACKGROUND",     (3,n_tax_row),   (-1,n_tax_row),   colors.HexColor("#e2e8f0")),
        ("BOX",            (3,n_tax_row),   (-1,n_tax_row),   0.5, colors.HexColor("#94a3b8")),
        ("LINEBEFORE",     (4,n_tax_row),   (4,n_tax_row),    0.5, colors.HexColor("#94a3b8")),
        ("SPAN",           (0,n_tax_row),   (2,n_tax_row)),
        # 合計行
        ("ALIGN",          (3,n_total_row), (3,n_total_row),  "CENTER"),
        ("ALIGN",          (4,n_total_row), (4,n_total_row),  "RIGHT"),
        ("BACKGROUND",     (3,n_total_row), (-1,n_total_row), colors.white),
        ("BOX",            (3,n_total_row), (-1,n_total_row), 0.5, colors.HexColor("#94a3b8")),
        ("LINEBEFORE",     (4,n_total_row), (4,n_total_row),  0.5, colors.HexColor("#94a3b8")),
        ("FONTSIZE",       (3,n_total_row), (-1,n_total_row), 11),
        ("SPAN",           (0,n_total_row), (2,n_total_row)),
        ("VALIGN",         (0,0),  (-1,-1),           "MIDDLE"),
        # 共通パディング
        ("TOPPADDING",     (0,0),  (-1,-1),           4),
        ("BOTTOMPADDING",  (0,0),  (-1,-1),           4),
        ("LEFTPADDING",    (0,0),  (-1,-1),           4),
        ("RIGHTPADDING",   (0,0),  (-1,-1),           4),
        # 工事内容列は左右を広めに
        ("LEFTPADDING",    (2,0),  (2,-1),            8),
        ("RIGHTPADDING",   (2,0),  (2,-1),            8),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 6*mm))

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    logger.info("PDF生成完了: %s", output_path)
    return output_path
