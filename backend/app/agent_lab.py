"""Local Qwen LoRA router + LangChain tool loop. No external patient-data calls."""
import json, logging, sqlite3, threading, time, uuid
from pathlib import Path
from functools import lru_cache
from contextlib import contextmanager
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from .config import ROOT, get_settings
from .db import get_db
from .models import Analysis, User
from .security import current_user
from .services import access_study, serialize_analysis, perform_analysis

router=APIRouter(prefix='/api/v1/agent',tags=['agent'])
log=logging.getLogger('ecg.agent')
guard=threading.Lock()
SYSTEM='选择心电工作空间工具，只输出字母。A=分析数字信号波形；B=分析报告图片；C=读取已有检查结果；D=上传格式使用帮助；E=查询模型版本状态。'
NAMES=['analyze_signal','analyze_image','read_result','input_help','model_info']

def read_with_retry(fn,db=None):
 """Three retries for transient read failures; never repeat analysis writes."""
 for attempt in range(4):
  try: return fn()
  except (OSError,OperationalError):
   if db is not None: db.rollback()
   if attempt==3: raise HTTPException(503,'读取工具暂不可用，已重试3次，请稍后再试')
   log.warning('agent_read_retry attempt=%s',attempt+1)
   time.sleep(0.1*(2**attempt))

def adapter_paths():
 folder=ROOT/'runtime/agent'; active=folder/'active_adapter.json'
 selected=json.loads(active.read_text(encoding='utf-8')) if active.exists() else {}
 adapter=(folder/selected.get('directory','adapter')).resolve()
 metrics=(folder/selected.get('metrics','training_metrics.json')).resolve()
 if not adapter.is_relative_to(folder.resolve()) or not metrics.is_relative_to(folder.resolve()):raise HTTPException(503,'适配器配置路径无效')
 return adapter,metrics

@lru_cache
def local_model():
 import torch
 from transformers import AutoTokenizer, AutoModelForCausalLM
 from peft import PeftModel
 folder=ROOT/'runtime/agent'
 adapter,_=adapter_paths()
 if not (adapter/'adapter_config.json').exists():
  raise HTTPException(503,'本地LoRA模型尚未准备好，请先运行 scripts/lab5_train.py')
 torch.set_num_threads(4)
 tok=AutoTokenizer.from_pretrained(folder/'base',local_files_only=True)
 model=AutoModelForCausalLM.from_pretrained(folder/'base',local_files_only=True,torch_dtype=torch.float32)
 model=PeftModel.from_pretrained(model,adapter).eval()
 return tok,model

def choose(query):
 import torch
 tok,model=local_model()
 prompt=tok.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':query}],tokenize=False,add_generation_prompt=True)
 batch=tok(prompt,return_tensors='pt',truncation=True,max_length=512)
 ids=[tok.encode(x,add_special_tokens=False)[0] for x in 'ABCDE']
 with torch.no_grad(): scores=model(**batch).logits[0,-1,ids]
 return NAMES[scores.argmax().item()]

class RouterModel(BaseChatModel):
 query: str
 planned_tool: str | None = None
 @property
 def _llm_type(self): return 'local-qwen-lora-router'
 def bind_tools(self, tools, **kwargs): return self
 def _generate(self,messages,stop=None,run_manager=None,**kwargs):
  if isinstance(messages[-1],ToolMessage):
   # Grounded verbatim rendering is deliberate: no generated diagnosis.
   msg=AIMessage(content=str(messages[-1].content))
  else:
   name=self.planned_tool or choose(self.query)
   msg=AIMessage(content='',tool_calls=[dict(name=name,args={},id=uuid.uuid4().hex,type='tool_call')])
  return ChatResult(generations=[ChatGeneration(message=msg)])

