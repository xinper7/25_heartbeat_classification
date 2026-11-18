"""Self-contained PDF: saved results, original source attachments and input preview."""
import io,json,os
from pathlib import Path
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime,timezone
from xml.sax.saxutils import escape
import numpy as np
from sqlalchemy import select
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from reportlab.graphics.shapes import Drawing,PolyLine,String,Line
from pypdf import PdfReader,PdfWriter
from .models import Patient,Asset
from .config import get_settings
from .services import serialize_analysis
from .inputs import LEADS

font_path=Path(os.environ.get('ECG_PDF_FONT','C:/Windows/Fonts/simsun.ttc'))
if font_path.is_file():
 pdfmetrics.registerFont(TTFont('ReportCN',str(font_path),subfontIndex=0))
else:
 pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT='ReportCN' if font_path.is_file() else 'STSong-Light'

def report_pdf(db,study,analysis):
 cfg=get_settings();patient=db.get(Patient,study.patient_id);result=serialize_analysis(db,analysis)
 folder=(cfg.storage_dir/'uploads'/study.metadata_json['storage_key']).resolve()
 if not folder.is_relative_to((cfg.storage_dir/'uploads').resolve()):raise ValueError('Invalid input path')
 assets=list(db.scalars(select(Asset).where(Asset.study_id==study.id)))
 styles=getSampleStyleSheet()
 for name in ('Normal','Title','Heading2'):styles[name].fontName=FONT
 styles['Normal'].fontSize=10;styles['Normal'].leading=16;styles['Normal'].wordWrap='CJK'
 styles.add(ParagraphStyle(name='SmallCN',fontName=FONT,fontSize=8,leading=12,wordWrap='CJK'))
 def p(value,style='Normal'):return Paragraph(escape(str(value)).replace('\n','<br/>'),styles[style])
 story=[p('心电分析报告','Title'),p('CARDIO WORKSPACE · 模型辅助分析与人工复核记录'),Spacer(1,12)]
 def section(title):story.extend([Spacer(1,10),p(title,'Heading2')])
 def table(rows,widths):
  t=Table([[p(c) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf4fa')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#cfdae5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t)
 table([['项目','记录'],['检查编号',f'ECG-{study.id:05d} / 分析 #{analysis.id}'],['受检者',f'{patient.name}（{patient.code}）'],['检查名称',study.title],['输入类型','数字心电信号' if study.kind=='signal' else '标准报告图'],['分析时间',str(analysis.created_at)+' UTC'],['报告导出时间',datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')]], [100,415])
 section('模型分类结果')
 table([['类别','名称','模型分数','阈值','判定']]+[[r['code'],r['name'],f"{r['probability']*100:.2f}%",f"{r['threshold']:.2f}",'阳性' if r['positive'] else '阴性'] for r in analysis.predictions],[60,155,100,80,120])
 story.append(p('模型分数不等于患病概率；本结果为多标签辅助分析，不替代专业人员判断。'))
 section('专业复核')
 labels={'returned':'退回补充','resubmitted':'补充后重新送审','confirmed':'确认归档','needs_attention':'归档，需进一步关注'}
 history=result['review_history']
 if not history: story.append(p('尚未复核。本报告包含未复核模型结果。'))
 for event in reversed(history):
  story.append(p(f"{labels.get(event['conclusion'],event['conclusion'])} · {event['reviewer']} · {event['created_at']}\n{event['comment']}"))
 section('模型与处理信息')
 story.append(p(f'模型：{analysis.model_version}\n预处理：{analysis.preprocessing_version}\n推理耗时：{analysis.timings.get("inference_ms",0):.2f} ms\n模型 SHA-256：{analysis.provenance.get("model_sha256","未记录")}','SmallCN'))
 story.append(PageBreak());section('原始输入与数据来源')
 for a in assets:
  story.append(p(f'{a.original_name} · {a.byte_size} 字节\nSHA-256：{a.sha256}','SmallCN'))
 story.append(p('原始上传文件作为附件嵌入本 PDF，使用支持附件的 PDF 阅读器可提取。以下图形用于阅读；数字信号图来自校验/预处理后的物理波形，不替代原始附件。'))
 if study.kind=='image':
  a=assets[0];path=(folder/a.stored_name).resolve()
  if path.parent!=folder:raise ValueError('Invalid source path')
  width,height=ImageReader(str(path)).getSize();factor=min(515/width,540/height)
  story.extend([Spacer(1,12),Image(str(path),width*factor,height*factor)])
 else:
  arr=np.load(folder/'input.npy',allow_pickle=False)
  if arr.shape!=(12,1000):raise ValueError('Unexpected signal shape')
  for group in range(2):
   if group:story.append(PageBreak())
   story.append(p(f'12导联物理波形 · 第{group+1}/2页 · 100 Hz · 10秒 · mV'))
   for lead in range(group*6,group*6+6):
    d=Drawing(515,86);values=arr[lead];amplitude=max(float(np.max(np.abs(values))),.1)
    d.add(String(0,72,f'{LEADS[lead]} | +/-{amplitude:.3f} mV',fontName='Helvetica',fontSize=8))
    for second in range(11):
     x=35+second*47;d.add(Line(x,10,x,66,strokeColor=colors.HexColor('#e3dfe2'),strokeWidth=.4))
    d.add(Line(35,38,505,38,strokeColor=colors.grey,strokeWidth=.4))
    points=[(35+i*470/999,38+float(v)*26/amplitude) for i,v in enumerate(values)]
    d.add(PolyLine(points,strokeColor=colors.HexColor('#245b79'),strokeWidth=.5));story.append(d)
   story.append(p('横轴：0—10秒，每条竖线间隔1秒；各导联纵轴独立缩放，范围标注于导联名称旁。','SmallCN'))
 section('输入参数与校验说明')
 meta=study.metadata_json
 if study.kind=='signal':
  story.append(p('12标准导联；采样率100 Hz；时长10秒；每导联1000个采样点；波形单位mV。'))
 else:
  story.append(p(f"原始图片尺寸：{meta.get('width','未记录')} × {meta.get('height','未记录')} 像素；模型输入224 × 224；标准3行4列布局及底部II导联节律条。"))
 for warning in meta.get('warnings',[]):story.append(p(warning,'SmallCN'))
 story.append(p('原始文件及其校验值见本节上方；具体预处理版本见报告首页。','SmallCN'))
 raw=io.BytesIO()
 def footer(canvas,doc):
  canvas.setFont(FONT,8);canvas.drawString(40,24,f'ECG-{study.id:05d} / 分析 #{analysis.id}');canvas.drawRightString(555,24,f'第 {doc.page} 页')
 SimpleDocTemplate(raw,pagesize=(595.28,841.89),leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=40,title=f'心电分析报告-{analysis.id}',author='Cardio Workspace').build(story,onFirstPage=footer,onLaterPages=footer)
 writer=PdfWriter();writer.append(PdfReader(io.BytesIO(raw.getvalue())))
 for a in assets:
  path=(folder/a.stored_name).resolve()
  if path.parent!=folder:raise ValueError('Invalid attachment path')
  writer.add_attachment(a.original_name,path.read_bytes())
 out=io.BytesIO();writer.write(out);return out.getvalue()
