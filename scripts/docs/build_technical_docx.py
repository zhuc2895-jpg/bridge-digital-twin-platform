# -*- coding: utf-8 -*-
"""Build a submission-ready technical DOCX for the bridge digital twin project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "assets" / "planning"
GEN_DIR = OUT_DIR / "generated"
OUTPUT = OUT_DIR / "桥梁数字孪生健康监测平台_技术文档_v1.1.docx"
SCREENSHOT = ROOT / "assets" / "screenshots" / "monitoring-session-1600.png"

FONT_CN = "微软雅黑"
FONT_BODY = "宋体"
FONT_EN = "Times New Roman"
FONT_MONO = "Consolas"

NAVY = "101820"
TEAL = "2D7D7A"
TEAL_LIGHT = "E7F3F2"
AMBER = "D79A2B"
AMBER_LIGHT = "FBF2E1"
INK = "25313A"
MUTED = "66727A"
LINE = "D9DFE3"
PAPER = "F7F8F8"
WHITE = "FFFFFF"


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        path = Path("C:/Windows/Fonts/consola.ttf")
    elif bold:
        path = Path("C:/Windows/Fonts/msyhbd.ttc")
    else:
        path = Path("C:/Windows/Fonts/msyh.ttc")
    return ImageFont.truetype(str(path), size=size)


def draw_round_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    radius: int = 24,
    width: int = 3,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=hex_rgb(fill), outline=hex_rgb(outline), width=width)


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = "9BA7AD",
    width: int = 6,
    head: int = 16,
) -> None:
    draw.line([start, end], fill=hex_rgb(color), width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 >= x1 else -1
        draw.polygon(
            [(x2, y2), (x2 - direction * head, y2 - head // 2), (x2 - direction * head, y2 + head // 2)],
            fill=hex_rgb(color),
        )
    else:
        direction = 1 if y2 >= y1 else -1
        draw.polygon(
            [(x2, y2), (x2 - head // 2, y2 - direction * head), (x2 + head // 2, y2 - direction * head)],
            fill=hex_rgb(color),
        )


def text_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    fill: str = INK,
    size: int = 24,
    bold: bool = False,
    spacing: int = 8,
) -> None:
    active_font = font(size, bold=bold)
    lines = text.split("\n")
    heights = [draw.textbbox((0, 0), line, font=active_font)[3] for line in lines]
    total = sum(heights) + spacing * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total) / 2
    for line, height in zip(lines, heights):
        width = draw.textbbox((0, 0), line, font=active_font)[2]
        draw.text(
            (box[0] + (box[2] - box[0] - width) / 2, y),
            line,
            font=active_font,
            fill=hex_rgb(fill),
        )
        y += height + spacing


def make_cover_banner(path: Path) -> None:
    width, height = 2400, 760
    image = Image.new("RGB", (width, height), hex_rgb(NAVY))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 100):
        draw.line([(x, 0), (x, height)], fill=hex_rgb("16222C"), width=1)
    for y in range(0, height, 100):
        draw.line([(0, y), (width, y)], fill=hex_rgb("16222C"), width=1)
    # Cable-stayed bridge line drawing on the right.
    deck_y = 470
    draw.line([(1180, deck_y), (2250, deck_y)], fill=hex_rgb("76908F"), width=7)
    for tower_x in (1540, 1950):
        draw.line([(tower_x, 170), (tower_x, deck_y + 120)], fill=hex_rgb("A7B8B7"), width=8)
        draw.line([(tower_x - 18, 220), (tower_x + 18, 220)], fill=hex_rgb("D5B574"), width=5)
    for anchor_x in (1250, 1370, 1450, 1620, 1720, 1810, 2030, 2110, 2190):
        top_x = 1540 if anchor_x < 1700 else 1950
        draw.line([(top_x, 235), (anchor_x, deck_y - 8)], fill=hex_rgb("6A8B89"), width=2)
    draw.line([(1170, deck_y + 120), (2260, deck_y + 120)], fill=hex_rgb("2D3B43"), width=3)
    for pier_x in (1420, 1770, 2120):
        draw.line([(pier_x, deck_y + 8), (pier_x, height - 30)], fill=hex_rgb("34434B"), width=12)
    draw.line([(110, 120), (760, 120)], fill=hex_rgb(AMBER), width=5)
    draw.text((112, 150), "HUIHE BRIDGE", font=font(62, bold=True), fill=hex_rgb(WHITE))
    draw.text((115, 235), "MONITOR OS", font=font(35, bold=False), fill=hex_rgb("9CC3C1"))
    draw.text((115, 330), "DIGITAL TWIN  /  STRUCTURAL HEALTH MONITORING", font=font(23), fill=hex_rgb("93A3A9"))
    draw.text((115, 390), "桥梁数字孪生结构健康监测平台", font=font(38, bold=True), fill=hex_rgb("DDE8E7"))
    draw.text((115, 500), "TECHNICAL DOCUMENT  ·  V1.1  ·  2026.11", font=font(22), fill=hex_rgb("D5B574"))
    image.save(path)


def make_architecture_diagram(path: Path) -> None:
    width, height = 2400, 1200
    image = Image.new("RGB", (width, height), hex_rgb("FBFCFC"))
    draw = ImageDraw.Draw(image)
    draw.text((100, 70), "端到端逻辑链路：从传感器数据到可解释决策", font=font(42, bold=True), fill=hex_rgb(NAVY))
    draw.text((102, 132), "规则与 AI 并行执行；第三层只在分歧或不确定性门控时介入。", font=font(24), fill=hex_rgb(MUTED))
    cards = [
        ("01", "接入校验", "JSON / CSV / 单条\n10,000 条整批原子"),
        ("02", "数据引擎", "最新值 / 滚动窗口\n全量历史 / Top-K"),
        ("03", "规则 + AI", "物理阈值底线\n三模型投票 + 仲裁"),
        ("04", "告警生命周期", "10 s 事件时间冷却\n统一来源与保留"),
        ("05", "10 KB Live Frame", "32 测点快照\n确定性降级"),
        ("06", "孪生表达", "3D / 回放 / 报告\nREST + WebSocket"),
    ]
    card_w, card_h, gap, start_x, y = 330, 230, 45, 80, 260
    for index, (number, title, detail) in enumerate(cards):
        x = start_x + index * (card_w + gap)
        fill = "FFFFFF" if index not in (2, 4) else TEAL_LIGHT
        outline = LINE if index not in (2, 4) else "8FC3BF"
        draw_round_box(draw, (x, y, x + card_w, y + card_h), fill=fill, outline=outline)
        draw.text((x + 24, y + 20), number, font=font(20, bold=True), fill=hex_rgb(TEAL))
        text_center(draw, (x + 10, y + 58, x + card_w - 10, y + 125), title, size=27, bold=True)
        text_center(draw, (x + 18, y + 135, x + card_w - 18, y + 215), detail, size=20, fill=MUTED, spacing=6)
        if index < len(cards) - 1:
            draw_arrow(draw, (x + card_w + 7, y + card_h // 2), (x + card_w + gap - 7, y + card_h // 2))
    # Supporting planes.
    draw_round_box(draw, (80, 600, 810, 760), fill=AMBER_LIGHT, outline="E6C98E", radius=20, width=2)
    text_center(draw, (110, 620, 780, 740), "Bridge Scene Profile\n模型变换 · 桥面边界 · 测点锚点 · 图表角色", size=24, fill="684B18", spacing=8)
    draw_arrow(draw, (810, 680), (2155, 680), color="C8A655", width=4, head=12)
    draw_arrow(draw, (2155, 680), (2155, 500), color="C8A655", width=4, head=12)
    draw_round_box(draw, (850, 600, 1570, 760), fill=TEAL_LIGHT, outline="9CCAC6", radius=20, width=2)
    text_center(draw, (880, 620, 1540, 740), "原子检查点\n导出完整状态 · fsync · os.replace", size=24, fill="1F5F5D", spacing=8)
    draw_arrow(draw, (930, 600), (930, 500), color="5EA6A1", width=4, head=12)
    draw_round_box(draw, (1610, 600, 2320, 760), fill="EFF2F3", outline=LINE, radius=20, width=2)
    text_center(draw, (1640, 620, 2290, 740), "可追溯分析\n补偿估计 · 模态反演 · HTML 报告", size=24, fill=INK, spacing=8)
    draw_arrow(draw, (1750, 600), (1750, 500), color="9BA7AD", width=4, head=12)
    draw.text((80, 850), "实现原则：实时性来自有界数据结构和固定预算；可解释性来自统一证据字段；可恢复性来自原子状态边界。", font=font(22), fill=hex_rgb(MUTED))
    image.save(path)


def make_detection_diagram(path: Path) -> None:
    width, height = 2400, 1350
    image = Image.new("RGB", (width, height), hex_rgb("FBFCFC"))
    draw = ImageDraw.Draw(image)
    draw.text((100, 60), "三层检测：规则守底线，AI 找未知，仲裁管分歧", font=font(42, bold=True), fill=hex_rgb(NAVY))
    draw.text((102, 122), "第三层不处理所有读数，只处理模型分歧、低认知或高不确定性样本。", font=font(24), fill=hex_rgb(MUTED))
    bands = [
        (220, 260, "01", "物理阈值规则", "确定性安全底线", TEAL_LIGHT, "8FC3BF", TEAL),
        (540, 330, "02", "三模型投票", "独立基线 + 置信度门槛 + 至少两票", "FFF8EA", "E6C98E", "8A6219"),
        (920, 300, "03", "特征 / 空间仲裁", "均值漂移 · 方差变化 · 趋势斜率 · 空间残差", "EDF1F3", LINE, INK),
    ]
    for y, h, number, title, subtitle, fill, outline, color in bands:
        draw_round_box(draw, (100, y, 2300, y + h), fill=fill, outline=outline, radius=26, width=3)
        draw.text((135, y + 30), number, font=font(28, bold=True), fill=hex_rgb(color))
        draw.text((220, y + 28), title, font=font(34, bold=True), fill=hex_rgb(color))
        draw.text((220, y + 80), subtitle, font=font(23), fill=hex_rgb(MUTED))
    # Layer 1 chips.
    for index, (label, detail) in enumerate([
        ("红 / 橙 / 黄", "按绝对值降级匹配"),
        ("统一告警入口", "快照 + 冷却 + 50k 保留"),
        ("规则兜底", "AI 故障仍保留确定性告警"),
    ]):
        x = 220 + index * 650
        draw_round_box(draw, (x, 360, x + 590, 455), fill=WHITE, outline="B9D9D6", radius=16, width=2)
        draw.text((x + 24, 374), label, font=font(23, bold=True), fill=hex_rgb(INK))
        draw.text((x + 24, 412), detail, font=font(19), fill=hex_rgb(MUTED))
    # Layer 2 model chips.
    models = [
        ("STALWART-inspired", "快慢 EMA 突变"),
        ("GAN-AE", "重构误差 + 8 子模型"),
        ("Isolation Forest", "滚动窗口离群"),
    ]
    for index, (name, detail) in enumerate(models):
        x = 220 + index * 650
        draw_round_box(draw, (x, 680, x + 590, 800), fill=WHITE, outline="E2C999", radius=16, width=2)
        draw.text((x + 24, 696), name, font=font(24, bold=True), fill=hex_rgb(INK))
        draw.text((x + 24, 742), detail, font=font(20), fill=hex_rgb(MUTED))
    # Layer 3 chips.
    features = [
        ("均值漂移", "近期均值 / 历史尺度"),
        ("方差变化", "波动结构是否改变"),
        ("趋势斜率", "持续恶化 vs 瞬时跳变"),
        ("空间残差", "孤立坏点 vs 协同响应"),
    ]
    for index, (name, detail) in enumerate(features):
        x = 220 + index * 500
        draw_round_box(draw, (x, 1040, x + 450, 1160), fill=WHITE, outline="CCD5D9", radius=16, width=2)
        draw.text((x + 20, 1054), name, font=font(23, bold=True), fill=hex_rgb(INK))
        draw.text((x + 20, 1097), detail, font=font(18), fill=hex_rgb(MUTED))
    draw_arrow(draw, (1200, 480), (1200, 540), color="9BA7AD", width=5, head=12)
    draw_arrow(draw, (1200, 870), (1200, 920), color="9BA7AD", width=5, head=12)
    draw.text((1218, 490), "并行安全网", font=font(19), fill=hex_rgb(MUTED))
    draw.text((1218, 875), "≥2 票且置信度 ≥0.7；低认知 / 高不确定性进入仲裁", font=font(19), fill=hex_rgb(MUTED))
    draw.text((100, 1250), "输出证据：模型投票、置信度、认知度、不确定性、特征超限项、空间状态、阈值版本。", font=font(21), fill=hex_rgb(MUTED))
    image.save(path)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_margins(cell, top: int = 90, start: int = 120, bottom: int = 90, end: int = 120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tc_pr.append(margins)


def set_table_borders(table, color: str = LINE, size: int = 4) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)
        borders.append(node)
    tbl_pr.append(borders)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def set_run_font(run, *, name: str, east_asia: str, size: float, bold: bool = False, color: str = INK) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(*hex_rgb(color))


def style_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.7)
    section.right_margin = Cm(2.5)
    section.header_distance = Cm(1.1)
    section.footer_distance = Cm(1.0)
    section.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = FONT_EN
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(*hex_rgb(INK))
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(5)

    heading_specs = {
        "Heading 1": (16, NAVY, 18, 9),
        "Heading 2": (13.5, TEAL, 14, 6),
        "Heading 3": (11.5, INK, 10, 4),
    }
    for style_name, (size, color, before, after) in heading_specs.items():
        style = doc.styles[style_name]
        style.font.name = FONT_CN
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(*hex_rgb(color))
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for style_name in ("List Bullet", "List Number"):
        style = doc.styles[style_name]
        style.font.name = FONT_EN
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
        style.font.size = Pt(10.5)
        style.paragraph_format.line_spacing = 1.4
        style.paragraph_format.space_after = Pt(3)

    settings = doc.settings.element
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.append(update_fields)


def add_field(paragraph, instruction: str, placeholder: str = "1") -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(separate)
    run._r.append(text)
    run._r.append(end)
    set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)


def add_bottom_border(paragraph, color: str = LINE, size: int = 6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def configure_header_footer(doc: Document) -> None:
    section = doc.sections[0]
    header = section.header
    paragraph = header.paragraphs[0]
    table = header.add_table(rows=1, cols=2, width=Cm(15.8))
    paragraph._p.addprevious(table._tbl)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Cm(9.0)
    table.columns[1].width = Cm(6.8)
    left_cell, right_cell = table.rows[0].cells
    left_cell.width = Cm(9.0)
    right_cell.width = Cm(6.8)
    left_p = left_cell.paragraphs[0]
    left_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    left_p.paragraph_format.space_after = Pt(0)
    left = left_p.add_run("桥梁数字孪生结构健康监测平台  ·  技术文档")
    set_run_font(left, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)
    right_p = right_cell.paragraphs[0]
    right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_p.paragraph_format.space_after = Pt(0)
    right = right_p.add_run("TECHNICAL DOCUMENT  /  V1.1")
    set_run_font(right, name=FONT_EN, east_asia=FONT_CN, size=8.5, color="8A969D")
    paragraph.add_run("")
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(1)
    add_bottom_border(paragraph)

    footer = section.footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("第 ")
    set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)
    add_field(paragraph, "PAGE")
    run = paragraph.add_run(" 页  /  共 ")
    set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)
    add_field(paragraph, "NUMPAGES")
    run = paragraph.add_run(" 页")
    set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)


def body_paragraph(doc: Document, text: str, *, bold_lead: str | None = None, first_indent: bool = True) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Pt(21)
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.space_after = Pt(5)
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        set_run_font(lead, name=FONT_EN, east_asia=FONT_BODY, size=10.5, bold=True, color=INK)
        rest = paragraph.add_run(text[len(bold_lead) :])
        set_run_font(rest, name=FONT_EN, east_asia=FONT_BODY, size=10.5, color=INK)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=10.5, color=INK)


def bullet_list(doc: Document, items: Iterable[str]) -> None:
    for item in items:
        paragraph = doc.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.left_indent = Pt(18)
        paragraph.paragraph_format.first_line_indent = Pt(-12)
        run = paragraph.add_run(item)
        set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=10.5, color=INK)


def add_caption(doc: Document, text: str, *, kind: str = "图") -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(9)
    run = paragraph.add_run(text)
    set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, color=MUTED)


def add_figure(doc: Document, path: Path, caption: str, *, width_cm: float = 16.0) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.add_run().add_picture(str(path), width=Cm(width_cm))
    add_caption(doc, caption)


def add_table(
    doc: Document,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    caption: str | None = None,
    widths_cm: Sequence[float] | None = None,
    font_size: float = 9.2,
) -> None:
    if caption:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(caption)
        set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=9, bold=True, color=TEAL)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    set_table_borders(table)
    header = table.rows[0]
    prevent_row_split(header)
    for index, label in enumerate(headers):
        cell = header.cells[index]
        set_cell_shading(cell, NAVY)
        set_cell_margins(cell)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(label)
        set_run_font(run, name=FONT_EN, east_asia=FONT_CN, size=font_size, bold=True, color=WHITE)
        if widths_cm:
            cell.width = Cm(widths_cm[index])
    for row_index, values in enumerate(rows):
        row = table.add_row()
        prevent_row_split(row)
        for index, value in enumerate(values):
            cell = row.cells[index]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_margins(cell)
            if row_index % 2 == 1:
                set_cell_shading(cell, "F3F6F6")
            paragraph = cell.paragraphs[0]
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.LEFT
                if index == 0 or len(str(value)) > 16
                else WD_ALIGN_PARAGRAPH.CENTER
            )
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run(str(value))
            set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=font_size, color=INK)
            if widths_cm:
                cell.width = Cm(widths_cm[index])
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(3)


def add_code_block(doc: Document, code: str) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, color="DDE4E6", size=3)
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F4F7F7")
    set_cell_margins(cell, top=120, bottom=120, start=160, end=160)
    cell.paragraphs[0].text = ""
    lines = code.strip("\n").splitlines()
    for index, line in enumerate(lines):
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.12
        run = paragraph.add_run(line if line else " ")
        set_run_font(run, name=FONT_MONO, east_asia=FONT_CN, size=8.5, color="2C3A42")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def page_break(doc: Document) -> None:
    doc.add_page_break()


def add_heading(doc: Document, text: str, level: int) -> None:
    paragraph = doc.add_heading(level=level)
    run = paragraph.add_run(text)
    size = {1: 16, 2: 13.5, 3: 11.5}[level]
    color = {1: NAVY, 2: TEAL, 3: INK}[level]
    set_run_font(run, name=FONT_CN, east_asia=FONT_CN, size=size, bold=True, color=color)
    if level == 1:
        paragraph.paragraph_format.page_break_before = False


def add_toc(doc: Document) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-2" \\h \\z \\u '
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "目录将在 Word 打开后自动更新。"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, text, end])
    set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=10.5, color=MUTED)


def add_cover(doc: Document, banner: Path) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_picture(str(banner), width=Cm(16.0))
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(30)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("桥梁数字孪生结构健康监测平台")
    set_run_font(run, name=FONT_CN, east_asia=FONT_CN, size=30, bold=True, color=NAVY)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(25)
    run = paragraph.add_run("技术文档")
    set_run_font(run, name=FONT_CN, east_asia=FONT_CN, size=20, bold=False, color=TEAL)

    info = [
        ("文档版本", "V1.1"),
        ("更新日期", "2026-11-03"),
        ("文件性质", "工程技术文档 / 竞赛答辩支撑材料"),
        ("适用范围", "项目介绍、技术评审、答辩与后续工程化评审"),
        ("文档状态", "与当前仓库实现及验收产物一致"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, color="E3E8EA", size=3)
    for label, value in info:
        row = table.add_row()
        row.cells[0].width = Cm(4.0)
        row.cells[1].width = Cm(9.5)
        for cell in row.cells:
            set_cell_margins(cell, top=120, bottom=120)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_shading(row.cells[0], "F0F5F5")
        p0 = row.cells[0].paragraphs[0]
        r0 = p0.add_run(label)
        set_run_font(r0, name=FONT_EN, east_asia=FONT_CN, size=9.5, bold=True, color=TEAL)
        p1 = row.cells[1].paragraphs[0]
        r1 = p1.add_run(value)
        set_run_font(r1, name=FONT_EN, east_asia=FONT_BODY, size=9.5, color=INK)
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(50)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("本文件依据仓库当前实现、自动化测试和验收记录编写。")
    set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=9, color=MUTED)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("数据边界、合成数据定位与工程限制见第 8、9 章。")
    set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=9, color=MUTED)


# CONTENT_PART_2


def build_document() -> Document:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    banner = GEN_DIR / "technical_doc_banner.png"
    architecture = GEN_DIR / "technical_architecture.png"
    detection = GEN_DIR / "technical_detection_layers.png"
    make_cover_banner(banner)
    make_architecture_diagram(architecture)
    make_detection_diagram(detection)

    doc = Document()
    style_document(doc)
    configure_header_footer(doc)
    doc.core_properties.title = "桥梁数字孪生结构健康监测平台技术文档"
    doc.core_properties.subject = "数字孪生、结构健康监测、异常检测、工程软件"
    doc.core_properties.author = "Bridge Digital Twin Platform"
    doc.core_properties.keywords = "桥梁监测, 数字孪生, SHM, 异常检测, FastAPI, Three.js"

    add_cover(doc, banner)
    page_break(doc)

    add_heading(doc, "文档控制与摘要", 1)
    add_table(
        doc,
        ["项目", "内容"],
        [
            ["文档名称", "桥梁数字孪生结构健康监测平台技术文档"],
            ["文档版本", "V1.1"],
            ["更新时间", "2026-11-03"],
            ["对应代码版本", "仓库当前工作区：README、backend、frontend、benchmarks"],
            ["数据边界", "合成验证集 + 公开 VBA 录音级基准；不代表真实桥梁工程精度"],
            ["阈值定位", "competition-design-basis-v1 / provisional"],
            ["适用场景", "工程场景数字化竞赛、技术答辩、工程化评审"],
        ],
        caption="表 1  文档控制信息",
        widths_cm=[3.6, 12.0],
    )
    body_paragraph(
        doc,
        "本文档描述一套面向大跨径桥梁运维的数字孪生结构健康监测平台。系统把传感器读数、物理阈值、三层异常检测、三维模型和统一告警生命周期放在同一条运行链路里，最终落到结构状态、告警记录和处置材料。",
    )
    body_paragraph(
        doc,
        "平台采用前后端分离架构。后端以 FastAPI 为服务入口，负责数据校验、内存数据引擎、阈值状态投影、规则与 AI 检测、告警生命周期、原子检查点、WebSocket 实时帧和分析接口；前端以 Vue 3、Three.js 和 ECharts 构建单屏监控台，完成三维桥梁、测点状态、响应云图、趋势曲线、历史回放与报告展示。",
    )
    body_paragraph(
        doc,
        "为便于判断结论适用范围，本文分别说明代码实际做到什么、验收中测到什么、哪些还不能证明。合成验证集用于检查行为和可复现性，VBA 基准用于检查录音级融合分类；两者都不能替代真实桥梁现场标定。",
    )
    add_heading(doc, "目标读者", 2)
    bullet_list(
        doc,
        [
            "桥梁运维与结构工程师：关注状态投影、阈值依据、响应场与分析边界。",
            "软件与算法研发人员：关注模块边界、数据合同、检测器扩展和复现方式。",
            "竞赛评审与答辩人员：关注问题定义、工程链路、技术优势、验收证据和风险。",
        ],
    )
    page_break(doc)
    add_table(
        doc,
        ["核心问题", "平台回答"],
        [
            ["状态是否直观", "3D 桥梁、测点颜色、响应云图与趋势同屏联动"],
            ["异常是否可信", "规则 + 三模型投票 + 不确定性门控 + 特征/空间仲裁"],
            ["结果是否可解释", "保存投票、置信度、特征超限项、空间证据和阈值快照"],
            ["实时是否稳定", "单实时循环、10 KB 有界帧、慢客户端隔离"],
            ["能否持续运行", "原子检查点、损坏容忍、健康检查与降级"],
            ["结论能否复现", "384 项测试、系统验收、VBA 基准、固定命令和产物"],
        ],
        caption="表 2  平台核心问题与回答",
        widths_cm=[4.2, 11.4],
    )
    add_heading(doc, "阅读指引", 2)
    bullet_list(
        doc,
        [
            "关注架构与逻辑链路时，优先阅读第 2、3 章。",
            "关注算法可信度与创新点时，优先阅读第 4、7 章。",
            "关注验收数据与答辩风险时，优先阅读第 8、9 章。",
            "本文所有定量指标均应结合数据来源、运行环境和工程边界一起理解。",
        ],
    )
    add_table(
        doc,
        ["关键指标", "当前结果", "口径"],
        [
            ["后端自动化测试", "384 passed", "pytest 全量"],
            ["10,000 条批量摄入", "393.76 ms", "本机单进程"],
            ["三层检测 p95", "11.45 ms", "150 条基线后单条"],
            ["API 吞吐", "152.65 QPS", "本机回环负载"],
            ["合成验证集", "准确率 0.9924 / 误报 0.0023", "24 h 合成数据"],
            ["VBA 融合基准", "准确率 0.9706 / 误报 0.0278", "录音级离线分类"],
        ],
        caption="关键指标速览（详细口径见第 8 章）",
        widths_cm=[4.0, 6.0, 5.4],
        font_size=8.6,
    )
    page_break(doc)

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(12)
    run = paragraph.add_run("目  录")
    set_run_font(run, name=FONT_CN, east_asia=FONT_CN, size=18, bold=True, color=NAVY)
    add_toc(doc)
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(14)
    alignment = paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("提示：目录域已设置自动更新；提交前可在 Word 中按 Ctrl+A、F9 再次刷新。")
    set_run_font(run, name=FONT_EN, east_asia=FONT_BODY, size=9, color=MUTED)
    page_break(doc)

    # ------------------------------------------------------------------
    # 1. Project definition
    # ------------------------------------------------------------------
    add_heading(doc, "1  项目定义与目标", 1)
    add_heading(doc, "1.1  工程问题", 2)
    body_paragraph(
        doc,
        "传统桥梁运维通常依赖定期人工巡检、离线检测和单点阈值报警。对于大跨径斜拉桥，这种模式容易出现响应滞后、数据割裂、误报漏报并存和结果难解释等问题。现场读数已经很多，缺的是从读数到结构状态、再到运维决策的连续链路。",
    )
    bullet_list(
        doc,
        [
            "响应滞后：异常从出现到被发现可能跨越数天，难以支撑及时处置。",
            "数据割裂：应变、位移、加速度、温度数据缺少统一语义和空间解释。",
            "误报漏报：单点固定阈值无法区分噪声、传感器漂移和真实结构响应。",
            "结果难解释：只有“报警/不报警”，缺少模型证据、空间证据和阈值来源。",
        ],
    )
    body_paragraph(
        doc,
        "本项目以主跨 120 m 的斜拉桥演示场景为对象，构建从传感器数据到结构状态、分级预警和处置证据的工程软件原型。系统不替代有限元分析或持证工程师判断，负责把监测数据的实时组织、异常证据和历史查询做成可运行服务。",
    )

    add_heading(doc, "1.2  设计目标", 2)
    add_table(
        doc,
        ["目标", "实现方式", "可验证证据"],
        [
            ["实时感知", "1 Hz 仿真或外部数据流，WebSocket 推送", "10 个客户端同时接收，帧延迟 p95 9.10 ms"],
            ["分级预警", "黄/橙/红物理阈值 + AI 告警", "统一告警生命周期与 10 s 事件时间冷却"],
            ["降低误报", "多模型投票、认知/不确定性门控、空间残差", "合成验证集误报率 0.0023"],
            ["可解释", "模型投票、置信度、特征证据、阈值快照", "告警与分析接口返回完整诊断字段"],
            ["三维映射", "Bridge Scene Profile 统一空间语义", "3D、图表、压力场消费同一 profile revision"],
            ["历史追溯", "时间范围查询、时刻快照、1x–16x 回放、HTML 报告", "REST + 前端回放 + 报告接口"],
            ["可复现", "pytest、系统验收、VBA 基准、数据哈希", "384 项测试通过；验收命令与产物固定"],
        ],
        caption="表 3  设计目标与验证方式",
        widths_cm=[2.8, 7.2, 5.6],
        font_size=8.8,
    )

    add_heading(doc, "1.3  当前版本的非目标与边界", 2)
    bullet_list(
        doc,
        [
            "不把竞赛设计阈值宣称为正式工程限值；当前阈值档案为 provisional。",
            "不把合成数据精度宣称为真实桥梁工程精度。",
            "不把 VBA 录音级融合结果宣称为线上逐读数精度或应力/位移预测精度。",
            "当前版本不包含正式身份认证、RBAC、租户隔离、工单审批和云端多租户计费。",
            "当前版本不替代有限元分析、桥梁设计验算和持证工程师判断。",
        ],
    )
    body_paragraph(
        doc,
        "这些边界属于系统设计的一部分。把已经做到的能力和暂时不能证明的内容分开，评审与后续部署才能有正确预期。",
    )

    # ------------------------------------------------------------------
    # 2. Architecture
    # ------------------------------------------------------------------
    add_heading(doc, "2  系统总体架构", 1)
    add_figure(doc, architecture, "图 1  端到端逻辑链路与支撑边界", width_cm=16.0)
    add_heading(doc, "2.1  系统上下文", 2)
    body_paragraph(
        doc,
        "系统的外部参与者包括传感器/仿真器、运维人员、桥梁模型文件以及标定与模态数据。传感器提供带时间戳的应变、位移、加速度和温度读数；运维人员通过浏览器或桌面壳查看状态、回放历史和导出报告；模型文件决定三维桥梁与测点空间解释；标定/模态数据支撑补偿估计和全场变形反演。",
    )
    add_table(
        doc,
        ["运行形态", "组成", "适用场景"],
        [
            ["前后端分离开发", "FastAPI:8000 + Vite:5173，代理 /api 与 /ws", "开发、联调、演示"],
            ["单进程 Web", "FastAPI 托管 frontend/dist，/app 为入口", "内网部署、答辩现场"],
            ["Windows 桌面", "PyInstaller + pywebview，自动选择空闲回环端口", "无网络或单机演示"],
            ["Docker 后端", "容器暴露 REST/WS，状态卷持久化", "轻量服务器部署"],
        ],
        caption="表 4  系统运行形态",
        widths_cm=[3.4, 8.4, 4.2],
        font_size=8.8,
    )

    add_heading(doc, "2.2  技术栈", 2)
    add_table(
        doc,
        ["层次", "技术选型", "职责"],
        [
            ["前端", "Vue 3、TypeScript、Vite", "单屏监控台、实时/回放状态编排"],
            ["3D", "Three.js、glTF 2.0", "桥梁模型、测点、构件高亮、压力场贴图"],
            ["图表", "ECharts", "实时趋势、历史曲线"],
            ["后端", "FastAPI、Pydantic、Uvicorn", "REST、WebSocket、服务装配"],
            ["数据与算法", "NumPy、scikit-learn", "内存引擎、检测、补偿、模态反演"],
            ["测试", "pytest、httpx、websockets", "单元、接口、性能和实时验收"],
            ["部署", "Docker、PyInstaller、pywebview", "容器后端、Windows 单机应用"],
        ],
        caption="表 5  技术栈与职责",
        widths_cm=[3.0, 5.4, 7.2],
        font_size=8.8,
    )

    add_heading(doc, "2.3  模块职责", 2)
    add_table(
        doc,
        ["模块", "职责", "关键约束"],
        [
            ["ingestion.py", "JSON/CSV 完整校验", "最多 10,000 条；单条非法整批拒绝"],
            ["engine/data_engine.py", "摄入、历史、阈值、告警、投影", "滚动窗口 + 全量历史 + 时间索引"],
            ["processing.py", "摄入→规则→AI→持久化编排", "AI 异常不阻断规则告警"],
            ["ml/", "检测、投票、仲裁、补偿、模态", "检测器失败隔离；统一 DetectionResult"],
            ["live_stream.py", "进程级 1 Hz 实时循环", "单循环，避免每连接重复生成"],
            ["live_contract.py", "Live Frame 合同与预算", "10 KB 上限与固定降级顺序"],
            ["bridge_models.py", "GLB/glTF 导入、激活、profile revision", "100 MB 上限；自包含资源"],
            ["persistence.py", "原子检查点", "fsync + os.replace；损坏可忽略"],
        ],
        caption="表 6  后端模块职责",
        widths_cm=[4.0, 7.4, 4.0],
        font_size=8.6,
    )

    # ------------------------------------------------------------------
    # 3. End-to-end chain
    # ------------------------------------------------------------------
    add_heading(doc, "3  端到端逻辑链路", 1)
    add_heading(doc, "3.1  实时数据链", 2)
    body_paragraph(
        doc,
        "实时数据由内置仿真器或外部 REST 接口进入系统。每条记录必须包含 sensor_id、name、type、value 和 timestamp，类型仅允许 strain、displacement、acceleration、temperature。批次在写入状态前完整校验，避免“前一半成功、后一半失败”的部分写入。",
    )
    add_code_block(
        doc,
        """