@contextmanager
def store():
 path=get_settings().storage_dir/'agent_sessions.sqlite3'; path.parent.mkdir(parents=True,exist_ok=True)
 conn=sqlite3.connect(path,timeout=10)
 conn.execute('CREATE TABLE IF NOT EXISTS plans(token TEXT PRIMARY KEY, owner INTEGER NOT NULL, session TEXT NOT NULL, study INTEGER, query TEXT NOT NULL, tool TEXT NOT NULL, expires REAL NOT NULL)')
 conn.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, owner INTEGER NOT NULL, study INTEGER, messages TEXT NOT NULL)')
 try:
  with conn: yield conn
 finally: conn.close()

class ChatIn(BaseModel):
 query: str=Field(min_length=1,max_length=1000)
 session_id: str | None=Field(default=None,max_length=64)
 study_id: int | None=Field(default=None,gt=0)
 allow_analysis: bool=False
 plan_token: str | None=Field(default=None,max_length=64)
 selected_tool: str | None=Field(default=None,max_length=40)

def session(conn,sid,user):
 row=conn.execute('SELECT owner,study,messages FROM sessions WHERE id=?',(sid,)).fetchone()
 if not row or row[0]!=user.id: raise HTTPException(404,'会话不存在')
 return row

@router.get('/sessions/{sid}')
def history(sid:str,user:User=Depends(current_user)):
 with store() as conn:
  row=session(conn,sid,user)
 return dict(code=0,result=dict(session_id=sid,study_id=row[1],messages=json.loads(row[2])),msg='成功')

LABELS=dict(zip(NAMES,['数字信号分析','报告图分析','读取已有结果','上传格式说明','模型版本信息']))

def clarify(query):
 import re
 if re.search(r'删除|停用|修改密码|创建账号|自动归档|自动复核|开药|处方',query):
  return '这项操作不在助手支持的五类工具内，请使用对应业务页面。'
 if re.search(r'(信号|波形|CSV|csv)',query) and re.search(r'图片|照片|PNG|JPEG',query) and re.search(r'分析|推理|识别',query):
  return '请分两轮操作，每轮选择一条检查和一种输入类型。'
 if re.search(r'(不要|别|不需要|不用|停止|取消).{0,12}(分析|运行|推理|识别)',query):
  return '已取消分析意图。请明确本轮是读取已有结果、查询模型，还是查看上传说明。'
 if re.search(r'(同时|然后|并且|再帮|再读|之后)',query) and sum(bool(re.search(x,query)) for x in ['分析|推理|识别','结果|结论','上传|格式','模型|版本'])>1:
  return '本轮请只选择一项操作，完成后再提出下一项。'
 if re.search(r'天气|股票|彩票|讲笑话|写诗',query):
  return '我支持心电检查的分析、结果读取、上传说明和模型信息。请明确需要哪一项。'
 return None

def routing_query(query, messages, study):
 """Include bounded context for elliptical follow-ups; explicit requests stay unchanged."""
 import re
 if not messages or not re.search(r'刚才|上次|它|这个|那个|继续|再来|出来了吗|怎么样了',query):return query
 history=[]
 for message in messages[-6:]:
  if message.get('role')=='user':history.append('用户：'+str(message.get('content',''))[:160])
  for call in message.get('tool_calls',[]):
   if call.get('name') in NAMES:history.append('已执行工具：'+call['name'])
 state=f'当前检查类型：{study.kind}。' if study else '当前未选择检查。'
 return '最近操作（仅用于理解省略指代）：\n'+'\n'.join(history[-6:])+'\n'+state+'\n当前请求：'+query

@router.get('/status')
def agent_status(user:User=Depends(current_user)):
 folder=ROOT/'runtime/agent'
 base=all((folder/'base'/name).exists() for name in ['config.json','model.safetensors'])
 adapter_folder,path=adapter_paths()
 adapter=(adapter_folder/'adapter_config.json').exists() and (adapter_folder/'adapter_model.safetensors').exists()
 metrics={}
 if path.exists():
  try:
   data=json.loads(path.read_text(encoding='utf-8')); metrics=dict(accuracy=data['finetuned']['accuracy'],test_samples=data['test_samples'],train_samples=data['train_samples'],scope='适配器离线分类评估，非当前端到端成功率',adapter=adapter_folder.relative_to(folder).as_posix(),source=path.relative_to(folder).as_posix())
  except (ValueError,KeyError): pass
 return dict(code=0,result=dict(base_ready=base,adapter_ready=adapter,loaded=local_model.cache_info().currsize>0,ready=base and adapter,metrics=metrics,scope='仅五类工具路由；确认后执行；不生成医学诊断'),msg='成功')

