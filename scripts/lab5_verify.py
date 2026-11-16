"""Real local router + API + Chrome acceptance. Creates labelled demo studies."""
import json, statistics, time, uuid, re
from pathlib import Path
import httpx
import verify_system as v
from lab5_train import TEST
from playwright.sync_api import sync_playwright

def main():
 c=httpx.Client(base_url=v.BASE,timeout=120,trust_env=False)
 login=v.checked(c.post('/api/v1/auth/login',json=dict(username=v.cfg.bootstrap_admin_username,password=v.cfg.bootstrap_admin_password)))
 c.headers['Authorization']='Bearer '+login['access_token']
 patient=v.checked(c.post('/api/v1/patients',json=dict(code='LAB5-'+uuid.uuid4().hex[:8],name='实验五验收样本')))
 studies={k:v.make_study(c,patient['id'],k,'实验五验收 · '+k) for k in ['signal','image']}
 started=time.perf_counter(); warm=v.checked(c.post('/api/v1/agent/chat',json=dict(query='当前用什么模型'))); cold=(time.perf_counter()-started)*1000
 mapping=dict(zip('ABCDE',['analyze_signal','analyze_image','read_result','input_help','model_info']))
 rows=[]
 for query,label in TEST:
  sid=studies['image' if label=='B' else 'signal']
  t=time.perf_counter(); plan=v.checked(c.post('/api/v1/agent/plan',json=dict(query=query,study_id=sid)))
  if 'token' not in plan:
   rows.append(dict(query=query,expected=mapping[label],actual='clarification',correct=False,ms=round((time.perf_counter()-t)*1000,2),answer=plan.get('clarification','')))
   continue
  result=v.checked(c.post('/api/v1/agent/chat',json=dict(query=query,session_id=plan['session_id'],study_id=sid,allow_analysis=True,plan_token=plan['token']))); ms=(time.perf_counter()-t)*1000
  name=result['tool_calls'][0]['name']
  rows.append(dict(query=query,expected=mapping[label],actual=name,correct=name==mapping[label],ms=round(ms,2),answer=result['agent']))
  print('tool',label,name,round(ms,2),flush=True)
 # Continue without study_id: context must remain bound to the stored study.
 r=v.checked(c.post('/api/v1/agent/chat',json=dict(query='读取检查结果',study_id=studies['signal'])))
 continuation=v.checked(c.post('/api/v1/agent/chat',json=dict(query='查看已有预测',session_id=r['session_id'])))
 assert continuation['study_id']==studies['signal']
 history=v.checked(c.get('/api/v1/agent/sessions/'+r['session_id']))
 assert len(history['messages'])==4
 assert c.post('/api/v1/agent/chat',json={'query':' '}).status_code==400
 assert httpx.post(v.BASE+'/api/v1/agent/chat',json={'query':'说明'},trust_env=False).status_code==401
 # Verify both real classifier results were created by tools (not fabricated text).
 for kind,sid in studies.items():
  detail=v.checked(c.get(f'/api/v1/studies/{sid}'))
  assert detail['analyses'],f'{kind} analysis was not executed; inspect routing metrics'
  assert len(detail['analyses'][0]['predictions'])==5
 test_text=(v.OUT/'pytest-lab5.txt').read_text(encoding='utf-8-sig')
 test_result=re.search(r'\d+ passed',test_text).group(0)
 report=dict(rows=rows,accuracy=sum(x['correct'] for x in rows)/10,mean_ms=round(statistics.mean(x['ms'] for x in rows),2),max_ms=max(x['ms'] for x in rows),cold_ms=round(cold,2),pytest=test_result,study_ids=studies,multiturn=True)
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True)
  page=browser.new_page(viewport=dict(width=1440,height=1100))
  errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(v.BASE);page.get_by_test_id('login-username').fill(v.cfg.bootstrap_admin_username);page.get_by_test_id('login-password').fill(v.cfg.bootstrap_admin_password);page.get_by_test_id('login-submit').click()
  page.get_by_role('navigation').get_by_role('button',name='心电工作助手',exact=True).click()
  page.get_by_test_id('agent-query').fill('当前用什么模型');page.get_by_test_id('agent-send').click()
  page.get_by_role('heading',name='确认本轮操作').wait_for(timeout=120000)
  page.get_by_role('button',name='确认执行',exact=True).click()
  page.locator('.agent-message.agent').first.wait_for(timeout=120000)
  page.screenshot(path=str(v.OUT/'agent-desktop.png'),full_page=True)
  page.reload();page.locator('.agent-message.agent').first.wait_for(); report['browser_restore']=True
  page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(v.OUT/'agent-mobile.png'),full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
  report['browser_errors']=errors; assert not errors
  browser.close()
 (v.OUT/'agent_acceptance_v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('accuracy',report['accuracy'],'mean_ms',report['mean_ms'],flush=True)

if __name__=='__main__': main()