仿真器 / 外部 JSON·CSV
  → 字段与类型校验
  → SensorBatch(records, live_eligibility)
  → MonitoringEngine.ingest
  → 物理阈值告警 + 三层 AI 检测
  → 统一告警生命周期
  → Live Sensor Snapshot（最多 32 测点）
  → 归一化响应场 + 10 KB Live Frame
  → WebSocket 广播
  → 3D 测点 / 趋势 / 云图 / 告警面板
""",
    )
    body_paragraph(
        doc,
        "引擎为每个测点维护最新值、实时最新值、500 条滚动窗口、最多 100,000 条完整历史、独立时间戳数组和 Top-K 峰值。最新值查询为字典 O(1)，滚动窗口使用 deque，时间查询使用二分查找，Top-K 使用堆。",
    )

    add_heading(doc, "3.2  物理状态与阈值投影", 2)
    body_paragraph(
        doc,
        "服务器按当前 Threshold Profile 和可选逐测点 override 生成物理状态，前端不重复计算阈值。物理状态只取 normal、yellow、orange、red、unknown；连接状态独立取 online 或 offline。未来时间戳、阈值缺失、阈值不完整或 override 类型不匹配时，物理状态为 unknown，不默认成正常。",
    )
    add_code_block(
        doc,
        """