@router.post('/plan')
def plan(body:ChatIn,db=Depends(get_db),user:User=Depends(current_user)):
 if not body.query.strip(): raise HTTPException(400,'请输入问题')
 sid=body.session_id or uuid.uuid4().hex
 with store() as conn:
  row=session(conn,sid,user) if body.session_id else None
 study_id=body.study_id if 'study_id' in body.model_fields_set else (row[1] if row else None)
 study=access_study(db,study_id,user) if study_id else None
 hint=clarify(body.query)
 if hint:return dict(code=0,result=dict(clarification=hint),msg='需要澄清')
 if body.selected_tool and body.selected_tool not in NAMES:raise HTTPException(400,'不支持的工具')
 if not guard.acquire(blocking=False):raise HTTPException(429,'助手正在处理其他请求，请稍后重试')
 try: name=body.selected_tool or choose(routing_query(body.query,json.loads(row[2]) if row else [],study))
 finally:guard.release()
 if name not in NAMES:raise HTTPException(400,'无法确定操作，请重新描述')
 if name in NAMES[:3] and not study:return dict(code=0,result=dict(clarification='请先在上方选择检查记录。'),msg='需要选择检查')
 if name in NAMES[:2]:
  if user.role not in ('admin','analyst'):raise HTTPException(403,'当前角色没有分析权限')
  if study.kind != ('signal' if name==NAMES[0] else 'image'):return dict(code=0,result=dict(clarification='所选检查与工具类型不一致，请更换检查或修正工具。'),msg='需要修正')
 token=uuid.uuid4().hex; expires=time.time()+300
 with store() as conn:
  if not row:conn.execute('INSERT INTO sessions VALUES(?,?,?,?)',(sid,user.id,study_id,'[]'))
  conn.execute('DELETE FROM plans WHERE expires<?',(time.time(),))
  conn.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?)',(token,user.id,sid,study_id,body.query,name,expires))
 return dict(code=0,result=dict(session_id=sid,study_id=study_id,study_title=study.title if study else None,tool=name,label=LABELS[name],writes=name in NAMES[:2],token=token,expires_at=expires,note='已有结果将直接读取；没有结果时运行并保存模型分析。' if name in NAMES[:2] else '仅查询，不修改检查。'),msg='请确认操作')

