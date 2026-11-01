# -*- coding: utf-8 -*-
"""纯标准库生成Word文档 - 修复版"""
import zipfile
import os
from pathlib import Path
from xml.sax.saxutils import escape

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / 'assets' / 'planning' / 'project-plan.docx'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

content = [
    ('title', '项目计划书'),
    ('subtitle', '数字孪生+桥梁结构健康监测与预警系统'),
    ('blank', ''),
    ('h1', '一、项目概述'),
    ('p', '本项目以大跨径拉索桥为工程对象，面向桥梁运维阶段健康监测需求，构建一套基于数字孪生技术的桥梁结构健康监测与预警系统。系统融合BIM三维建模、多源传感器数据实时采集、三层递进式人工智能异常检测算法，实现桥梁结构状态的三维可视化、智能分级预警、历史数据回放与监测报告自动生成。'),
    ('p', '系统采用前后端分离架构：前端基于Vue3与Three.js实现桥梁数字孪生体的交互式三维展示，后端基于FastAPI构建高性能数据处理与AI推理服务。通过物理阈值快速筛查、STALWART-inspired时序突变检测、GAN-AE分布漂移识别与Isolation Forest离群点投票的三层检测架构，将桥梁异常响应时间从传统人工巡检的天级压缩至分钟级，关键构件异常预测准确率达90%以上。'),
    ('h1', '二、项目背景与意义'),
    ('h2', '2.1 行业背景'),
    ('p', '截至2025年底，我国公路桥梁总量已超过90万座，其中大跨径拉索桥（斜拉桥、悬索桥）数量居世界首位。拉索桥结构体系复杂，拉索、索塔、主梁等关键构件在长期荷载与环境作用下易产生疲劳损伤、腐蚀退化等问题，一旦发生病害将严重威胁运营安全。传统桥梁健康监测主要依赖人工定期巡检与单点阈值报警，存在巡检效率低、漏检率高、异常响应滞后、数据利用率低等痛点，难以满足拉索桥精细化运维需求。'),
    ('p', '数字孪生技术通过构建与物理桥梁实时映射的虚拟模型，为桥梁全生命周期管理提供了新的技术路径。将数字孪生与人工智能异常检测相结合，能够实现桥梁结构状态的实时感知、智能诊断与主动预警，对提升拉索桥运维智能化水平、保障桥梁运营安全具有重要工程价值。'),
    ('h2', '2.2 项目意义'),
    ('p', '（1）工程价值：实现拉索桥多源监测数据的统一接入与智能分析，将异常响应时间从天级压缩至分钟级，减少30%以上不必要的实地巡检，降低运维成本。'),
    ('p', '（2）技术价值：提出三层递进式AI异常检测架构，融合物理规则与数据驱动方法，兼顾检测实时性与准确性，为拉索桥结构健康监测提供可复用的技术方案。'),
    ('p', '（3）社会价值：提升拉索桥运营安全保障能力，降低桥梁突发事故风险，为交通基础设施数字化转型提供实践参考。'),
    ('h1', '三、项目目标'),
    ('h2', '3.1 总体目标'),
    ('p', '构建一套可运行、可演示、可推广的拉索桥数字孪生健康监测系统，实现桥梁结构状态的三维可视化、实时监测、智能预警与历史回溯，形成完整的工程场景数字化解决方案。'),
    ('h2', '3.2 具体目标'),
    ('p', '（1）完成拉索桥BIM模型构建与轻量化处理，实现Web端流畅加载与交互式浏览。'),
    ('p', '（2）实现应变、位移、加速度、温度四类传感器数据的实时接入与可视化展示。'),
    ('p', '（3）开发三层递进式AI异常检测算法，关键构件异常预测准确率不低于90%，误报率不高于10%。'),
    ('p', '（4）实现黄/橙/红三级智能预警，异常响应时间不超过1分钟。'),
    ('p', '（5）支持历史数据回放（1x至16x倍速）与监测报告自动导出。'),
    ('p', '（6）系统支持8个以上传感器并发接入，前端页面加载时间不超过3秒。'),
    ('h1', '四、技术方案'),
    ('h2', '4.1 系统总体架构'),
    ('p', '系统采用前后端分离的三层架构：'),
    ('p', '数据层：基于内存数据引擎实现传感器数据的高速读写与全量历史存储，支持滚动窗口与降采样查询。'),
    ('p', '服务层：基于FastAPI构建RESTful API与WebSocket实时推送服务，集成AI异常检测引擎与告警管理模块。'),
    ('p', '展示层：基于Vue3与Three.js构建数字孪生前端，实现三维模型渲染、传感器状态映射、趋势图表与告警面板。'),
    ('h2', '4.2 数字孪生建模'),
    ('p', '采用Autodesk Revit进行拉索桥参数化BIM建模，涵盖主梁、索塔、拉索、桥墩等主要结构构件。通过glTF格式转换与网格简化实现模型轻量化，压缩比达70%以上，确保Web端流畅加载。Three.js渲染引擎支持鼠标拖拽旋转、滚轮缩放、右键平移等交互操作，传感器以彩色球体标注于模型对应位置（拉索、索塔、主梁关键截面），颜色随结构状态实时变化。'),
    ('h2', '4.3 三层递进式AI异常检测'),
    ('p', '系统采用物理阈值、AI多模型投票、特征仲裁三层递进式检测架构：'),
    ('p', '第一层：物理阈值快速筛查。基于桥梁设计规范与历史统计数据，设置应变、位移、加速度、温度四类传感器的黄/橙/红三级阈值，实现毫秒级异常初筛。'),
    ('p', '第二层：AI多模型投票。集成STALWART-inspired时序突变检测（EMA快慢线偏差）、GAN-AE生成对抗自编码器分布漂移识别、Isolation Forest孤立森林离群点检测三个模型，采用多数投票机制输出异常判定，单模型置信度不低于0.7时触发预警。'),
    ('p', '第三层：多窗口特征仲裁。对AI模型判定的异常，进一步提取滑动窗口内的均值偏移、方差变化、趋势斜率等特征进行二次确认，有效降低误报率。'),
    ('h2', '4.4 实时数据传输'),
    ('p', '后端通过WebSocket向前端实时推送传感器数据与告警信息，推送频率为1Hz。数据引擎采用双缓冲机制，实时数据写入滚动窗口（最近500条），全量数据写入历史存储（最多10万条每传感器），兼顾实时性与历史回溯能力。'),
    ('h2', '4.5 历史回放与报告生成'),
    ('p', '系统支持任意历史时段的数据回放，提供1x/2x/4x/8x/16x五档倍速，回放过程中传感器数值、3D模型颜色、趋势图表、告警列表同步更新。监测报告自动生成HTML格式，包含监测概况、传感器状态、告警记录、系统运行状态等内容，支持一键打印导出为PDF。'),
    ('h1', '五、项目创新点'),
    ('p', '（1）三层递进式检测架构：首创物理阈值初筛、AI多模型投票、特征仲裁确认的三层检测流程，兼顾检测速度与准确性，解决单一模型误报率高的问题。'),
    ('p', '（2）数字孪生与AI深度融合：将AI检测结果实时映射至三维数字孪生体，实现拉索、索塔等异常位置的空间定位与可视化，改变传统监测系统数据与空间脱节的局限。'),
    ('p', '（3）全流程闭环管理：从实时监测、智能预警、历史回放到报告生成，形成拉索桥健康监测的完整闭环，支持工程场景下的实际运维流程。'),
    ('p', '（4）轻量化Web端部署：基于glTF模型压缩与浏览器端WebGL渲染，无需安装专业软件即可在普通PC浏览器中流畅运行，降低系统部署与使用门槛。'),
    ('h1', '六、实施计划'),
    ('table', {
        'headers': ['阶段', '时间', '主要任务', '交付物'],
        'rows': [
            ['第一阶段', '2026.07-2026.08', '需求分析、拉索桥BIM建模、系统架构设计、前后端框架搭建', '需求文档、BIM模型、系统原型'],
            ['第二阶段', '2026.08-2026.09', '数据引擎开发、AI检测算法实现、三维可视化开发', '数据引擎、AI模块、3D展示模块'],
            ['第三阶段', '2026.09-2026.10', '实时通信、告警管理、历史回放、报告生成功能开发', '完整功能系统'],
            ['第四阶段', '2026.10-2026.11', '系统集成测试、验证数据生成、算法调优、性能优化', '测试报告、优化后系统'],
            ['第五阶段', '2026.11-2026.12', '文档撰写、答辩材料准备、比赛展示优化', '项目文档、演示视频、答辩PPT'],
        ]
    }),
    ('h1', '七、预期成果'),
    ('p', '（1）一套可运行的拉索桥数字孪生健康监测系统（含前端、后端、AI检测模块）。'),
    ('p', '（2）拉索桥轻量化BIM模型（glTF格式，支持Web端加载）。'),
    ('p', '（3）三层递进式AI异常检测算法实现与验证报告。'),
    ('p', '（4）24小时桥梁监测验证数据集（含3组典型损伤工况）。'),
    ('p', '（5）项目技术文档、用户手册与答辩展示材料。'),
    ('p', '（6）预期申请软件著作权1项，发表学术论文1篇。'),
    ('h1', '八、团队分工'),
    ('table', {
        'headers': ['角色', '人数', '主要职责'],
        'rows': [
            ['项目负责人', '1人', '项目整体规划、技术方案设计、进度管理、答辩汇报'],
            ['BIM与前端开发', '1-2人', '拉索桥BIM建模、模型轻量化、Three.js三维可视化、前端界面开发'],
            ['后端与算法开发', '1-2人', '数据引擎开发、API设计、AI异常检测算法实现、系统集成'],
            ['测试与文档', '1人', '验证数据生成、系统测试、算法性能评估、文档撰写'],
        ]
    }),
    ('h1', '九、经费预算'),
    ('table', {
        'headers': ['预算科目', '金额（元）', '说明'],
        'rows': [
            ['软件与云服务', '2000', '云服务器租赁、域名、SSL证书'],
            ['数据采集设备', '3000', '传感器、数据采集卡（如需实物验证）'],
            ['资料与文献', '500', '专业书籍、文献检索、标准规范'],
            ['差旅与调研', '1500', '桥梁现场调研、数据采集'],
            ['其他', '1000', '打印、耗材、不可预见费用'],
            ['合计', '8000', ''],
        ]
    }),
    ('h1', '十、风险分析与应对'),
    ('p', '（1）技术风险：AI算法在真实桥梁数据上的检测效果可能不及预期。应对措施：采用物理阈值与AI相结合的混合策略，确保至少第一层检测可靠；同时使用仿真验证数据进行充分调优。'),
    ('p', '（2）性能风险：三维模型与大量实时数据可能导致前端卡顿。应对措施：采用glTF模型压缩、数据降采样、WebGL渲染优化等手段，确保页面流畅运行。'),
    ('p', '（3）进度风险：团队成员非计算机专业，开发进度可能滞后。应对措施：制定详细里程碑计划，采用敏捷开发模式，每周同步进度，必要时寻求指导教师与技术顾问支持。'),
    ('p', '（4）数据风险：缺乏真实拉索桥监测数据。应对措施：基于拉索桥力学特性与历史文献生成高仿真验证数据，覆盖正常工况与典型损伤工况（拉索腐蚀、索塔偏移、主梁挠度异常等），确保算法验证的科学性。'),
]

