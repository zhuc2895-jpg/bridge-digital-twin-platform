# -*- coding: utf-8 -*-
"""生成项目计划书Word文档"""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

doc = Document()

# 设置默认字体
doc.styles['Normal'].font.name = '宋体'
doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
doc.styles['Normal'].font.size = Pt(12)

# 页边距
for section in doc.sections:
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

def add_title(text, level=1):
    """添加标题"""
    p = doc.add_heading('', level=level)
    run = p.add_run(text)
    run.font.name = '黑体'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    if level == 1:
        run.font.size = Pt(16)
    elif level == 2:
        run.font.size = Pt(14)
    else:
        run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0, 0, 0)
    return p

def add_para(text, indent=True, bold=False):
    """添加正文段落"""
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Pt(24)
    p.paragraph_format.line_spacing = 1.5
    run = p.add_run(text)
    run.font.name = '宋体'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    run.font.size = Pt(12)
    run.bold = bold
    return p

# ===== 封面 =====
for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('项目计划书')
run.font.name = '黑体'
run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
run.font.size = Pt(36)
run.bold = True

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('数字孪生+桥梁结构健康监测与预警系统')
run.font.name = '黑体'
run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
run.font.size = Pt(22)

for _ in range(6):
    doc.add_paragraph()

info_items = [
    ('项目名称：', '数字孪生+桥梁结构健康监测与预警系统'),
    ('参赛赛道：', '虚拟仿真赛道（工程场景数字化）'),
    ('申报日期：', '2026年8月'),
]
for label, value in info_items:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(label + value)
    run.font.name = '宋体'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    run.font.size = Pt(14)

doc.add_page_break()

# ===== 一、项目概述 =====
add_title('一、项目概述', 1)
add_para('本项目以山西浍河大桥为工程对象，面向桥梁运维阶段健康监测需求，构建一套基于数字孪生技术的桥梁结构健康监测与预警系统。系统融合BIM三维建模、多源传感器数据实时采集、三层递进式人工智能异常检测算法，实现桥梁结构状态的三维可视化、智能分级预警、历史数据回放与监测报告自动生成。')
add_para('系统采用前后端分离架构：前端基于Vue3与Three.js实现桥梁数字孪生体的交互式三维展示，后端基于FastAPI构建高性能数据处理与AI推理服务。通过物理阈值快速筛查、STALWART-inspired时序突变检测、GAN-AE分布漂移识别与Isolation Forest离群点投票的三层检测架构，将桥梁异常响应时间从传统人工巡检的天级压缩至分钟级，关键构件异常预测准确率达90%以上。')

# ===== 二、项目背景与意义 =====
add_title('二、项目背景与意义', 1)

add_title('2.1 行业背景', 2)
add_para('截至2025年底，我国公路桥梁总量已超过90万座，其中大量桥梁进入设计使用年限中后期，结构老化、病害累积问题日益突出。传统桥梁健康监测主要依赖人工定期巡检与单点阈值报警，存在巡检效率低、漏检率高、异常响应滞后、数据利用率低等痛点，难以满足大规模桥梁群精细化运维需求。')
add_para('数字孪生技术通过构建与物理桥梁实时映射的虚拟模型，为桥梁全生命周期管理提供了新的技术路径。将数字孪生与人工智能异常检测相结合，能够实现桥梁结构状态的实时感知、智能诊断与主动预警，对提升桥梁运维智能化水平、保障桥梁运营安全具有重要工程价值。')

add_title('2.2 项目意义', 2)
add_para('（1）工程价值：实现桥梁多源监测数据的统一接入与智能分析，将异常响应时间从天级压缩至分钟级，减少30%以上不必要的实地巡检，降低运维成本。')
add_para('（2）技术价值：提出三层递进式AI异常检测架构，融合物理规则与数据驱动方法，兼顾检测实时性与准确性，为工程结构健康监测提供可复用的技术方案。')
add_para('（3）社会价值：提升桥梁运营安全保障能力，降低桥梁突发事故风险，为交通基础设施数字化转型提供实践参考。')

# ===== 三、项目目标 =====
add_title('三、项目目标', 1)

add_title('3.1 总体目标', 2)
add_para('构建一套可运行、可演示、可推广的桥梁数字孪生健康监测系统，实现桥梁结构状态的三维可视化、实时监测、智能预警与历史回溯，形成完整的工程场景数字化解决方案。')

add_title('3.2 具体目标', 2)
add_para('（1）完成浍河大桥BIM模型构建与轻量化处理，实现Web端流畅加载与交互式浏览。')
add_para('（2）实现应变、位移、加速度、温度四类传感器数据的实时接入与可视化展示。')
add_para('（3）开发三层递进式AI异常检测算法，关键构件异常预测准确率≥90%，误报率≤10%。')
add_para('（4）实现黄/橙/红三级智能预警，异常响应时间≤1分钟。')
add_para('（5）支持历史数据回放（1x~16x倍速）与监测报告自动导出。')
add_para('（6）系统支持8个以上传感器并发接入，前端页面加载时间≤3秒。')

