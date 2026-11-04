# -*- coding: utf-8 -*-
"""Build a 10-slide defense deck for the bridge digital twin project."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
from pptx.oxml import parse_xml


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "assets" / "planning"
OUTPUT = OUT_DIR / "桥梁数字孪生健康监测平台_答辩PPT_10页_v1.1.pptx"
SCREENSHOT_COVER = ROOT / "assets" / "screenshots" / "console-redesign-1600.png"
SCREENSHOT_TWIN = ROOT / "assets" / "screenshots" / "monitoring-session-1600.png"

NAVY = "0B1118"
NAVY_2 = "14202A"
TEAL = "2D7D7A"
TEAL_LIGHT = "E7F3F2"
TEAL_MID = "6BA8A4"
AMBER = "D79A2B"
AMBER_LIGHT = "FBF2E1"
INK = "25313A"
MUTED = "66727A"
LINE = "D9DFE3"
PAPER = "F7F8F8"
WHITE = "FFFFFF"
RED = "B94B37"
RED_LIGHT = "F7E6E1"
GREEN = "2F7D5B"
GREEN_LIGHT = "E8F3ED"

FONT_CN = "Microsoft YaHei"
FONT_EN = "Arial"
SLIDE_W = 13.333
SLIDE_H = 7.5


def rgb(value: str) -> RGBColor:
    value = value.lstrip("#")
    return RGBColor(*(int(value[index : index + 2], 16) for index in (0, 2, 4)))


def set_run_font(run, size: float, *, bold: bool = False, color: str = INK) -> None:
    run.font.name = FONT_EN
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    r_pr = run._r.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = parse_xml('<a:ea xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>')
        r_pr.append(ea)
    ea.set("typeface", FONT_CN)


def set_bg(slide, color: str = PAPER) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(color)


def add_rect(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str = WHITE,
    line: str | None = LINE,
    radius: bool = True,
    line_width: float = 1.0,
):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x),
        Inches(y),
        Inches(w),
        Inches(h),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    if line:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Pt(line_width)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_text(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    *,
    size: float = 16,
    bold: bool = False,
    color: str = INK,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    valign: MSO_ANCHOR = MSO_ANCHOR.TOP,
    margin: float = 0.0,
    line_spacing: float = 1.05,
    space_after: float = 0,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(margin)
    tf.margin_right = Inches(margin)
    tf.margin_top = Inches(margin)
    tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = valign
    lines = text.split("\n")
    for index, line in enumerate(lines):
        paragraph = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        paragraph.alignment = align
        paragraph.line_spacing = line_spacing
        paragraph.space_after = Pt(space_after)
        run = paragraph.add_run()
        run.text = line
        set_run_font(run, size, bold=bold, color=color)
    return box


def add_bullets(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    items: Iterable[str],
    *,
    size: float = 15,
    color: str = INK,
    bullet_color: str = TEAL,
    gap: float = 8,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for index, item in enumerate(items):
        paragraph = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        paragraph.space_after = Pt(gap)
        paragraph.line_spacing = 1.1
        dot = paragraph.add_run()
        dot.text = "•  "
        set_run_font(dot, size, bold=True, color=bullet_color)
        run = paragraph.add_run()
        run.text = item
        set_run_font(run, size, color=color)
    return box


def add_brand(slide, page: int, *, dark: bool = False, source: str | None = None) -> None:
    brand_color = "AFC2C7" if dark else NAVY
    accent = AMBER if dark else TEAL
    add_rect(slide, 0.66, 0.38, 0.28, 0.28, fill=accent, line=None, radius=False)
    add_text(slide, 1.03, 0.31, 3.8, 0.28, "HUIHE BRIDGE  /  MONITOR OS", size=10.5, bold=True, color=brand_color)
    add_text(slide, 1.03, 0.58, 4.5, 0.22, "DIGITAL TWIN  ·  STRUCTURAL HEALTH MONITORING", size=7.5, color="8FA1A7" if dark else MUTED)
    add_text(slide, 10.55, 0.38, 2.1, 0.26, f"TECHNICAL DEFENSE  ·  {page:02d}", size=8.5, color="8FA1A7" if dark else MUTED, align=PP_ALIGN.RIGHT)
    if not dark:
        line = slide.shapes.add_connector(1, Inches(0.66), Inches(0.93), Inches(12.67), Inches(0.93))
        line.line.color.rgb = rgb(LINE)
        line.line.width = Pt(0.8)
    if source:
        add_text(slide, 0.68, 7.08, 9.8, 0.2, source, size=7.8, color=MUTED)


def add_slide_title(slide, title: str, *, subtitle: str | None = None, y: float = 1.05) -> None:
    add_text(slide, 0.68, y, 11.7, 0.52, title, size=27, bold=True, color=NAVY)
    if subtitle:
        add_text(slide, 0.70, y + 0.50, 11.5, 0.32, subtitle, size=12.5, color=MUTED)


def add_metric_chip(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    label: str,
    *,
    dark: bool = False,
    accent: str = TEAL,
) -> None:
    fill = "111B23" if dark else WHITE
    line = "2B3C46" if dark else LINE
    add_rect(slide, x, y, w, h, fill=fill, line=line)
    add_rect(slide, x, y, 0.06, h, fill=accent, line=None, radius=False)
    add_text(slide, x + 0.20, y + 0.16, w - 0.32, 0.35, value, size=20, bold=True, color=WHITE if dark else NAVY)
    add_text(slide, x + 0.20, y + 0.55, w - 0.32, 0.22, label, size=9.5, color="AFC2C7" if dark else MUTED)


def add_right_arrow(slide, x: float, y: float, w: float = 0.28, h: float = 0.20, color: str = "A7B2B8") -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False


def add_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


# SLIDE_PART_2


def build_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    # ------------------------------------------------------------------
    # Slide 1: Cover
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, NAVY)
    for x in [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9, 11.0, 12.1]:
        line = slide.shapes.add_connector(1, Inches(x), Inches(0), Inches(x), Inches(SLIDE_H))
        line.line.color.rgb = rgb("16222C")
        line.line.width = Pt(0.5)
    for y in [0.8, 1.6, 2.4, 3.2, 4.0, 4.8, 5.6, 6.4]:
        line = slide.shapes.add_connector(1, Inches(0), Inches(y), Inches(SLIDE_W), Inches(y))
        line.line.color.rgb = rgb("16222C")
        line.line.width = Pt(0.5)
    add_brand(slide, 1, dark=True)
    add_rect(slide, 0.75, 1.55, 1.82, 0.06, fill=AMBER, line=None, radius=False)
    add_text(slide, 0.75, 1.82, 5.4, 0.30, "工程场景数字化 · 数字孪生 / 结构健康监测", size=10.5, color="9CC3C1")
    add_text(slide, 0.75, 2.25, 5.6, 0.78, "桥梁数字孪生", size=34, bold=True, color=WHITE)
    add_text(slide, 0.75, 3.02, 5.6, 0.78, "健康监测平台", size=34, bold=True, color=WHITE)
    add_text(slide, 0.75, 3.92, 5.2, 0.62, "传感器数据、结构状态、告警证据与运维追溯", size=17, color="C7D5D6")
    add_text(slide, 0.75, 4.63, 4.8, 0.55, "规则与 AI 并行 · 三模型投票 · 特征/空间仲裁\n3D 数字孪生 · 历史回放 · 可重跑验收", size=11.5, color="8FA1A7")
    # Screenshot panel.
    add_rect(slide, 6.28, 1.52, 6.36, 3.66, fill="101B23", line="354750", radius=False, line_width=1.2)
    picture = slide.shapes.add_picture(str(SCREENSHOT_COVER), Inches(6.38), Inches(1.62), width=Inches(6.16), height=Inches(3.465))
    add_rect(slide, 6.28, 5.24, 6.36, 0.06, fill=TEAL_MID, line=None, radius=False)
    add_text(slide, 6.38, 5.38, 6.0, 0.30, "实时监控台 / 3D 桥梁 · 响应云图 · 趋势 · 告警证据", size=9.5, color="8FA1A7")
    add_metric_chip(slide, 0.75, 6.02, 2.55, 0.82, "384", "后端测试通过", dark=True, accent=TEAL)
    add_metric_chip(slide, 3.55, 6.02, 2.55, 0.82, "152.65", "API QPS", dark=True, accent=AMBER)
    add_metric_chip(slide, 6.35, 6.02, 2.55, 0.82, "11.45 ms", "三层检测 p95", dark=True, accent=TEAL_MID)
    add_metric_chip(slide, 9.15, 6.02, 2.55, 0.82, "10 / 10", "WebSocket 客户端", dark=True, accent=AMBER)
    add_text(slide, 0.75, 7.10, 8.0, 0.18, "技术答辩 · 2026.11  /  指标口径见验收与边界页", size=7.8, color="7E9097")
    add_notes(
        slide,
        "开场 30 秒：这是一个从传感器接入、异常检测、三维表达、历史回放到可追溯报告的完整工程链路。"
        "单点算法指标只是证据之一。答辩时用测试、验收和边界说明系统已经做到什么，以及哪些结果还不能证明。",
    )

    # ------------------------------------------------------------------
    # Slide 2: Problem
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 2, source="来源：项目问题定义；桥梁结构健康监测工程背景")
    add_slide_title(
        slide,
        "数据已经在流，决策却没有接上",
        subtitle="现场读数很多；难点在把读数解释成状态，再把状态变成可执行的处置证据。",
    )
    nodes = [
        ("01", "持续采样", "应变 / 位移 / 加速度 / 温度", WHITE, LINE, TEAL),
        ("02", "数据进入平台", "批量校验、存储、历史回放", WHITE, LINE, TEAL),
        ("03", "状态判断", "单点阈值、噪声、空间关系缺失", AMBER_LIGHT, "E6C98E", "8A6219"),
        ("04", "巡检修缮", "证据不足，响应仍靠人工", RED_LIGHT, "E5B8AC", RED),
    ]
    xs = [0.72, 3.79, 6.86, 9.93]
    for index, (number, title, detail, fill, outline, accent) in enumerate(nodes):
        x = xs[index]
        add_rect(slide, x, 2.25, 2.72, 1.55, fill=fill, line=outline, radius=False, line_width=1.1)
        add_rect(slide, x, 2.25, 2.72, 0.06, fill=accent, line=None, radius=False)
        add_text(slide, x + 0.17, 2.44, 0.36, 0.20, number, size=8.8, bold=True, color=accent)
        add_text(slide, x + 0.17, 2.72, 2.32, 0.30, title, size=15.2, bold=True, color=INK)
        add_text(slide, x + 0.17, 3.18, 2.32, 0.42, detail, size=9.6, color=MUTED)

    # Continuous link from sampling to the platform.
    add_right_arrow(slide, 3.47, 2.92, w=0.28, h=0.20)
    # Two visible breaks in the decision chain.
    for x, label in ((6.62, "语义断点"), (9.69, "决策断点")):
        add_rect(slide, x, 2.77, 0.06, 0.50, fill=RED, line=None, radius=False)
        add_text(slide, x - 0.56, 2.30, 1.18, 0.22, label, size=7.8, bold=True, color=RED, align=PP_ALIGN.CENTER)
    add_rect(slide, 0.72, 4.55, 11.94, 1.30, fill=NAVY, line=None, radius=False)
    add_text(slide, 0.98, 4.76, 1.05, 0.24, "工程目标", size=9.8, bold=True, color=AMBER)
    add_text(slide, 2.07, 4.70, 10.15, 0.56, "把四段接起来，并让每一次判断都能追问证据。", size=19.5, bold=True, color=WHITE)
    add_text(slide, 2.07, 5.26, 10.0, 0.24, "读数先变成统一语义，再变成可复核的状态和告警。", size=9.7, color="AFC2C7")
    add_notes(
        slide,
        "这一页把问题画成一条断开的链：采样和数据接入已经有了，但从数据到状态、从状态到处置仍缺连续的证据。"
        "后面的实时性、空间语义、误报治理和可解释性，都是在这两个断点上做补齐。",
    )

    # ------------------------------------------------------------------
    # Slide 3: Logic chain
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 3, source="来源：系统架构、实时链路与告警生命周期实现")
    add_slide_title(slide, "从接入口到报告，每一步都有数据合同")
    stages = [
        ("01", "接入校验", "JSON / CSV / 单条\n10,000 条整批原子"),
        ("02", "数据引擎", "最新值 / 滚动窗口\n全量历史 / Top-K"),
        ("03", "规则 + AI", "物理阈值底线\n三模型投票 + 仲裁"),
        ("04", "告警生命周期", "10 s 事件时间冷却\n统一来源与保留"),
        ("05", "10 KB Live Frame", "32 测点快照\n确定性降级"),
        ("06", "孪生表达", "3D / 回放 / 报告\nREST + WebSocket"),
    ]
    start_x, y, w, h, gap = 0.66, 1.88, 1.78, 1.40, 0.32
    for index, (number, title, detail) in enumerate(stages):
        x = start_x + index * (w + gap)
        fill = TEAL_LIGHT if index in (2, 4) else WHITE
        outline = "8FC3BF" if index in (2, 4) else LINE
        add_rect(slide, x, y, w, h, fill=fill, line=outline)
        add_text(slide, x + 0.14, y + 0.10, 0.36, 0.20, number, size=8.8, bold=True, color=TEAL)
        add_text(slide, x + 0.12, y + 0.36, w - 0.24, 0.30, title, size=12.2, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.10, y + 0.82, w - 0.20, 0.42, detail, size=9.0, color=MUTED, align=PP_ALIGN.CENTER)
        if index < len(stages) - 1:
            add_right_arrow(slide, x + w + 0.07, y + h / 2 - 0.10, w=0.18, h=0.20)

    supports = [
        ("Bridge Scene Profile", "模型变换 · 桥面边界 · 测点锚点 · 图表角色", AMBER_LIGHT, "E6C98E"),
        ("原子检查点", "导出完整状态 · fsync · os.replace", TEAL_LIGHT, "9CCAC6"),
        ("可追溯分析", "补偿估计 · 模态反演 · HTML 报告", "EEF2F3", LINE),
    ]
    for index, (title, detail, fill, outline) in enumerate(supports):
        x = 0.70 + index * 4.0
        add_rect(slide, x, 4.43, 3.72, 1.15, fill=fill, line=outline)
        add_text(slide, x + 0.18, 4.58, 3.35, 0.24, title, size=12.2, bold=True, color=INK)
        add_text(slide, x + 0.18, 4.94, 3.32, 0.35, detail, size=8.8, color=MUTED)
    add_text(slide, 0.72, 6.18, 11.9, 0.35, "实现原则：实时性来自有界数据结构；可解释性来自统一证据字段；可恢复性来自原子状态边界。", size=11.5, color=MUTED)
    add_notes(
        slide,
        "这一页说明数据合同如何把接入、存储、规则/AI、告警、实时帧和孪生表达连起来。"
        "下方的 Scene Profile、检查点和分析能力支撑整条链路，也各自有独立边界。",
    )

    # ------------------------------------------------------------------
    # Slide 4: Detection
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 4, source="来源：processor.process / VotingDetector / FeatureArbitrationDetector / SpatialResidualModel")
    add_slide_title(slide, "不让一个模型直接决定告警等级", subtitle="规则、模型投票和特征/空间仲裁各自负责一类判断；第三层只处理不确定样本")
    layer_specs = [
        (1.78, 1.17, "01", "物理阈值规则", "确定性安全底线", TEAL_LIGHT, "8FC3BF", TEAL),
        (3.14, 1.38, "02", "三模型投票", "独立基线 + 置信度门槛 + 至少两票", "FFF8EA", "E6C98E", "8A6219"),
        (4.70, 1.42, "03", "特征 / 空间仲裁", "均值漂移 · 方差变化 · 趋势斜率 · 空间残差", "EEF2F3", LINE, INK),
    ]
    for y, h, number, title, subtitle, fill, outline, color in layer_specs:
        add_rect(slide, 0.68, y, 8.35, h, fill=fill, line=outline)
        add_text(slide, 0.90, y + 0.13, 0.38, 0.20, number, size=9, bold=True, color=color)
        add_text(slide, 1.32, y + 0.10, 3.3, 0.30, title, size=14.2, bold=True, color=color)
        add_text(slide, 1.32, y + 0.43, 6.7, 0.22, subtitle, size=8.8, color=MUTED)

    layer1_chips = [
        ("红 / 橙 / 黄", "按绝对值降级匹配"),
        ("统一告警入口", "快照 + 冷却 + 50k 保留"),
        ("规则兜底", "AI 故障仍保留确定性告警"),
    ]
    for index, (label, detail) in enumerate(layer1_chips):
        x = 1.34 + index * 2.50
        add_rect(slide, x, 2.31, 2.28, 0.50, fill=WHITE, line="B9D9D6")
        add_text(slide, x + 0.12, 2.38, 2.02, 0.19, label, size=8.8, bold=True, color=INK)
        add_text(slide, x + 0.12, 2.58, 2.02, 0.16, detail, size=8.0, color=MUTED)

    layer2_models = [
        ("STALWART-inspired", "快慢 EMA 突变"),
        ("GAN-AE", "重构误差 + 8 子模型"),
        ("Isolation Forest", "滚动窗口离群"),
    ]
    for index, (name, detail) in enumerate(layer2_models):
        x = 1.34 + index * 2.50
        add_rect(slide, x, 3.84, 2.28, 0.52, fill=WHITE, line="E2C999")
        add_text(slide, x + 0.12, 3.91, 2.04, 0.20, name, size=8.7, bold=True, color=INK)
        add_text(slide, x + 0.12, 4.12, 2.04, 0.16, detail, size=8.0, color=MUTED)

    layer3_chips = [
        ("均值漂移", "近期均值 / 历史尺度"),
        ("方差变化", "波动结构是否改变"),
        ("趋势斜率", "持续恶化 vs 瞬时跳变"),
        ("空间残差", "孤立坏点 vs 协同响应"),
    ]
    for index, (name, detail) in enumerate(layer3_chips):
        x = 1.34 + index * 1.88
        add_rect(slide, x, 5.38, 1.72, 0.50, fill=WHITE, line="CBD5D9")
        add_text(slide, x + 0.09, 5.44, 1.54, 0.18, name, size=8.0, bold=True, color=INK)
        add_text(slide, x + 0.09, 5.63, 1.54, 0.15, detail, size=7.2, color=MUTED)
    # Layer arrows.
    add_right_arrow(slide, 4.82, 2.98, w=0.24, h=0.12, color="9BA7AD")
    add_right_arrow(slide, 4.82, 4.54, w=0.24, h=0.12, color="9BA7AD")
    add_text(slide, 5.10, 2.93, 2.4, 0.18, "并行安全网", size=7.8, color=MUTED)
    add_text(slide, 5.10, 4.49, 3.5, 0.18, "≥2 票 & 置信度 ≥0.7", size=7.8, color=MUTED)

    add_rect(slide, 9.30, 1.78, 3.28, 4.35, fill=NAVY, line=None)
    add_text(slide, 9.55, 2.02, 2.72, 0.25, "为什么这样设计？", size=10.5, bold=True, color=AMBER)
    reasons = [
        ("规则", "确定性、低延迟、可审计的安全底线"),
        ("AI", "发现规则未覆盖的未知模式"),
        ("第三层", "只把预算花在分歧和不确定样本上"),
    ]
    for index, (title, detail) in enumerate(reasons):
        y = 2.55 + index * 1.05
        add_text(slide, 9.58, y, 1.2, 0.25, title, size=12, bold=True, color=WHITE)
        add_text(slide, 9.58, y + 0.30, 2.70, 0.50, detail, size=9.4, color="AFC2C7")
    add_text(slide, 0.72, 6.42, 8.3, 0.25, "输出证据：模型投票 · 置信度 · 认知度 · 不确定性 · 特征超限项 · 空间状态 · 阈值版本", size=8.8, color=MUTED)
    add_notes(
        slide,
        "规则和 AI 并行执行，各自承担不同职责。"
        "第三层是查询成本更高的证据层，只在模型分歧、低认知或高不确定性时介入。",
    )

    # ------------------------------------------------------------------
    # Slide 5: Digital twin
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 5, source="来源：Bridge Scene Profile / 25×9 响应场 / 前端监控台")
    add_slide_title(slide, "模型、测点、图表和响应场共用一套坐标", subtitle="Scene Profile 是这套坐标的唯一来源")
    add_rect(slide, 0.70, 1.82, 7.48, 4.24, fill="101B23", line="354750", radius=False, line_width=1.0)
    slide.shapes.add_picture(str(SCREENSHOT_TWIN), Inches(0.80), Inches(1.92), width=Inches(7.28), height=Inches(4.095))
    add_text(slide, 0.82, 6.10, 7.15, 0.20, "实时监控台：3D 桥梁 / 测点状态 / 趋势 / 响应云图 / 告警证据", size=7.7, color=MUTED)

    add_text(slide, 8.50, 1.78, 4.0, 0.30, "同一个 Scene Profile 驱动", size=11, bold=True, color=TEAL)
    twin_items = [
        ("01", "3D 模型与相机", "模型变换、单位缩放、桥面边界"),
        ("02", "测点与图表角色", "锚点、主应变、塔顶位移、拉索加速度"),
        ("03", "25×9 响应场", "网格边界与测点投影使用同一空间解释"),
        ("04", "模型导入 revision", "GLB/glTF 100 MB；profile 不可变版本"),
    ]
    for index, (number, title, detail) in enumerate(twin_items):
        y = 2.28 + index * 0.92
        add_text(slide, 8.52, y, 0.35, 0.20, number, size=8.5, bold=True, color=AMBER)
        add_text(slide, 8.92, y - 0.02, 3.50, 0.24, title, size=11.8, bold=True, color=INK)
        add_text(slide, 8.92, y + 0.27, 3.48, 0.30, detail, size=8.5, color=MUTED)
    add_text(slide, 8.52, 6.04, 3.9, 0.52, "响应场是归一化响应指数，不是物理压力，也不是有限元应力结果。", size=9.0, color=RED)
    add_notes(
        slide,
        "数字孪生在工程上要求模型、测点、图表和响应场共享同一套空间语义。"
        "Scene Profile 提供这套语义；更换模型时切换 profile revision，前端不另维护坐标规则。",
    )

    # ------------------------------------------------------------------
    # Slide 6: Real-time reliability
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 6, source="来源：LiveTickPipeline / LiveFrameAssembler / WebSocketManager / CheckpointStore")
    add_slide_title(slide, "实时系统的关键，是预算内可预测地降级")
    stages = [
        ("01", "Live Snapshot", "最多 32 个\nLive Eligible 测点"),
        ("02", "Response Field", "25×9 网格\n归一化响应场"),
        ("03", "Frame Assemble", "10 KB UTF-8\n确定性降级"),
        ("04", "WebSocket", "每客户端有界队列\n慢客户端隔离"),
    ]
    for index, (number, title, detail) in enumerate(stages):
        x = 0.72 + index * 3.02
        add_rect(slide, x, 1.78, 2.62, 1.30, fill=WHITE, line=LINE)
        add_text(slide, x + 0.14, 1.90, 0.35, 0.20, number, size=8.5, bold=True, color=TEAL)
        add_text(slide, x + 0.14, 2.15, 2.30, 0.25, title, size=12.5, bold=True, color=INK)
        add_text(slide, x + 0.14, 2.52, 2.25, 0.42, detail, size=8.2, color=MUTED)
        if index < 3:
            add_right_arrow(slide, x + 2.68, 2.36, w=0.23, h=0.16)

    add_rect(slide, 0.72, 3.66, 7.62, 1.82, fill=TEAL_LIGHT, line="9CCAC6")
    add_text(slide, 0.94, 3.82, 2.4, 0.24, "帧预算降级顺序", size=11.5, bold=True, color=TEAL)
    degrade_steps = ["完整帧", "去点元数据", "去压力场", "压缩文本", "最小文本", "移除最旧测点"]
    for index, step in enumerate(degrade_steps):
        x = 0.94 + (index % 3) * 2.40
        y = 4.20 + (index // 3) * 0.50
        add_rect(slide, x, y, 2.14, 0.34, fill=WHITE, line="B9D9D6")
        add_text(slide, x + 0.10, y + 0.06, 1.94, 0.18, step, size=8.2, color=INK, align=PP_ALIGN.CENTER)

    add_rect(slide, 8.58, 3.60, 4.00, 1.98, fill=NAVY, line=None)
    add_text(slide, 8.82, 3.78, 3.35, 0.24, "四道实时闸门", size=10.5, bold=True, color=AMBER)
    gates = [
        ("queue", "每客户端最多 4 帧"),
        ("stale", "帧最大等待 0.5 s"),
        ("slow", "超时或过期即断开"),
    ]
    for index, (key, detail) in enumerate(gates):
        y = 4.16 + index * 0.44
        add_text(slide, 8.82, y, 0.78, 0.20, key, size=9.5, bold=True, color=TEAL_MID)
        add_text(slide, 9.55, y, 2.65, 0.22, detail, size=9.4, color=WHITE)
    add_text(slide, 0.75, 5.88, 11.5, 0.32, "单进程实时循环避免每连接重复生成；原子检查点保证批次、阈值修改和正常停止都可恢复。", size=10.5, color=MUTED)
    add_notes(
        slide,
        "这一页把实时系统拆成四段：快照、响应场、帧组装和广播。"
        "这一页看四个运行环节：快照、响应场、帧组装和广播。预算不够时按固定顺序降级，慢客户端单独隔离。",
    )

    # ------------------------------------------------------------------
    # Slide 7: Results
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 7, source="来源：benchmarks/runs/20261103T145921Z/acceptance.md（本机单进程、回环网络）")
    add_slide_title(slide, "端到端性能通过，误报控制有数据支撑")
    add_rect(slide, 10.60, 1.04, 2.06, 0.34, fill=GREEN_LIGHT, line="B9D7C7")
    add_text(slide, 10.70, 1.11, 1.86, 0.18, "ALL GATES PASSED", size=8.4, bold=True, color=GREEN, align=PP_ALIGN.CENTER)
    metrics = [
        ("393.76 ms", "10,000 条批量摄入"),
        ("7.47 ms", "常规查询 p95"),
        ("1.04 ms", "历史快照 p95"),
        ("11.45 ms", "三层检测 p95"),
        ("152.65", "API QPS"),
        ("9.10 ms", "WebSocket 帧延迟 p95"),
    ]
    for index, (value, label) in enumerate(metrics):
        x = 0.72 + (index % 3) * 2.62
        y = 1.72 + (index // 3) * 1.50
        add_rect(slide, x, y, 2.36, 1.20, fill=WHITE, line=LINE)
        add_rect(slide, x, y, 0.05, 1.20, fill=TEAL if index % 2 == 0 else AMBER, line=None, radius=False)
        add_text(slide, x + 0.17, y + 0.17, 2.00, 0.33, value, size=18.5, bold=True, color=NAVY)
        add_text(slide, x + 0.17, y + 0.66, 2.02, 0.28, label, size=8.6, color=MUTED)

    add_rect(slide, 8.58, 1.70, 4.00, 3.70, fill=NAVY, line=None)
    add_text(slide, 8.84, 1.92, 3.35, 0.24, "合成验证集", size=10.5, bold=True, color=AMBER)
    add_text(slide, 8.84, 2.34, 3.25, 0.55, "99.24%", size=30, bold=True, color=WHITE)
    add_text(slide, 8.86, 2.92, 3.10, 0.22, "准确率", size=9.5, color="AFC2C7")
    add_text(slide, 8.84, 3.36, 3.25, 0.45, "0.23%", size=22, bold=True, color=TEAL_MID)
    add_text(slide, 8.86, 3.78, 3.10, 0.22, "误报率", size=9.5, color="AFC2C7")
    add_text(slide, 8.84, 4.22, 3.15, 0.70, "24 h / 8 测点 / 69,120 条读数\n1,440 个一分钟窗口", size=8.3, color="AFC2C7", line_spacing=1.1)
    add_text(slide, 0.74, 5.82, 12.0, 0.55, "数据口径：本机单进程验收，不是跨机器 benchmark；准确率与误报率来自合成数据，真实工程精度需现场标定。", size=9.4, color=MUTED)
    add_text(slide, 0.74, 6.34, 12.0, 0.28, "同时：384 项 pytest 全通过；10/10 WebSocket 客户端；所有验收门槛通过。", size=9.2, color=TEAL)
    add_notes(
        slide,
        "这一页只讲通过的门槛和口径：10,000 条摄入、查询、快照、检测、API 和 WebSocket 全部通过。"
        "右侧的 99.24% 和 0.23% 是合成验证集结果，必须和“合成数据”一起说。",
    )

    # ------------------------------------------------------------------
    # Slide 8: VBA benchmark
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 8, source="来源：benchmarks/vba/enhanced-v1.json / enhanced-v1.md；录制级 5 折分层评估")
    add_slide_title(slide, "公开数据证明融合价值，但不把离线结果说成线上精度")
    add_rect(slide, 0.72, 1.68, 7.48, 4.35, fill=WHITE, line=LINE)
    add_text(slide, 0.96, 1.86, 4.2, 0.25, "VBA 录音级指标", size=11, bold=True, color=TEAL)
    add_text(slide, 0.96, 2.14, 3.2, 0.20, "准确率 / 越高越好", size=8.8, bold=True, color=MUTED)
    add_text(slide, 0.96, 2.45, 0.84, 0.22, "原始", size=8.5, color=MUTED)
    add_text(slide, 1.70, 2.43, 0.86, 0.24, "47.06%", size=9.6, bold=True, color=MUTED, align=PP_ALIGN.RIGHT)
    add_rect(slide, 2.66, 2.41, 2.26, 0.30, fill="AEB8BD", line=None, radius=False)
    add_text(slide, 0.96, 2.87, 0.84, 0.22, "增强", size=8.5, color=TEAL)
    add_text(slide, 1.70, 2.85, 0.86, 0.24, "97.06%", size=9.6, bold=True, color=TEAL, align=PP_ALIGN.RIGHT)
    add_rect(slide, 2.66, 2.83, 4.66, 0.30, fill=TEAL, line=None, radius=False)
    line = slide.shapes.add_connector(1, Inches(0.96), Inches(3.32), Inches(7.58), Inches(3.32))
    line.line.color.rgb = rgb(LINE)
    line.line.width = Pt(0.8)
    add_text(slide, 0.96, 3.47, 3.2, 0.20, "误报率 / 越低越好", size=8.8, bold=True, color=MUTED)
    add_text(slide, 0.96, 3.78, 0.84, 0.22, "原始", size=8.5, color=MUTED)
    add_text(slide, 1.70, 3.76, 0.86, 0.24, "100%", size=9.6, bold=True, color=RED, align=PP_ALIGN.RIGHT)
    add_rect(slide, 2.66, 3.74, 4.66, 0.30, fill="D46A54", line=None, radius=False)
    add_text(slide, 0.96, 4.20, 0.84, 0.22, "增强", size=8.5, color=AMBER)
    add_text(slide, 1.70, 4.18, 0.86, 0.24, "2.78%", size=9.6, bold=True, color=AMBER, align=PP_ALIGN.RIGHT)
    add_rect(slide, 2.66, 4.16, 0.18, 0.30, fill=AMBER, line=None, radius=False)
    add_text(slide, 2.94, 4.16, 1.3, 0.30, "0.0278", size=8.3, color=AMBER, valign=MSO_ANCHOR.MIDDLE)
    add_text(slide, 0.96, 4.74, 6.7, 0.55, "增强分类准确率 0.9706、F1 0.9688；原始告警链路在该数据集上误报率 1.0000，说明仅靠固定阈值不足。", size=8.7, color=MUTED)
    add_text(slide, 0.96, 5.28, 6.72, 0.56, "口径：68 条录音 / 8 加速度通道 / 5 折录音级划分\n模型：StandardScaler + LogisticRegression（离线监督融合）", size=8.8, color=INK, line_spacing=1.15)

    add_rect(slide, 8.50, 1.68, 4.12, 4.35, fill=NAVY, line=None)
    add_text(slide, 8.76, 1.92, 3.45, 0.25, "必须同时说清楚", size=10.5, bold=True, color=AMBER)
    facts = [
        ("离线", "录音级分类，不是线上逐读数告警"),
        ("单模态", "仅加速度通道，不覆盖应变/位移/温度"),
        ("非预测", "不是结构应力或位移预测精度"),
    ]
    for index, (label, detail) in enumerate(facts):
        y = 2.45 + index * 0.88
        add_text(slide, 8.78, y, 1.0, 0.20, label, size=9.2, bold=True, color=TEAL_MID)
        add_text(slide, 8.78, y + 0.27, 3.40, 0.35, detail, size=9.2, color=WHITE)
    add_text(slide, 8.78, 5.22, 3.40, 0.40, "结论：融合有价值，但不能替换实时链路指标。", size=8.4, color="AFC2C7")
    add_notes(
        slide,
        "这一页主动展示一个看起来不完美的原始链路结果，再说明融合增强的收益。"
        "答辩时要主动说明：这是录音级离线分类，不能当作线上实时逐读数精度。",
    )

    # ------------------------------------------------------------------
    # Slide 9: Innovation
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 9, source="来源：技术文档第 7 章；创新点为系统组合与工程落地，不主张单项基础算法首创")
    add_slide_title(
        slide,
        "难点在五层约束同时成立",
        subtitle="创新落在这些约束的组合方式上，模型只是其中一层。",
    )
    layers = [
        ("01", "物理约束", "单位、阈值来源、审批状态、测点 override", TEAL_LIGHT, "8FC3BF", TEAL),
        ("02", "模型证据", "投票、置信度、认知度、不确定性", AMBER_LIGHT, "E6C98E", "8A6219"),
        ("03", "空间一致性", "Scene Profile、测点锚点、跨传感器残差", "EEF2F3", LINE, INK),
        ("04", "实时预算", "32 测点、10 KB 帧、慢客户端、原子检查点", WHITE, LINE, "586B73"),
        ("05", "验收证据", "384 tests、数据哈希、VBA 基准、24 h 长稳入口", WHITE, LINE, "586B73"),
    ]
    for index, (number, title, detail, fill, outline, accent) in enumerate(layers):
        y = 1.92 + index * 0.72
        x = 0.72 + index * 0.08
        w = 8.30 - index * 0.08
        add_rect(slide, x, y, w, 0.58, fill=fill, line=outline, radius=False, line_width=1.0)
        add_rect(slide, x, y, 0.50, 0.58, fill=accent, line=None, radius=False)
        add_text(slide, x + 0.10, y + 0.17, 0.30, 0.20, number, size=8.2, bold=True, color=WHITE if accent in (TEAL, "8A6219", INK, "586B73") else INK, align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.64, y + 0.09, 2.0, 0.24, title, size=11.4, bold=True, color=INK)
        add_text(slide, x + 2.62, y + 0.12, w - 2.82, 0.24, detail, size=8.9, color=MUTED)

    add_rect(slide, 9.32, 1.92, 3.22, 3.50, fill=NAVY, line=None, radius=False)
    add_text(slide, 9.56, 2.12, 2.70, 0.24, "工程结果", size=10.5, bold=True, color=AMBER)
    outcomes = [
        ("告警可追问", "投票、特征、空间状态和阈值都能回查"),
        ("结论可重跑", "测试、数据哈希与验收命令留在仓库"),
        ("组件可替换", "检测器、模型存储、检查点都有明确边界"),
    ]
    for index, (title, detail) in enumerate(outcomes):
        y = 2.55 + index * 0.90
        add_text(slide, 9.56, y, 2.70, 0.26, title, size=12.0, bold=True, color=WHITE)
        add_text(slide, 9.56, y + 0.30, 2.70, 0.42, detail, size=8.8, color="AFC2C7")
    add_text(slide, 0.72, 5.98, 11.9, 0.48, "本页列的是工程组合层面的改进，不对基础算法主张首创。", size=9.6, color=MUTED)
    add_notes(
        slide,
        "这一页用五层约束说明工程难点：物理语义、模型证据、空间一致性、实时预算和验收证据必须同时成立。"
        "创新点在这些约束的组合方式，不在某个模型名字。右侧三条结果分别对应可解释、可复现和可替换。",
    )

    # ------------------------------------------------------------------
    # Slide 10: Boundaries + roadmap
    # ------------------------------------------------------------------
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide)
    add_brand(slide, 10, source="来源：技术文档第 9 章；路线为后续工程化计划")
    add_slide_title(slide, "先讲清不能证明什么，再谈下一步", subtitle="当前边界、近期补强与工程化路线")
    add_rect(slide, 0.72, 1.72, 5.55, 3.98, fill=NAVY, line=None)
    add_text(slide, 0.98, 1.94, 4.95, 0.26, "当前不宣称", size=10.5, bold=True, color=AMBER)
    limits = [
        "真实桥梁工程精度",
        "正式工程阈值",
        "线上逐读数 97% 精度",
        "已完成 24 小时长稳",
        "多 worker / 认证 / 多租户",
    ]
    for index, item in enumerate(limits):
        y = 2.42 + index * 0.56
        add_text(slide, 1.00, y, 0.30, 0.22, "×", size=14, bold=True, color="D46A54")
        add_text(slide, 1.34, y - 0.01, 4.55, 0.28, item, size=12.0, color=WHITE)

    add_text(slide, 6.62, 1.76, 5.9, 0.28, "下一阶段", size=10.5, bold=True, color=TEAL)
    roadmap = [
        ("近期", "24 h 长稳 · 桌面回归 · 前端 code splitting · 现场标定", TEAL),
        ("中期", "MQTT/OPC UA · 时序数据库 · 消息总线 · 认证与 RBAC", AMBER),
        ("长期", "有限元更新 · 传感器优化 · 损伤演化 · 多桥多项目管理", "586B73"),
    ]
    for index, (phase, detail, accent) in enumerate(roadmap):
        y = 2.20 + index * 1.05
        add_text(slide, 6.66, y, 0.62, 0.22, phase, size=11.5, bold=True, color=accent)
        add_rect(slide, 7.32, y + 0.10, 0.06, 0.50, fill=accent, line=None, radius=False)
        add_text(slide, 7.52, y - 0.01, 4.82, 0.55, detail, size=9.6, color=INK)

    add_rect(slide, 0.72, 6.02, 11.96, 0.82, fill=TEAL, line=None)
    add_text(slide, 1.02, 6.15, 2.8, 0.42, "谢谢 / Q&A", size=20, bold=True, color=WHITE)
    add_text(slide, 4.30, 6.18, 7.9, 0.42, "每个告警都带着依据，下一次还能重跑。", size=11.0, color=WHITE, align=PP_ALIGN.RIGHT)
    add_notes(
        slide,
        "收尾先讲边界，再讲路线。当前不宣称真实工程精度、正式阈值、线上 97% 精度、完整 24 小时长稳和多租户能力。"
        "下一步从长稳、现场标定、工业协议和生产架构逐步推进。最后用一句话收束：让数据成为可解释的工程证据。",
    )

    prs.core_properties.title = "桥梁数字孪生结构健康监测平台答辩PPT"
    prs.core_properties.subject = "工程场景数字化 / 数字孪生 / 结构健康监测"
    prs.core_properties.author = "Bridge Digital Twin Platform"
    prs.core_properties.keywords = "桥梁, 数字孪生, SHM, 异常检测, 工程答辩"
    return prs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    presentation = build_deck()
    presentation.save(OUTPUT)
    print(f"PPTX written: {OUTPUT}")


if __name__ == "__main__":
    main()