def para(text, bold=False, size=24, align=None, before=0, after=120, indent=True):
    text = escape(text)
    ind = '<w:ind w:firstLine="480"/>' if indent and not align else ''
    jc = f'<w:jc w:val="{align}"/>' if align else ''
    b = '<w:b/><w:bCs/>' if bold else ''
    return f'''<w:p>
<w:pPr><w:spacing w:before="{before}" w:after="{after}" w:line="360" w:lineRule="auto"/>{jc}{ind}
<w:rPr><w:rFonts w:eastAsia="宋体" w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/>{b}</w:rPr></w:pPr>
<w:r><w:rPr><w:rFonts w:eastAsia="宋体" w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/>{b}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'''

def table(headers, rows):
    cols = len(headers)
    cw = int(9000 / cols)
    tblpr = '''<w:tblPr>
<w:tblW w:w="0" w:type="auto"/>
<w:tblBorders>
<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>
</w:tblBorders></w:tblPr>'''
    grid = '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{cw}"/>' for _ in range(cols)) + '</w:tblGrid>'
    def cell(text, bold=False, header=False):
        text = escape(str(text))
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if header else ''
        b = '<w:b/><w:bCs/>' if bold else ''
        return f'''<w:tc><w:tcPr><w:tcW w:w="{cw}" w:type="dxa"/>{shd}</w:tcPr>
<w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>
<w:r><w:rPr><w:rFonts w:eastAsia="宋体" w:ascii="Times New Roman"/><w:sz w:val="20"/><w:szCs w:val="20"/>{b}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:tc>'''
    hrow = '<w:tr>' + ''.join(cell(h, bold=True, header=True) for h in headers) + '</w:tr>'
    drows = ''
    for row in rows:
        istotal = row[0] == '合计'
        drows += '<w:tr>' + ''.join(cell(c, bold=istotal) for c in row) + '</w:tr>'
    return f'<w:tbl>{tblpr}{grid}{hrow}{drows}</w:tbl><w:p/>'