@router.post('/chat')
def chat(body:ChatIn,db=Depends(get_db),user:User=Depends(current_user)):
 if not body.query.strip(): raise HTTPException(400,'请输入问题')
 if not guard.acquire(blocking=False): raise HTTPException(429,'助手正在处理其他请求，请稍后重试')
 started=time.perf_counter()
 try:
  sid=body.session_id or uuid.uuid4().hex
  with store() as conn:
   row=session(conn,sid,user) if body.session_id else None
  messages=json.loads(row[2]) if row else []
  study_id=body.study_id if 'study_id' in body.model_fields_set else (row[1] if row else None)
  study=access_study(db,study_id,user) if study_id else None
  planned_tool=None
  if body.plan_token:
   with store() as conn:
    conn.execute('BEGIN IMMEDIATE')
    p=conn.execute('SELECT owner,session,study,query,tool,expires FROM plans WHERE token=?',(body.plan_token,)).fetchone()
    if not p or p[0]!=user.id or p[1]!=sid or p[2]!=study_id or p[3]!=body.query or p[5]<time.time():
     raise HTTPException(409,'确认已失效或内容已改变，请重新预览操作')
    planned_tool=p[4]
    conn.execute('DELETE FROM plans WHERE token=?',(body.plan_token,))
  elif body.selected_tool:
   raise HTTPException(409,'请先预览并确认操作')
  hint=clarify(body.query)
  if hint: return dict(code=0,result=dict(session_id=sid,agent=hint,tool_calls=[],elapsed_ms=0,study_id=study_id),msg='需要澄清')
  def result_text(a):
   lines=[f"检查 #{a['study_id']}，模型 {a['model_version']}。"]
   for p in a['predictions']:
    lines.append(f"{p['code']} {p['name']}：分数 {p['probability']:.3f}，阈值 {p['threshold']:.3f}，{'阳性' if p['positive'] else '阴性'}。")
   lines.append('模型分数不等于患病概率；以上为模型辅助结果，请由专业人员复核。')
   return '\n'.join(lines)
  def run(kind):
   if not study: return '请先在上方选择检查记录，再运行分析。'
   if study.kind!=kind: return '所选记录与请求的分析类型不一致，请重新选择检查。'
   if not body.allow_analysis or not planned_tool: return '运行分析会保存新的结果。请先预览操作并确认；勾选允许分析后执行。'
   if user.role not in ('admin','analyst'): raise HTTPException(403,'当前角色没有分析权限')
   existing=db.scalar(select(Analysis).where(Analysis.study_id==study.id).order_by(Analysis.id.desc()))
   a=existing or perform_analysis(db,study.id,user.id)
   return result_text(serialize_analysis(db,a))
  @tool
  def analyze_signal()->str:
   """运行选中检查的数字信号分析。"""
   return run('signal')
  @tool
  def analyze_image()->str:
   """运行选中检查的报告图分析。"""
   return run('image')
  @tool
  def read_result()->str:
   """读取选中检查已保存的分析结果。"""
   if not study: return '请先选择检查记录。'
   a=read_with_retry(lambda:db.scalar(select(Analysis).where(Analysis.study_id==study.id).order_by(Analysis.id.desc())),db)
   return result_text(serialize_analysis(db,a)) if a else '该检查尚未分析，请明确要求运行信号或图片分析。'
  @tool
  def input_help()->str:
   """返回项目支持的上传格式说明。"""
   return '数字信号：同时选择同名 .hea/.dat，或上传含12标准导联的CSV，100 Hz、10秒、1000行，声明mV/uV。原始波形选择40 Hz低通，已处理样本选择实验处理版。报告图：PNG/JPEG，3行4列并含底部II导联节律条；请在报告图分析页上传。单次不超过16 MB。'
  @tool
  def model_info()->str:
   """读取发布清单中的两份模型信息。"""
   manifest=json.loads(read_with_retry(lambda:(get_settings().models_dir/'manifest.json').read_text(encoding='utf-8')))
   return '\n'.join(f"{k}：{v['version']}；输入 {v['input_shape']}；类别 {', '.join(v['classes'])}" for k,v in manifest.items())
  graph=create_agent(RouterModel(query=routing_query(body.query,messages,study),planned_tool=planned_tool),[analyze_signal,analyze_image,read_result,input_help,model_info])
  output=graph.invoke({'messages':[{'role':'user','content':body.query}]},{'recursion_limit':5})
  calls=[dict(name=c['name'],args=c['args']) for m in output['messages'] if isinstance(m,AIMessage) for c in m.tool_calls]
  answer=output['messages'][-1].content
  ms=round((time.perf_counter()-started)*1000,2)
  messages.extend([dict(role='user',content=body.query),dict(role='agent',content=answer,tool_calls=calls,elapsed_ms=ms)])
  messages=messages[-80:]
  with store() as conn:
   conn.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',(sid,user.id,study_id,json.dumps(messages,ensure_ascii=False)))
  log.info('agent_completed user=%s session=%s tools=%s elapsed_ms=%s',user.id,sid,[c['name'] for c in calls],ms)
  return dict(code=0,result=dict(session_id=sid,user=body.query,agent=answer,tool_calls=calls,elapsed_ms=ms,study_id=study_id,model='Qwen2.5-0.5B-Instruct + LoRA'),msg='成功')
 finally:
  guard.release()