level = 满足 |value| >= threshold 的最高告警等级
ratio = min(|value| / red_threshold, 1.25)
""",
    )

    add_heading(doc, "3.3  统一告警生命周期", 2)
    body_paragraph(
        doc,
        "规则告警和 AI 告警都通过 submit_alert() 进入统一生命周期。该边界负责 UUID、来源校验、传感器名称与阈值快照、事件时间冷却、全局保留和稳定排序。相同传感器、相同等级在 10 秒事件时间窗口内只保留一次；同一时刻的告警通过单调检测序号稳定排序。",
    )
    add_table(
        doc,
        ["字段/策略", "说明"],
        [
            ["来源", "rule、ai_stalwart、ai_gan_ae、ai_isolation_forest、ai_dual_confirm、ai_feature_arbitration"],
            ["等级", "yellow / orange / red，从低到高"],
            ["快照", "创建告警时保存传感器名称和阈值，后续阈值修改不篡改历史"],
            ["冷却", "按传感器+等级，以事件时间为基准 10 秒"],
            ["保留", "按事件时间全局保留最新 50,000 条"],
            ["事件时间", "触发告警的读数时间，不是入库时间"],
        ],
        caption="表 7  告警生命周期合同",
        widths_cm=[4.2, 11.2],
        font_size=8.8,
    )

    add_heading(doc, "3.4  实时帧、慢客户端与前端", 2)
    body_paragraph(
        doc,
        "LiveTickPipeline 每个周期生成或读取仿真帧，跳过尚待消费的外部同测点数据，完成摄入、规则、AI 和持久化；随后读取最多 32 个 Live Eligible 测点，生成 25×9 响应场，并交给 LiveFrameAssembler 在 10 KB UTF-8 上限内组装。",
    )
    bullet_list(
        doc,
        [
            "降级顺序：完整帧 → 去掉压力点元数据 → 去掉压力场 → 压缩文本 → 最小文本 → 移除最旧传感器 → 跳过该帧。",
            "每帧携带 budget.limit_bytes 与 budget.omissions，消费者能区分“本来没有”和“因预算省略”。",
            "每客户端队列上限 4 帧，帧最大等待 0.5 秒；队列满、发送超时或帧过期时断开慢客户端。",
            "实时线程与发送线程通过线程安全唤醒事件协作，不阻塞全局广播。",
        ],
    )

    add_heading(doc, "3.5  历史回填、模型导入与持久化", 2)
    body_paragraph(
        doc,
        "历史数据走同一处理器，但标记为 BACKFILL：可以参与历史和告警分析，不进入实时帧。模型导入由 BridgeModelStore 统一处理扩展名、100 MB 上限、临时写入、GLB/glTF 2.0 校验、自包含资源校验、原子提升、profile 初始化和索引更新。",
    )
    body_paragraph(
        doc,
        "Scene Profile 是模型空间解释的唯一权威来源，包含右手米制坐标帧、模型平移/旋转/缩放、源单位缩放、桥面边界、测点锚点、图表角色和显示元数据。3D 渲染、测点、图表、相机适配和响应场使用同一不可变 revision。",
    )
    body_paragraph(
        doc,
        "持久化采用临时文件写入、fsync、os.replace 原子替换和目录 fsync。检查点缺失、损坏或 schema 不兼容时只记录告警并继续启动，不阻塞演示与服务可用性。",
    )

    # ------------------------------------------------------------------
    # 4. Algorithms
    # ------------------------------------------------------------------
    add_heading(doc, "4  核心算法设计", 1)
    add_figure(doc, detection, "图 2  规则、三模型投票与第三层仲裁", width_cm=16.0)
    body_paragraph(
        doc,
        "规则与 AI 并行执行。规则提供确定性底线，AI 用于发现规则未覆盖的模式，第三层只在模型分歧、低认知或高不确定性时介入。",
    )

    add_heading(doc, "4.1  STALWART-inspired EMA", 2)
    body_paragraph(
        doc,
        "每个传感器维护快慢两个指数移动平均，通过快慢 EMA 的偏离程度识别突发跳变。默认 fast α=0.3、slow α=0.05、阈值 3σ。该检测器计算量小，适合连续流，但不单独决定最终告警。",
    )
    add_code_block(
        doc,
        """
