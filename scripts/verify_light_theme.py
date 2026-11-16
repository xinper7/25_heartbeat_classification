"""Visual regression of the light workspace; does not modify business records."""
import json
import verify_system as v
from playwright.sync_api import sync_playwright

out=v.ROOT/'runtime/qa/light-theme';out.mkdir(parents=True,exist_ok=True)
errors=[];results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(v.BASE,wait_until='networkidle')
 page.screenshot(path=str(out/'login.png'),full_page=True)
 page.get_by_test_id('login-username').fill(v.cfg.bootstrap_admin_username)
 page.get_by_test_id('login-password').fill(v.cfg.bootstrap_admin_password)
 page.get_by_test_id('login-submit').click()
 page.locator('.app-shell').wait_for()
 for route in ['dashboard','patients','signal','image','studies','review','jobs','models','admin','agent']:
  page.goto(v.BASE+'/'+route,wait_until='networkidle')
  page.locator('.content > .el-loading-mask').wait_for(state='hidden')
  page.screenshot(path=str(out/(route+'.png')),full_page=True)
  results.append({'route':route,'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth+1')})
  if route=='dashboard':
   assert page.locator('.overview-metric').count()==4
   assert page.locator('.overview-entry').count()==2
   assert page.locator('.chart-legend li').count()==5
   assert page.locator('.service-item').count()==2
   assert page.get_by_role('button',name='导入演示样本',exact=True).is_visible()
   page.locator('.overview-entry').first.click()
   page.wait_for_url('**/signal')
   page.goto(v.BASE+'/dashboard',wait_until='networkidle')
   page.locator('.overview-metric').nth(1).click()
   page.wait_for_url('**/studies')
   page.goto(v.BASE+'/dashboard',wait_until='networkidle')
  dark_text=page.evaluate("""() => [...document.querySelectorAll('.content *')].filter(e=>e.children.length===0 && e.textContent.trim() && e.getBoundingClientRect().width && getComputedStyle(e).color === 'rgb(0, 0, 0)').map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.trim().slice(0,50)}))""")
  if dark_text: print(route,'black_text',json.dumps(dark_text,ensure_ascii=False),flush=True)
 # Dialog fields and overlay must share the theme.
 page.goto(v.BASE+'/dashboard',wait_until='networkidle')
 page.get_by_role('button',name='新建检查',exact=True).click()
 page.locator('.el-dialog').filter(has=page.get_by_text('检查名称',exact=True)).first.wait_for()
 page.wait_for_timeout(350)
 page.screenshot(path=str(out/'dialog.png'),full_page=True)
 page.keyboard.press('Escape')
 page.goto(v.BASE+'/studies',wait_until='networkidle')
 row=page.locator('.el-table__row').filter(has_text='signal').first
 row.get_by_role('button',name='查看详情',exact=True).click()
 page.locator('.el-drawer .signal-chart canvas').wait_for()
 page.wait_for_timeout(350)
 page.screenshot(path=str(out/'detail.png'),full_page=True)
 page.keyboard.press('Escape')
 for route in ['dashboard','signal','agent']:
  page.set_viewport_size({'width':390,'height':844})
  page.goto(v.BASE+'/'+route,wait_until='networkidle');page.wait_for_timeout(300)
  page.screenshot(path=str(out/(route+'-mobile.png')),full_page=True)
  results.append({'route':route+'-mobile','overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth+1')})
 browser.close()
(out/'verification.json').write_text(json.dumps({'errors':errors,'pages':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'errors':errors,'pages':results},ensure_ascii=False))