# ===== 四、技术方案 =====
add_title('四、技术方案', 1)

add_title('4.1 系统总体架构', 2)
add_para('系统采用前后端分离的三层架构：')
add_para('（1）数据层：基于内存数据引擎实现传感器数据的高速读写与全量历史存储，支持滚动窗口与降采样查询。')
add_para('（2）服务层：基于FastAPI构建RESTful API与WebSocket实时推送服务，集成AI异常检测引擎与告警管理模块。')
add_para('（3）展示层：基于Vue3与Three.js构建数字孪生前端，实现三维模型渲染、传感器状态映射、趋势图表与告警面板。')

add_title('4.2 数字孪生建模', 2)
add_para('采用Autodesk Revit进行浍河大桥参数化BIM建模，涵盖主梁、索塔、拉索、桥墩等主要结构构件。通过glTF格式转换与网格简化实现模型轻量化，压缩比达70%以上，确保Web端流畅加载。Three.js渲染引擎支持鼠标拖拽旋转、滚轮缩放、右键平移等交互操作，传感器以彩色球体标注于模型对应位置，颜色随结构状态实时变化。')

add_title('4.3 三层递进式AI异常检测', 2)
add_para('系统采用"物理阈值—AI多模型投票—特征仲裁"三层递进式检测架构：')
add_para('第一层：物理阈值快速筛查。基于桥梁设计规范与历史统计数据，设置应变、位移、加速度、温度四类传感器的黄/橙/红三级阈值，实现毫秒级异常初筛。')
add_para('第二层：AI多模型投票。集成STALWART-inspired时序突变检测（EMA快慢线偏差）、GAN-AE生成对抗自编码器分布漂移识别、Isolation Forest孤立森林离群点检测三个模型，采用多数投票机制输出异常判定，单模型置信度≥0.7时触发预警。')
add_para('第三层：多窗口特征仲裁。对AI模型判定的异常，进一步提取滑动窗口内的均值偏移、方差变化、趋势斜率等特征进行二次确认，有效降低误报率。')

add_title('4.4 实时数据传输', 2)
add_para('后端通过WebSocket向前端实时推送传感器数据与告警信息，推送频率为1Hz。数据引擎采用双缓冲机制，实时数据写入滚动窗口（最近500条），全量数据写入历史存储（最多10万条/传感器），兼顾实时性与历史回溯能力。')

add_title('4.5 历史回放与报告生成', 2)
add_para('系统支持任意历史时段的数据回放，提供1x/2x/4x/8x/16x五档倍速，回放过程中传感器数值、3D模型颜色、趋势图表、告警列表同步更新。监测报告自动生成HTML格式，包含监测概况、传感器状态、告警记录、系统运行状态等内容，支持一键打印导出为PDF。')

# ===== 五、创新点 =====
add_title('五、项目创新点', 1)
add_para('（1）三层递进式检测架构：首创"物理阈值初筛—AI多模型投票—特征仲裁确认"的三层检测流程，兼顾检测速度与准确性，解决单一模型误报率高的问题。')
add_para('（2）数字孪生与AI深度融合：将AI检测结果实时映射至三维数字孪生体，实现异常位置的空间定位与可视化，改变传统监测系统"数据与空间脱节"的局限。')
add_para('（3）全流程闭环管理：从实时监测、智能预警、历史回放到报告生成，形成桥梁健康监测的完整闭环，支持工程场景下的实际运维流程。')
add_para('（4）轻量化Web端部署：基于glTF模型压缩与浏览器端WebGL渲染，无需安装专业软件即可在普通PC浏览器中流畅运行，降低系统部署与使用门槛。')

# ===== 六、实施计划 =====
add_title('六、实施计划', 1)

table = doc.add_table(rows=6, cols=4)
table.style = 'Table Grid'
table.alignment = WD_TABLE_ALIGNMENT.CENTER

headers = ['阶段', '时间', '主要任务', '交付物']
for i, h in enumerate(headers):
    cell = table.rows[0].cells[i]
    cell.text = h
    for p in cell.paragraphs:
        for run in p.runs:
            run.bold = True
            run.font.name = '宋体'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