fast_t = a_fast * x_t + (1 - a_fast) * fast_(t-1)
slow_t = a_slow * x_t + (1 - a_slow) * slow_(t-1)
z_t = |fast_t - slow_t| / baseline_sigma
""",
    )

    add_heading(doc, "4.2  GAN-AE 重构检测", 2)
    body_paragraph(
        doc,
        "每个传感器从正常窗口学习轻量对抗自编码器。编码器压缩窗口，生成器重建窗口，重构误差超过训练分布阈值时投票。默认使用 8 个对抗子模型；子模型投票分歧和误差离散度形成认知度与不确定性。实现基于 NumPy，不依赖外部深度学习运行时。",
    )
    add_code_block(
        doc,
        """
latent = Encoder(normalized_window)
reconstruction = Generator(latent)
error = mean((normalized_window - reconstruction)^2)
""",
    )

    add_heading(doc, "4.3  Isolation Forest", 2)
    body_paragraph(
        doc,
        "每个传感器维护 200 条滚动窗口，使用 scikit-learn Isolation Forest（100 棵树）检测离群值。模型在获得足够正常样本后拟合，并按 25 条新正常读数在后台异步重拟合。评分同时参考森林 decision function 与值分布偏离，降低单一评分尺度带来的阈值漂移。",
    )

    add_heading(doc, "4.4  三模型投票与不确定性门控", 2)
    body_paragraph(
        doc,
        "每个模型独立产生 anomalous、confidence、score、cognition 和 uncertainty。单个模型只有满足 ready、anomalous 且 confidence ≥0.7 才计票；至少两票才确认异常。一致性置信度由参与投票模型的平均置信度乘以最低认知度得到。",
    )
    add_code_block(
        doc,
        """
