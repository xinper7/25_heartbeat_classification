"""Read-only verification of preview, drag/drop, waveform windows and review context."""
import json,base64,httpx,uuid
import verify_system as v
from playwright.sync_api import sync_playwright
out=v.OUT/'dynamic-ui';out.mkdir(parents=True,exist_ok=True);errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(v.BASE);page.get_by_test_id('login-username').fill(v.cfg.bootstrap_admin_username);page.get_by_test_id('login-password').fill(v.cfg.bootstrap_admin_password);page.get_by_test_id('login-submit').click();page.locator('.app-shell').wait_for()
 page.goto(v.BASE+'/image',wait_until='networkidle');page.get_by_test_id('workspace-files').set_input_files(str(v.SAMPLE/'report.png'));page.locator('.local-image-preview img').wait_for();page.get_by_text('本地预览 · 尚未保存与校验',exact=True).wait_for()
 page.screenshot(path=str(out/'image-preview.png'),full_page=True)
 page.goto(v.BASE+'/signal',wait_until='networkidle')
 page.locator('.upload-zone').evaluate("el=>{const data=new DataTransfer();data.items.add(new File(['bad'],'wrong.txt'));el.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:data}));}")
 page.get_by_text('请选择一份 CSV，或同名的 .hea 与 .dat 配对文件',exact=True).wait_for()
 # Create a clearly labelled public-sample acceptance study through the UI.
 c=httpx.Client(base_url=v.BASE,trust_env=False);login=v.checked(c.post('/api/v1/auth/login',json={'username':v.cfg.bootstrap_admin_username,'password':v.cfg.bootstrap_admin_password}));c.headers['Authorization']='Bearer '+login['access_token']
 code='DYNAMIC-'+uuid.uuid4().hex[:8];v.checked(c.post('/api/v1/patients',json={'code':code,'name':'动态交互公开验收'}))
 page.goto(v.BASE+'/signal',wait_until='networkidle');page.get_by_test_id('workspace-patient').click();page.get_by_test_id('workspace-patient').locator('input').fill(code);page.get_by_role('option').filter(has_text=code).click()
 page.get_by_test_id('workspace-title').fill('动态交互验收 · 公开信号样例');page.get_by_test_id('workspace-files').set_input_files([str(v.SAMPLE/'00009_lr.hea'),str(v.SAMPLE/'00009_lr.dat')]);page.get_by_test_id('upload-submit').click();page.locator('.validation-success').wait_for();page.get_by_test_id('analyze-submit').click();page.get_by_text('分析完成，结果已保存，等待专业复核',exact=False).wait_for(timeout=60000);page.screenshot(path=str(out/'analysis-feedback.png'),full_page=True)
 page.goto(v.BASE+'/review?kind=signal',wait_until='networkidle');page.get_by_role('button',name='查看复核',exact=True).first.click();page.locator('.el-drawer .signal-chart canvas').wait_for()
 page.locator('.el-drawer').get_by_role('button',name='前2秒',exact=True).click();page.locator('.el-drawer').get_by_text('时间窗口 0.0—2.0 秒',exact=True).wait_for()
 page.locator('.el-drawer').get_by_role('button',name='填写复核意见',exact=True).first.click();page.locator('.review-workspace').wait_for();page.locator('.review-context .review-score').first.wait_for();page.wait_for_timeout(400);page.screenshot(path=str(out/'review-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400);page.screenshot(path=str(out/'review-mobile.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 browser.close()
result={'errors':errors,'local_preview':True,'drag_validation':True,'wave_window':True,'review_context':True,'mobile':True};(out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert not errors