stages = [
    ('第一阶段', '2026.07-2026.08', '需求分析、BIM建模、系统架构设计、前后端框架搭建', '需求文档、BIM模型、系统原型'),
    ('第二阶段', '2026.08-2026.09', '数据引擎开发、AI检测算法实现、三维可视化开发', '数据引擎、AI模块、3D展示模块'),
    ('第三阶段', '2026.09-2026.10', '实时通信、告警管理、历史回放、报告生成功能开发', '完整功能系统'),
    ('第四阶段', '2026.10-2026.11', '系统集成测试、验证数据生成、算法调优、性能优化', '测试报告、优化后系统'),
    ('第五阶段', '2026.11-2026.12', '文档撰写、答辩材料准备、比赛展示优化', '项目文档、演示视频、答辩PPT'),
]
for i, (stage, time, task, deliverable) in enumerate(stages, 1):
    row = table.rows[i].cells
    row[0].text = stage
    row[1].text = time
    row[2].text = task
    row[3].text = deliverable

doc.add_paragraph()

# ===== 七、预期成果 =====
add_title('七、预期成果', 1)
add_para('（1）一套可运行的桥梁数字孪生健康监测系统（含前端、后端、AI检测模块）。')
add_para('（2）浍河大桥轻量化BIM模型（glTF格式，支持Web端加载）。')
add_para('（3）三层递进式AI异常检测算法实现与验证报告。')
add_para('（4）24小时桥梁监测验证数据集（含3组典型损伤工况）。')
add_para('（5）项目技术文档、用户手册与答辩展示材料。')
add_para('（6）预期申请软件著作权1项，发表学术论文1篇。')

# ===== 八、团队分工 =====
add_title('八、团队分工', 1)

table2 = doc.add_table(rows=5, cols=3)
table2.style = 'Table Grid'
table2.alignment = WD_TABLE_ALIGNMENT.CENTER

headers2 = ['角色', '人数', '主要职责']
for i, h in enumerate(headers2):
    cell = table2.rows[0].cells[i]
    cell.text = h
    for p in cell.paragraphs:
        for run in p.runs:
            run.bold = True

members = [
    ('项目负责人', '1人', '项目整体规划、技术方案设计、进度管理、答辩汇报'),
    ('BIM与前端开发', '1-2人', '桥梁BIM建模、模型轻量化、Three.js三维可视化、前端界面开发'),
    ('后端与算法开发', '1-2人', '数据引擎开发、API设计、AI异常检测算法实现、系统集成'),
    ('测试与文档', '1人', '验证数据生成、系统测试、算法性能评估、文档撰写'),
]
for i, (role, num, duty) in enumerate(members, 1):
    row = table2.rows[i].cells
    row[0].text = role
    row[1].text = num
    row[2].text = duty

doc.add_paragraph()

# ===== 九、经费预算 =====
add_title('九、经费预算', 1)

table3 = doc.add_table(rows=6, cols=3)
table3.style = 'Table Grid'
table3.alignment = WD_TABLE_ALIGNMENT.CENTER

headers3 = ['预算科目', '金额（元）', '说明']
for i, h in enumerate(headers3):
    cell = table3.rows[0].cells[i]
    cell.text = h
    for p in cell.paragraphs:
        for run in p.runs:
            run.bold = True

budget = [
    ('软件与云服务', '2000', '云服务器租赁、域名、SSL证书'),
    ('数据采集设备', '3000', '传感器、数据采集卡（如需实物验证）'),
    ('资料与文献', '500', '专业书籍、文献检索、标准规范'),
    ('差旅与调研', '1500', '桥梁现场调研、数据采集'),
    ('其他', '1000', '打印、耗材、不可预见费用'),
]
for i, (item, amount, note) in enumerate(budget, 1):
    row = table3.rows[i].cells
    row[0].text = item
    row[1].text = amount
    row[2].text = note

doc.add_paragraph()
add_para('预算合计：8000元。', bold=True)

# ===== 十、风险分析与应对 =====
add_title('十、风险分析与应对', 1)
add_para('（1）技术风险：AI算法在真实桥梁数据上的检测效果可能不及预期。应对措施：采用物理阈值与AI相结合的混合策略，确保至少第一层检测可靠；同时使用仿真验证数据进行充分调优。')
add_para('（2）性能风险：三维模型与大量实时数据可能导致前端卡顿。应对措施：采用glTF模型压缩、数据降采样、WebGL渲染优化等手段，确保页面流畅运行。')
add_para('（3）进度风险：团队成员非计算机专业，开发进度可能滞后。应对措施：制定详细里程碑计划，采用敏捷开发模式，每周同步进度，必要时寻求指导教师与技术顾问支持。')
add_para('（4）数据风险：缺乏真实桥梁监测数据。应对措施：基于桥梁力学特性与历史文献生成高仿真验证数据，覆盖正常工况与典型损伤工况，确保算法验证的科学性。')

# ===== 保存 =====
PROJECT_ROOT = Path(__file__).resolve().parents[2]
output_path = PROJECT_ROOT / 'assets' / 'planning' / 'project-plan.docx'
output_path.parent.mkdir(parents=True, exist_ok=True)
doc.save(output_path)
print(f'文档已生成: {output_path}')