vote_i = ready_i AND anomalous_i AND confidence_i >= 0.7
confirmed = sum(vote_i) >= 2
consensus_confidence = mean(confidence of voting models) * min(cognition)
gate = min(cognition) < 0.35 OR max(uncertainty) >= 0.45
""",
    )
    body_paragraph(
        doc,
        "无门控且至少两票时输出 ai_dual_confirm；三票参与时等级为红，否则为橙。门控触发时，等级封顶为黄，并转入第三层特征/空间仲裁。",
    )

    add_heading(doc, "4.5  特征仲裁", 2)
    body_paragraph(
        doc,
        "第三层使用最近 20 条和此前 60 条，共 80 条窗口，计算均值漂移、方差变化和趋势斜率。三项中至少两项超限才确认异常；两项为橙，三项为红；仅一项超限为疑似黄色；零项为正常。",
    )
    body_paragraph(
        doc,
        "该层只处理第二层“有模型触发但票数不足”或“不确定性门控”的样本，避免对所有正常读数重复计算。",
    )

    add_heading(doc, "4.6  跨传感器空间残差", 2)
    body_paragraph(
        doc,
        "对每个目标传感器，用同一时刻其他传感器重建其值，并通过岭回归抑制共线性和过拟合。空间状态分为 coherent、isolated_outlier、consistent 和 unavailable。多个测点同时偏离时视为协同响应；单点偏离且缺少空间支持时，将已确认异常降为黄色。",
    )
    add_code_block(
        doc,
        """
