from app import agent_lab

def test_read_tool_retries_transient_errors(monkeypatch):
 monkeypatch.setattr(agent_lab.time,'sleep',lambda _:None)
 calls=[]
 def flaky():
  calls.append(1)
  if len(calls)<4: raise OSError('temporary')
  return 'ok'
 assert agent_lab.read_with_retry(flaky)=='ok'
 assert len(calls)==4

def test_agent_requires_login(client):
 assert client.post('/api/v1/agent/chat',json={'query':'上传说明'}).status_code==401

def test_agent_help_persisted_and_isolated(client,headers,monkeypatch):
 monkeypatch.setattr(agent_lab,'choose',lambda q:'input_help')
 r=client.post('/api/v1/agent/chat',headers=headers(),json={'query':'怎么上传'}); assert r.status_code==200,r.text
 data=r.json()['result']; assert data['tool_calls'][0]['name']=='input_help'
 assert '100 Hz' in data['agent']
 sid=data['session_id']; history=client.get('/api/v1/agent/sessions/'+sid,headers=headers()).json()['result']
 assert len(history['messages'])==2
 assert client.get('/api/v1/agent/sessions/'+sid,headers=headers('other')).status_code==404
 assert client.post('/api/v1/agent/chat',headers=headers('other'),json={'query':'继续','session_id':sid}).status_code==404

def test_agent_needs_study(client,headers,monkeypatch):
 monkeypatch.setattr(agent_lab,'choose',lambda q:'analyze_signal')
 r=client.post('/api/v1/agent/chat',headers=headers(),json={'query':'分析波形'})
 assert '选择检查' in r.json()['result']['agent']

def test_agent_study_access_and_confirm(client,headers,monkeypatch):
 monkeypatch.setattr(agent_lab,'choose',lambda q:'analyze_signal')
 p=client.post('/api/v1/patients',headers=headers(),json={'code':'AGENT-TEST','name':'测试'}).json()['result']
 s=client.post('/api/v1/studies',headers=headers(),json={'patient_id':p['id'],'title':'测试','kind':'signal'}).json()['result']
 r=client.post('/api/v1/agent/chat',headers=headers(),json={'query':'分析','study_id':s['id']})
 assert '勾选' in r.json()['result']['agent']
 assert client.post('/api/v1/agent/chat',headers=headers('other'),json={'query':'读取','study_id':s['id']}).status_code==404

def test_agent_busy_and_validation(client,headers):
 assert client.post('/api/v1/agent/chat',headers=headers(),json={'query':' '}).status_code==400
 agent_lab.guard.acquire()
 try: assert client.post('/api/v1/agent/chat',headers=headers(),json={'query':'上传'}).status_code==429
 finally: agent_lab.guard.release()

def test_plan_bound_to_query_and_single_use(client,headers,monkeypatch):
 monkeypatch.setattr(agent_lab,'choose',lambda q:'input_help')
 plan=client.post('/api/v1/agent/plan',headers=headers(),json={'query':'怎么上传'}).json()['result']
 body={'query':'怎么上传','session_id':plan['session_id'],'study_id':None,'plan_token':plan['token']}
 altered=body|{'query':'读取结果'}
 assert client.post('/api/v1/agent/chat',headers=headers(),json=altered).status_code==409
 assert client.post('/api/v1/agent/chat',headers=headers('other'),json=body).status_code==404
 result=client.post('/api/v1/agent/chat',headers=headers(),json=body)
 assert result.status_code==200,result.text
 assert result.json()['result']['tool_calls'][0]['name']=='input_help'
 assert client.post('/api/v1/agent/chat',headers=headers(),json=body).status_code==409

def test_plan_clarification_does_not_load_model(client,headers,monkeypatch):
 def forbidden(q):raise AssertionError('must not route unsupported instructions')
 monkeypatch.setattr(agent_lab,'choose',forbidden)
 for query in ['明天天气怎么样','不要分析信号','分析信号然后读取结果']:
  r=client.post('/api/v1/agent/plan',headers=headers(),json={'query':query})
  assert r.status_code==200,r.text
  assert r.json()['result']['clarification']

def test_manual_tool_is_whitelisted(client,headers):
 assert client.post('/api/v1/agent/plan',headers=headers(),json={'query':'上传格式','selected_tool':'delete_all'}).status_code==400
 p=client.post('/api/v1/agent/plan',headers=headers(),json={'query':'上传格式','selected_tool':'input_help'})
 assert p.json()['result']['tool']=='input_help'

def test_samples_and_audit_filters(client,headers):
 catalog=client.get('/api/v1/samples/catalog',headers=headers()).json()['result']
 assert catalog and 'signal.csv' in catalog[0]['files']
 template=client.get('/api/v1/input-template.csv',headers=headers())
 assert len(template.text.strip().splitlines())==1001
 assert client.get('/api/v1/samples/9/files/manifest.json',headers=headers()).status_code==404
 assert client.get('/api/v1/audit?q=not-existing-action',headers=headers()).json()['result']['total']==0
 assert client.get('/api/v1/audit',headers=headers('analyst')).status_code==403

def test_expired_plan_rejected(client,headers):
 p=client.post('/api/v1/agent/plan',headers=headers(),json={'query':'上传格式','selected_tool':'input_help'}).json()['result']
 with agent_lab.store() as conn:conn.execute('UPDATE plans SET expires=0 WHERE token=?',(p['token'],))
 r=client.post('/api/v1/agent/chat',headers=headers(),json={'query':'上传格式','session_id':p['session_id'],'plan_token':p['token']})
 assert r.status_code==409

def test_unknown_file_hash_not_marked_sample():
 from app.samples import source_for_hashes,packaged_hashes
 assert source_for_hashes(['unknown']) is None
 assert packaged_hashes()
 assert source_for_hashes(next(iter(packaged_hashes())))['purpose']=='public_sample'


def test_read_timeout_exhaustion(monkeypatch):
 import pytest
 from fastapi import HTTPException
 monkeypatch.setattr(agent_lab.time,'sleep',lambda _:None)
 attempts=[]
 def timeout():
  attempts.append(1)
  raise TimeoutError('injected read timeout')
 with pytest.raises(HTTPException) as error:agent_lab.read_with_retry(timeout)
 assert error.value.status_code==503
 assert len(attempts)==4

def test_legitimate_paraphrases_reach_router(client,headers,monkeypatch):
 seen=[]
 def route(q):seen.append(q);return 'model_info'
 monkeypatch.setattr(agent_lab,'choose',route)
 for query in ['将选定的十二路电压序列送入分类器','把已完成记录的分类输出调出来','请列出两种已部署分类器的输入规格']:
  r=client.post('/api/v1/agent/plan',headers=headers(),json={'query':query})
  assert r.status_code==200 and r.json()['result']['tool']=='model_info'
 assert len(seen)==3

def test_followup_context_bounded_and_explicit_query_unchanged():
 messages=[{'role':'user','content':'分析数字信号'},{'role':'agent','content':'private result','tool_calls':[{'name':'analyze_signal'}]}]
 text=agent_lab.routing_query('刚才的结果出来了吗',messages,None)
 assert '分析数字信号' in text and 'analyze_signal' in text and '当前请求' in text
 assert 'private result' not in text
 assert agent_lab.routing_query('怎么上传文件',messages,None)=='怎么上传文件'
 assert len(agent_lab.routing_query('继续',[{'role':'user','content':'x'*10000}]*100,None))<1500