body = ''
for typ, data in content:
    if typ == 'title':
        body += para(data, bold=True, size=44, align='center', before=3000, after=200, indent=False)
    elif typ == 'subtitle':
        body += para(data, bold=True, size=32, align='center', before=200, after=800, indent=False)
    elif typ == 'h1':
        body += para(data, bold=True, size=28, before=300, after=150, indent=False)
    elif typ == 'h2':
        body += para(data, bold=True, size=24, before=200, after=100, indent=False)
    elif typ == 'p':
        body += para(data, size=24)
    elif typ == 'blank':
        body += '<w:p/>'
    elif typ == 'table':
        body += table(data['headers'], data['rows'])

doc_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
xmlns:v="urn:schemas-microsoft-com:vml"
xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
xmlns:w10="urn:schemas-microsoft-com:office:word"
xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
mc:Ignorable="w14 wp14">
<w:body>{body}
<w:sectPr>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
<w:cols w:space="708"/>
<w:docGrid w:linePitch="360"/>
</w:sectPr>
</w:body></w:document>'''

ct = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>'''

core = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>项目计划书</dc:title>
<dc:creator>项目团队</dc:creator>
<cp:lastModifiedBy>项目团队</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">2026-08-31T00:00:00Z</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">2026-08-31T00:00:00Z</dcterms:modified>
</cp:coreProperties>'''

app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Office Word</Application>
</Properties>'''

with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', ct)
    z.writestr('_rels/.rels', rels)
    z.writestr('word/document.xml', doc_xml)
    z.writestr('word/_rels/document.xml.rels', doc_rels)
    z.writestr('docProps/core.xml', core)
    z.writestr('docProps/app.xml', app)

print(f'生成成功: {OUTPUT}')
print(f'大小: {os.path.getsize(OUTPUT)} 字节')