y_hat_j = Phi_j * beta_j
minimize ||W^(1/2) * (y - Phi * beta)||^2 + lambda * ||beta||^2
""",
    )

    add_heading(doc, "4.7  仿真-实测两阶段补偿与模态反演", 2)
    body_paragraph(
        doc,
        "补偿模型先用仿真数据给出基础响应，再用实测数据修正系统偏差，并输出方差、域距离和可靠性。超出训练域、方差过大或可靠性低于阈值时，接口返回 prediction=null 和回退原因，回退物理阈值，避免模型在未知工况下“自信地犯错”。",
    )
    body_paragraph(
        doc,
        "模态反演将结构响应近似为模态叠加 y≈Φq，经能量选模、方向置信度加权和岭正则化求模态坐标 q，输出全场位移、重建应变、残差、条件数、R²、RRMSE 和可靠度。可靠度由能量覆盖、测量支撑度和条件数共同决定。",
    )
    add_code_block(
        doc,
        """
y ~= Phi * q
q = (Phi^T * W * Phi + lambda * I)^(-1) * Phi^T * W * y
""",
    )

    # ------------------------------------------------------------------
    # 5. Digital twin and interaction
    # ------------------------------------------------------------------
    add_heading(doc, "5  数字孪生与前端交互", 1)
    add_figure(doc, SCREENSHOT, "图 3  单屏监控台：三维桥梁、实时趋势、响应云图与告警证据", width_cm=16.0)
    body_paragraph(
        doc,
        "只把模型放进浏览器还不够。模型、测点、图表和响应场需要共享同一套空间语义。平台通过 Bridge Scene Profile 把 glTF 模型变换、桥面边界、测点锚点、图表角色和响应场网格绑定在一起，前端和后端不再各自维护隐式坐标规则。",
    )

    add_heading(doc, "5.1  Bridge Scene Profile", 2)
    body_paragraph(
        doc,
        "Scene Profile 使用右手米制坐标帧：X 纵向、Y 向上、Z 横向。它记录模型平移、旋转、缩放、源单位缩放、桥面范围、测点锚点、测量角色和显示元数据。profile 采用不可变 revision；缺失时可根据 glTF 节点变换、accessor 边界和 deck/girder 命名推断 provisional profile，但推断失败会显式报错，不回退固定几何。",
    )
    add_table(
        doc,
        ["profile 字段", "作用"],
        [
            ["coordinate_frame", "定义右手米制坐标轴与单位"],
            ["model_transform", "模型平移、旋转、缩放、源单位换算"],
            ["deck_bounds", "桥面平面和响应场网格边界"],
            ["sensor_anchors", "测点在模型空间的锚点"],
            ["measurement_roles", "主应变、塔顶位移、拉索加速度等图表角色"],
            ["display", "桥型、跨度、节点数量等显示信息"],
        ],
        caption="表 8  Scene Profile 的空间语义",
        widths_cm=[4.6, 10.8],
        font_size=8.8,
    )

    add_heading(doc, "5.2  归一化响应场", 2)
    body_paragraph(
        doc,
        "每个测点将读数绝对值除以红色阈值，得到归一化响应指数，并截断到 1.25。响应指数按 Scene Profile 投影到桥面，再用反距离权重插值到 25×9 网格。该字段用于跨单位、跨测点的统一可视化，不是物理压力，也不是有限元应力结果。",
    )
    add_code_block(
        doc,
        """
