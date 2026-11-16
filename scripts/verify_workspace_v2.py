"""Read-only browser acceptance of filters, guidance and confirmed Agent execution."""
import json,time
import verify_system as v
from playwright.sync_api import sync_playwright
out=v.OUT/'workspace-v2';out.mkdir(parents=True,exist_ok=True)
errors=[];checks=[]
with sync_playwright() as p:
 for channel in ['chrome','msedge']:
  try:browser=p.chromium.launch(channel=channel,headless=True)
  except Exception as e:
   checks.append(dict(browser=channel,available=False,reason=str(e).splitlines()[0]));continue
  page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(v.BASE);page.get_by_test_id('login-username').fill(v.cfg.bootstrap_admin_username);page.get_by_test_id('login-password').fill(v.cfg.bootstrap_admin_password);page.get_by_test_id('login-submit').click();page.locator('.app-shell').wait_for()
  page.goto(v.BASE+'/dashboard',wait_until='networkidle');page.locator('.overview-metric').nth(3).click();page.wait_for_url('**/studies?status=archived');page.locator('.content > .el-loading-mask').wait_for(state='hidden')
  assert 'status=archived' in page.url
  page.reload(wait_until='networkidle');assert 'status=archived' in page.url
  page.get_by_role('button',name='重置筛选',exact=True).click();page.wait_for_url('**/studies')
  page.goto(v.BASE+'/signal',wait_until='networkidle');page.get_by_role('button',name='格式要求与演示样例').click();page.get_by_role('button',name='载入演示文件').click();page.get_by_text('2 个文件已选择',exact=True).wait_for();assert page.get_by_text('CSV采样率',exact=True).count()==0
  page.screenshot(path=str(out/(channel+'-upload.png')),full_page=True)
  page.goto(v.BASE+'/patients',wait_until='networkidle');page.get_by_role('button',name='档案详情',exact=True).first.click();page.get_by_role('heading',name='最近十次检查').wait_for();page.keyboard.press('Escape')
  page.goto(v.BASE+'/models',wait_until='networkidle');page.get_by_role('heading',name='本地工作助手').wait_for()
  page.goto(v.BASE+'/agent',wait_until='networkidle');page.get_by_test_id('agent-query').fill('怎么上传文件');page.get_by_test_id('agent-send').click();page.get_by_role('heading',name='确认本轮操作').wait_for(timeout=120000)
  # Route prediction can be corrected before execution. Force read-only help for deterministic acceptance.
  page.locator('.agent-message .el-select').click();page.get_by_role('option',name='上传格式说明',exact=True).click();page.get_by_role('button',name='重新预览',exact=True).click();page.get_by_role('heading',name='确认本轮操作').wait_for()
  page.get_by_role('button',name='确认执行',exact=True).click();page.locator('.agent-message.agent').last.wait_for(timeout=120000);assert '100 Hz' in page.locator('.agent-message.agent').last.inner_text()
  page.screenshot(path=str(out/(channel+'-agent.png')),full_page=True)
  page.reload(wait_until='networkidle');page.locator('.agent-message.agent').last.wait_for()
  page.get_by_test_id('agent-query').fill('不要分析信号');page.get_by_test_id('agent-send').click();page.get_by_text('已取消分析意图。请明确本轮是读取已有结果、查询模型，还是查看上传说明。',exact=True).wait_for()
  checks.append(dict(browser=channel,available=True,filters=True,reload=True,upload_guide=True,agent_confirmation=True,manual_correction=True,history=True,negation=True))
  page.set_viewport_size({'width':390,'height':844});page.goto(v.BASE+'/signal',wait_until='networkidle');page.get_by_role('button',name='格式要求与演示样例').click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(out/(channel+'-mobile.png')),full_page=True)
  browser.close()
result=dict(checks=checks,errors=errors);(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));assert not errors
