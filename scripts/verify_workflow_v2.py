"""End-to-end actual model analysis and review; creates explicitly named public QA samples."""
import json,time,uuid
import httpx
import verify_system as v
c=httpx.Client(base_url=v.BASE,timeout=120,trust_env=False)
r=v.checked(c.post('/api/v1/auth/login',json={'username':v.cfg.bootstrap_admin_username,'password':v.cfg.bootstrap_admin_password}));c.headers['Authorization']='Bearer '+r['access_token']
patient=v.checked(c.post('/api/v1/patients',json={'code':'QA-V2-'+uuid.uuid4().hex[:8],'name':'公开样例功能验收','note':'新增功能验收，公开 PTB-XL 演示数据'}))
studies={k:v.make_study(c,patient['id'],k,'功能验收 v2 · '+k) for k in ['signal','image']}
results=[]
for kind,sid in studies.items():
 query='分析数字心电信号' if kind=='signal' else '分析报告图片'
 started=time.perf_counter()
 plan=v.checked(c.post('/api/v1/agent/plan',json={'query':query,'study_id':sid}))
 route_ms=(time.perf_counter()-started)*1000
 assert plan['tool']=='analyze_'+kind,plan
 body={'query':query,'study_id':sid,'session_id':plan['session_id'],'plan_token':plan['token'],'allow_analysis':True}
 execute_started=time.perf_counter()
 answer=v.checked(c.post('/api/v1/agent/chat',json=body))
 execute_http_ms=(time.perf_counter()-execute_started)*1000
 total_ms=(time.perf_counter()-started)*1000
 detail=v.checked(c.get(f'/api/v1/studies/{sid}'));assert detail['analyses'] and len(detail['analyses'][0]['predictions'])==5
 assert detail['metadata']['source']['purpose']=='public_sample'
 assert c.post('/api/v1/agent/chat',json=body).status_code==409
 results.append(dict(kind=kind,study_id=sid,analysis_id=detail['analyses'][0]['id'],tool=answer['tool_calls'][0]['name'],elapsed_ms=answer['elapsed_ms'],route_http_ms=round(route_ms,2),execute_http_ms=round(execute_http_ms,2),full_http_ms=round(total_ms,2)))
 first=detail['analyses'][0]['id']
 review=v.checked(c.post(f'/api/v1/analyses/{first}/reviews',json={'conclusion':'confirmed','comment':'功能验收：公开样例实际推理完成，工具调用与记录一致。'}))
 assert v.checked(c.get(f'/api/v1/studies/{sid}'))['status']=='archived'
data=v.checked(c.get('/api/v1/studies',params={'source':'sample','patient_id':patient['id']}));assert data['total']==2
assert v.checked(c.get('/api/v1/studies',params={'source':'regular','patient_id':patient['id']}))['total']==0
status=v.checked(c.get('/api/v1/agent/status'));assert status['loaded'] and status['ready']
result=dict(studies=results,source_filter=True,review=True,single_use_token=True,agent=status)
out=v.OUT/'workspace-v2/workflow.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