ratio = min(abs(value) / red_threshold, 1.25)
weight = 1 / (dx^2 + dz^2 + 25)
field(x,z) = weighted_sum(ratio_i * weight_i) / sum(weight_i)
""",
    )

    add_heading(doc, "5.3  单屏监控与历史回放", 2)
    bullet_list(
        doc,
        [
            "3D 测点颜色与服务器 physical_state 对齐：正常、注意、警告、危险、未知。",
            "压力云图既可作为桥面贴图，也可在独立面板查看网格、测点投影和最大响应。",
            "趋势图按 Measurement Roles 选择传感器，不硬编码测点 ID。",
            "历史回放通过 REST 时刻快照驱动，支持时间轴拖动、播放/暂停和 1x/2x/4x/8x/16x 倍速。",
            "报告以 HTML 形式打开，可直接打印；桌面形态不依赖外网。",
        ],
    )

    add_heading(doc, "5.4  模型导入与热切换", 2)
    body_paragraph(
        doc,
        "模型导入只接受自包含 .glb 或 .gltf 2.0，单文件上限 100 MB。外部 .bin、纹理等 sidecar 资源会被拒绝，必须导出为 GLB 或内嵌 data URI。导入后生成或接收 Scene Profile，更新索引，并按需激活。前端重载模型与 profile，不另写一套坐标规则。",
    )

    # ------------------------------------------------------------------
    # 6. Reliability and performance
    # ------------------------------------------------------------------
    add_heading(doc, "6  工程可靠性与性能设计", 1)
    add_heading(doc, "6.1  数据结构与查询路径", 2)
    add_table(
        doc,
        ["需求", "结构", "原因"],
        [
            ["最新值 O(1)", "dict[sensor_id]", "高频读写"],
            ["滚动窗口", "deque(maxlen=500)", "O(1) 追加与淘汰"],
            ["全量回放", "每传感器 list", "有序二分查询"],
            ["时段计数", "array('d')", "紧凑时间戳存储"],
            ["Top-K", "最小堆", "O(log K) 维护"],
            ["历史降采样", "bisect + 均匀时间点", "避免全表扫描"],
            ["告警冷却", "每键有序时间数组 + bisect", "事件时间乱序也成立"],
        ],
        caption="表 9  数据引擎的关键数据结构",
        widths_cm=[3.8, 6.0, 5.6],
        font_size=8.8,
    )

    add_heading(doc, "6.2  并发与故障隔离", 2)
    body_paragraph(
        doc,
        "FastAPI 处理异步 HTTP/WebSocket；实时生成、规则、AI 和持久化在进程级后台线程中执行；可变业务状态通过 processing_lock 串行化。隔离森林重拟合在独立线程池执行，主检测路径不等待训练。当前架构建议单进程运行，多 worker 会分裂内存状态。",
    )
    add_table(
        doc,
        ["故障", "系统行为"],
        [
            ["单个 AI 模型异常", "记录失败，其他模型与规则告警继续"],
            ["检测管线整体异常", "保留规则告警，批次仍完成持久化"],
            ["检查点损坏", "启动继续，健康接口标记降级"],
            ["模型索引损坏", "忽略无效条目，不阻止服务"],
            ["Scene Profile 推断失败", "显式错误，不静默使用错误几何"],
            ["WebSocket 慢客户端", "断开该客户端，不影响其他订阅者"],
            ["实时帧超预算", "按固定顺序降级；仍失败则跳过该帧"],
        ],
        caption="表 10  典型故障与降级策略",
        widths_cm=[5.2, 10.2],
        font_size=8.8,
    )

    add_heading(doc, "6.3  可观测性与输入安全", 2)
    bullet_list(
        doc,
        [
            "每个 HTTP 请求生成或透传 X-Request-ID，响应返回同一标识。",
            "日志只记录方法、路径、状态、耗时和请求 ID；未处理异常不向客户端泄露堆栈。",
            "/api/health 汇总检测器、持久化、WebSocket、实时循环和阈值来源。",
            "CORS 使用显式来源白名单，禁止与 credentials 搭配的 *。",
            "批次先完整校验再写入；模型上传限制 100 MB 并校验 GLB/glTF 结构。",
            "当前未实现身份认证和权限模型；公网或生产内网部署必须在前置网关补齐认证、授权、审计和限速。",
        ],
    )

    add_heading(doc, "6.4  持久化与恢复", 2)
    body_paragraph(
        doc,
        "检查点由 CheckpointManager 在批次处理、阈值修改和正常停止时提交。JSON 适配器使用临时文件、fsync 和原子替换，保证读者只能看到完整文件；CheckpointStore 是可替换边界，后续可迁移到事务数据库或对象存储。",
    )

    # ------------------------------------------------------------------
    # 7. Characteristics, advantages, innovation
    # ------------------------------------------------------------------
    add_heading(doc, "7  技术特点、优势与创新点", 1)
    add_heading(doc, "7.1  技术特点", 2)
    bullet_list(
        doc,
        [
            "完整运行链路：接入、校验、存储、规则、AI、告警、3D、回放、报告和恢复在同一套服务里。",
            "规则与 AI 互补：规则提供确定性底线，AI 发现未知模式，仲裁处理分歧。",
            "告警保留判断依据：模型投票、置信度、认知度、不确定性、特征超限项、空间证据和阈值快照随告警保存。",
            "数字孪生一致性：Scene Profile 是模型、测点、图表和响应场的唯一空间事实源。",
            "有界实时传输：10 KB 帧预算、固定降级顺序、慢客户端隔离。",
            "工程化可靠性：检测器故障隔离、损坏检查点容忍、模型索引容错、显式降级。",
            "验收结果可以重跑：固定依赖、数据哈希、测试、性能门槛、算法基准和报告产物都留在仓库。",
        ],
    )

    add_heading(doc, "7.2  技术优势", 2)
    add_table(
        doc,
        ["维度", "单点固定阈值", "本平台"],
        [
            ["正常波动", "易受噪声和工况漂移影响", "基线学习 + 多窗口特征"],
            ["未知异常", "只能识别已设阈值的模式", "规则 + 三模型 + 仲裁"],
            ["误报治理", "调高阈值，牺牲灵敏度", "冷却、投票、认知门控、空间一致性"],
            ["可解释性", "只有阈值数字", "投票、特征、空间证据、来源"],
            ["数字孪生", "模型与数据脱节", "Scene Profile 统一空间语义"],
            ["失败处理", "模型失败可能中断链路", "局部降级、规则兜底"],
            ["验收", "人工演示", "自动化测试 + 性能/算法基准"],
        ],
        caption="表 11  与单阈值方案的能力对比",
        widths_cm=[2.8, 6.4, 6.2],
        font_size=8.6,
    )
    body_paragraph(
        doc,
        "平台的主要差异来自工程约束的组合。物理约束、模型不确定性、空间相关性、实时预算和验收证据共同决定系统能否交付；单个模型的分数只占其中一部分。",
    )

    add_heading(doc, "7.3  技术创新点", 2)
    body_paragraph(
        doc,
        "以下为工程组合创新和落地创新，不主张单个基础算法为行业首创。",
    )
    bullet_list(
        doc,
        [
            "不确定性驱动的分层决策：模型分歧、认知度和不确定性决定样本是否进入下一层。",
            "空间一致性仲裁：用其他测点重建目标测点，区分孤立坏点与真实结构协同响应，并对孤立超限限制等级。",
            "Scene Profile 单一事实源：模型变换、桥面边界、测点锚点、图表角色和响应场共用不可变 profile revision。",
            "带可靠性与回退的两阶段补偿：仿真给基础响应，实测修正偏差；超域/高方差/低可靠时回退物理阈值。",
            "带可靠度的模态全场反演：能量选模、方向置信度加权、正则化求解，并输出条件数、残差和可靠度。",
            "预算内可审计降级：实时帧明确记录省略项和文本精度，避免把传输裁剪误认为“没有异常”。",
            "验收即产品的一部分：测试、性能门槛、数据哈希、固定随机种子和复现命令共同构成工程证据。",
        ],
    )

    # ------------------------------------------------------------------
    # 8. Acceptance evidence
    # ------------------------------------------------------------------
    add_heading(doc, "8  验收与工程证据", 1)
    add_heading(doc, "8.1  自动化测试", 2)
    body_paragraph(
        doc,
        "后端测试覆盖数据摄入、阈值与状态、告警生命周期、历史回放、持久化、WebSocket、模型导入、Scene Profile、三层检测、GAN-AE 投票、特征仲裁、空间残差、补偿、模态反演、报告和系统验收。当前运行结果为 384 passed，1 条来自依赖库的弃用告警。",
    )
    add_code_block(
        doc,
        """
