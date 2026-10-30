// Real browser + engine CRUD acceptance; leaves only an archived audit fixture.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const base = process.env.TEST_URL || 'http://123.57.158.71';
const sid = 1900000000 + Math.floor(Date.now()/1000)%1000000;
const raw = `alert http any any -> any any (msg:"CRUD acceptance fixture"; flow:established,to_server; http.uri; content:"union"; nocase; sid:${sid}; rev:1;)`;
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-proxy-server']});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  if(process.env.LOCAL_PREVIEW)for(const file of ['index.html','style.css','app.js'])await page.route('**/'+(file==='index.html'?'':file),r=>r.fulfill({body:fs.readFileSync('frontend/public/'+file),contentType:file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html'}));
  const headers={Authorization:'Basic '+Buffer.from('analyst:'+process.env.APP_PASSWORD).toString('base64')};
  const get=async path=>{const r=await page.request.get(base+'/api'+path,{headers});if(!r.ok())throw Error(await r.text());return r.json()};
  const post=async(path,data,expected=200)=>{const r=await page.request.post(base+'/api'+path,{headers,data});if(r.status()!==expected)throw Error(r.status()+' '+await r.text());return r.json()};
  let task, event;
  try{
    await page.goto(base);await page.locator('#password').fill(process.env.APP_PASSWORD);await page.locator('#login').click();
    await page.waitForFunction(()=>document.querySelector('#identity').textContent==='分析员');
    await page.locator('#audience').selectOption('professional');await page.locator('[data-view="policies"]').click();
    await page.getByRole('button',{name:'+ 新增',exact:true}).click();
    await page.getByRole('textbox',{name:'新增规则原文',exact:true}).fill(raw.replace('rev:1;', 'invalid_keyword:yes;'));
    await page.getByRole('button',{name:'校验并新增规则',exact:true}).click();
    await page.locator('.rule-feedback').filter({hasText:'Suricata 校验失败'}).waitFor();
    if((await get('/rules')).some(r=>r.sid===sid))throw Error('invalid rule was stored');
    await page.getByRole('textbox',{name:'新增规则原文',exact:true}).fill(raw);
    await page.getByRole('button',{name:'校验并新增规则',exact:true}).click();
    await page.locator('tr[data-sid="'+sid+'"]').waitFor();
    await post('/rules/create',{sid,raw},409);
    await page.getByRole('textbox',{name:'规则名称或SID',exact:true}).fill(String(sid));
    await page.getByRole('button',{name:'搜索',exact:true}).click();
    if(await page.locator('#rules tbody tr').count()!==1)throw Error('rule search failed');
    const row=page.locator('tr[data-sid="'+sid+'"]');
    await row.getByRole('button',{name:'修改',exact:true}).click();
    const card=page.locator('dialog');
    await page.getByRole('textbox',{name:'规则 '+sid+' 编辑内容',exact:true}).fill(raw.replace('rev:1;', 'rev:2;'));
    await card.getByRole('button',{name:'校验并发布新版本',exact:true}).click();
    await card.locator('.rule-feedback').filter({hasText:'发布成功'}).waitFor();
    await page.getByRole('button',{name:'关闭弹窗',exact:true}).click();
    await post('/rules/'+sid+'/archive',{base_revision:1},409);
    const upload=await page.request.post(base+'/api/tasks',{headers:{...headers,'Content-Type':'application/octet-stream'},data:fs.readFileSync('data/web_sqli.pcap')});
    if(upload.status()!==202)throw Error(await upload.text());task=(await upload.json()).id;
    for(let i=0;i<90;i++){const t=(await get('/tasks')).find(t=>t.id===task);if(t.status==='complete')break;if(t.status==='failed')throw Error(t.error);if(i===89)throw Error('timeout');await new Promise(r=>setTimeout(r,1000))}
    event=(await get('/alerts?task_id='+task+'&size=100')).items.find(a=>a.sid===sid);if(!event)throw Error('new rule did not detect actual PCAP');
    await row.getByRole('button',{name:'删除',exact:true}).click();
    await page.getByRole('button',{name:'确认删除',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('规则已归档'));
    if((await get('/rules')).some(r=>r.sid===sid))throw Error('archive still active');
    if(!(await get('/alerts/'+event.id)).rule.includes('rev:2;'))throw Error('historical snapshot lost');
    await page.getByLabel('显示已归档规则（可恢复）').check();
    await row.getByRole('button',{name:'恢复',exact:true}).click();
    await page.getByRole('button',{name:'确认恢复',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='规则已恢复');
    await page.locator('tr[data-sid="'+sid+'"]').waitFor();
    if(!(await get('/rules')).some(r=>r.sid===sid&&!r.archived))throw Error('restore failed');
    const history=await get('/rules/'+sid+'/history');
    if(!['restore','archive','edit','create'].every(a=>history.some(r=>r.action===a)))throw Error('audit missing');
    const result={tested_at:new Date().toISOString(),sid,task,passed:true,checks:['invalid_engine_rejected','browser_create','duplicate_sid_rejected','browser_edit','stale_archive_rejected','new_rule_detects_pcap','browser_archive','historical_rule_snapshot_preserved','browser_restore','lifecycle_audit']};
    fs.writeFileSync('validation/rule-crud-smoke.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{
    try{const current=(await get('/rules?include_archived=1')).find(r=>r.sid===sid);if(current&&!current.archived)await post('/rules/'+sid+'/archive',{base_revision:current.revision})}finally{await browser.close()}
  }
})().catch(e=>{console.error(e);process.exitCode=1});