384 passed, 1 warning in 64.90s
""",
    )

    add_heading(doc, "8.2  系统验收", 2)
    body_paragraph(
        doc,
        "系统验收命令为 python -m benchmarks.acceptance，依次运行全量 pytest、10,000 条批量摄入、常规查询、快照、三层 AI 单条检测、API 负载、10 个 WebSocket 客户端和合成验证集精度门槛。以下结果来自 2026-11-03 的本机单进程、本机回环环境。",
    )
    add_table(
        doc,
        ["门槛", "实测", "上限/下限", "结果"],
        [
            ["10,000 条批量摄入", "393.76 ms", "≤ 500 ms", "PASS"],
            ["常规查询 p95", "7.47 ms", "≤ 200 ms", "PASS"],
            ["历史快照 p95", "1.04 ms", "≤ 100 ms", "PASS"],
            ["三层检测 p95", "11.45 ms", "≤ 200 ms", "PASS"],
            ["API 吞吐", "152.65 QPS", "≥ 50 QPS", "PASS"],
            ["WebSocket 客户端", "10 / 10", "≥ 10", "PASS"],
            ["WebSocket 帧延迟 p95", "9.10 ms", "≤ 500 ms", "PASS"],
            ["验证集准确率", "0.9924", "≥ 0.90", "PASS"],
            ["验证集误报率", "0.0023", "≤ 0.10", "PASS"],
        ],
        caption="表 12  系统验收结果（本机单进程）",
        widths_cm=[5.0, 4.0, 3.8, 2.4],
        font_size=8.8,
    )
    body_paragraph(
        doc,
        "合成验证集包含 24 小时、8 测点、69,120 条读数和 1,440 个一分钟窗口。带时间确认的规则链路准确率 0.9924、误报率 0.0023、召回率 0.9407、事件召回率 1.0000；未确认的原始规则层准确率为 0.9104。该结果证明确认策略降低了碎片化误报，但仍是合成数据验证。",
    )

    add_heading(doc, "8.3  VBA 公开数据基准", 2)
    body_paragraph(
        doc,
        "VBA 基准使用 68 条录音、8 个加速度通道，按工况分层做 5 折录音级划分。原始告警链路与离线监督融合结果如下。融合模型为 StandardScaler + LogisticRegression，用于验证“警报证据 + 多通道序列特征”能够降低录音级误报。",
    )
    add_table(
        doc,
        ["指标", "原始告警链路", "融合增强"],
        [
            ["准确率", "0.4706", "0.9706"],
            ["误报率", "1.0000", "0.0278"],
            ["召回率", "1.0000", "0.9688"],
            ["F1", "0.6400", "0.9688"],
            ["单链路处理 p95", "6.342 ms", "6.741 ms"],
        ],
        caption="表 13  VBA 录音级基准结果",
        widths_cm=[5.0, 5.2, 5.2],
        font_size=8.8,
    )
    body_paragraph(
        doc,
        "必须明确：该结果是录音级离线分类，不是线上逐读数告警精度，也不是结构应力/位移预测精度。原始告警链路在该基准上误报高，说明仅靠固定阈值不足；但不能把增强结果直接替换成实时链路指标。",
    )

    add_heading(doc, "8.4  长稳与前端构建", 2)
    body_paragraph(
        doc,
        "仓库提供 24 小时长稳入口，现有提交产物是 7.4 秒烟雾测试，验证了服务存活、10 个连接、帧接收和错误计数，但不能据此宣称已经完成 24 小时连续运行验收。正式提交前应保留一次完整 24 小时报告。",
    )
    body_paragraph(
        doc,
        "前端通过 vue-tsc + vite build 完成类型检查与生产构建，共转换 581 个模块。主 JS 包约 1,736 kB（gzip 约 537 kB），Vite 已提示单 chunk 超过 500 kB。构建通过不等同于低端设备首屏性能已验收，后续应做动态导入和 code splitting。",
    )

    # ------------------------------------------------------------------
    # 9. Boundaries and roadmap
    # ------------------------------------------------------------------
    add_heading(doc, "9  工程边界、演进路线与演示建议", 1)
    add_heading(doc, "9.1  当前边界与风险", 2)
    add_table(
        doc,
        ["类别", "当前边界", "影响"],
        [
            ["数据", "主验证集为合成数据；无真实桥梁长期监测数据", "不能宣称真实工程精度"],
            ["阈值", "competition-design-basis-v1，provisional", "不能用于正式工程决策"],
            ["VBA", "仅加速度、录音级标签", "不能外推为多传感器逐读数精度"],
            ["算法", "STALWART-inspired、轻量 GAN-AE、合成标定/模态", "真实精度需现场重新标定"],
            ["架构", "单进程内存状态；多 worker 会分裂状态", "不能直接横向扩容"],
            ["安全", "未实现认证、RBAC、租户隔离、审计", "公网部署需前置网关补强"],
            ["前端", "主 JS chunk 约 1.74 MB", "低端设备首屏性能仍需优化"],
            ["长稳", "24 小时入口已实现，完整报告尚未归档", "不能宣称已完成 24 小时验收"],
        ],
        caption="表 14  当前工程边界",
        widths_cm=[2.8, 8.2, 5.0],
        font_size=8.5,
    )

    add_heading(doc, "9.2  后续演进路线", 2)
    add_table(
        doc,
        ["阶段", "重点任务", "目标"],
        [
            ["近期", "24 小时长稳、桌面回归、前端 code splitting、现场数据标定", "补齐可交付性与真实数据基础"],
            ["中期", "MQTT/OPC UA/Modbus 网关、时序数据库、消息总线、认证与 RBAC", "从演示系统升级为生产架构"],
            ["长期", "有限元模型更新、传感器优化布置、损伤演化、多桥多项目管理", "形成工程智能与运维闭环"],
        ],
        caption="表 15  后续演进路线",
        widths_cm=[2.4, 8.2, 5.4],
        font_size=8.8,
    )

    add_heading(doc, "9.3  推荐演示路径", 2)
    bullet_list(
        doc,
        [
            "打开总览，展示 3D 桥梁、8 个测点、实时趋势、响应云图和告警面板。",
            "说明测点颜色由服务器物理状态投影生成，压力场和模型共享同一 Scene Profile。",
            "观察正常波动，解释基线学习和正常状态，不把每次波动都当异常。",
            "注入异常，展示规则/AI 告警证据、投票、认知度和不确定性。",
            "查看检测器状态，说明基线与模型健康；切换到历史回放，验证任意时刻快照。",
            "导出 HTML 报告，展示报告的时间范围和结构状态。",
            "导入自包含 GLB，展示模型激活、Scene Profile revision 和测点/压力场联动。",
            "主动说明合成数据、provisional 阈值和真实标定计划，体现工程严谨性。",
        ],
    )

    add_heading(doc, "9.4  与赛项评分点的对应", 2)
    add_table(
        doc,
        ["评分方向", "本项目可用证据"],
        [
            ["问题定义", "桥梁运维中的数据割裂、响应滞后、误报和可解释性问题"],
            ["方案思路", "分层架构、端到端链路、ADR 和算法边界"],
            ["方案成效", "384 项测试、系统验收、合成验证集、VBA 基准"],
            ["工程主题契合", "BIM/glTF、桥梁测点、规范阈值、响应场、模态反演和报告"],
            ["工程知识专业性", "阈值依据、单位、连接/物理状态分离、低温边界说明"],
            ["交互体验", "单屏监控、3D 测点、响应云图、趋势、回放、模型导入和报告"],
            ["运行效率", "摄入、查询、检测、API、WebSocket 指标与前端构建结果"],
        ],
        caption="表 16  竞赛评审关注点与文档证据",
        widths_cm=[4.2, 11.2],
        font_size=8.8,
    )

    # ------------------------------------------------------------------
    # 10. Conclusion
    # ------------------------------------------------------------------
    add_heading(doc, "10  结论", 1)
    body_paragraph(
        doc,
        "本项目已经形成一套可运行的桥梁数字孪生健康监测原型。它把物理规则、三模型检测、不确定性门控、空间残差、版本化 Scene Profile、有界实时帧和原子恢复放在同一条链路里，并通过自动化测试、系统验收和公开数据基准留下了可以重跑的证据。",
    )
    body_paragraph(
        doc,
        "面向真实工程，下一步需要完成现场数据标定、24 小时长稳、工业协议接入，以及生产存储与权限体系。边界讲清楚之后，数字孪生与 AI 检测才更容易通过工程评审和部署验收。",
    )

    # ------------------------------------------------------------------
    # Appendix
    # ------------------------------------------------------------------
    add_heading(doc, "附录 A  术语表", 1)
    add_table(
        doc,
        ["术语", "说明"],
        [
            ["SHM", "Structural Health Monitoring，结构健康监测"],
            ["Digital Twin", "物理对象与数字模型的动态映射"],
            ["Scene Profile", "桥梁空间解释档案，定义坐标、模型变换、桥面边界和测点锚点"],
            ["Live Frame", "1 Hz 推送给前端的实时数据帧"],
            ["Live Eligible", "允许进入实时帧的数据资格"],
            ["Backfill", "只进入历史和告警分析，不进入实时帧的数据"],
            ["Threshold Profile", "类型级黄/橙/红物理阈值集合"],
            ["Cognition", "模型对样本属于已学习工况的认知程度"],
            ["Uncertainty Gate", "低认知或高不确定性时限制告警等级并转仲裁的策略"],
            ["Spatial Residual", "用其他传感器预测目标传感器后的残差"],
            ["Coherent Outlier", "多个测点同时偏离，具有空间协同支持"],
            ["Isolated Outlier", "单点偏离且缺少其他测点支持"],
            ["VBA", "桥梁损伤振动数据集基准"],
        ],
        caption="表 17  术语表",
        widths_cm=[4.2, 11.2],
        font_size=8.5,
    )

    add_heading(doc, "附录 B  架构决策记录与复现命令", 1)
    body_paragraph(
        doc,
        "关键设计取舍记录在 docs/adr/ 下，共 15 项，包括统一告警生命周期、类型级阈值、VBA 录音级基准、指定测点注入、进程级实时流、Known/Online 语义、原子检查点、配置与可观测性、系统验收、融合增强边界、阈值来源、响应场与模型导入、服务器状态投影、版本化 Scene Profile、帧预算与导入流边界。",
    )
    add_code_block(
        doc,
        r"""
# 后端测试
.\.venv\Scripts\python.exe -m pytest -q

# 系统验收
.\.venv\Scripts\python.exe -m benchmarks.acceptance

# VBA 融合基准
.\.venv\Scripts\python.exe -m benchmarks.vba.evaluate --mode enhanced

# 24 小时长稳
.\.venv\Scripts\python.exe -m benchmarks.stability --hours 24 --probe-interval 60 --clients 10

# 前端构建
cd frontend
pnpm build
""",
    )
    body_paragraph(
        doc,
        "本文件与 README.md、docs/TECHNICAL_DOCUMENT.md、benchmarks/ 产物共同构成项目技术资料。答辩遇到指标追问时，应同时引用验收报告路径和数据集边界。",
    )

    return doc


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    document = build_document()
    document.save(OUTPUT)
    print(f"DOCX written: {OUTPUT}")


if __name__ == "__main__":
    main()
