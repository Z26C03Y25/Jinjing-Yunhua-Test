// Dev-only Playwright check. Supply PLAYWRIGHT_MODULE, APP_PASSWORD and TEST_PCAP.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const base = process.env.TEST_URL || 'http://123.57.158.71';
(async () => {
  if (!process.env.APP_PASSWORD || !process.env.TEST_PCAP) throw Error('APP_PASSWORD and TEST_PCAP required');
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH, args: ['--no-proxy-server'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const dialogs = [], errors = [];
    page.on('dialog', async d => { dialogs.push(d.message()); await d.dismiss(); });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('#password').fill(process.env.APP_PASSWORD);
    await page.locator('#login').click();
    await page.waitForFunction(() => document.querySelector('#identity').textContent === '分析员');
    await page.locator('#overview .metric strong').first().waitFor();
    fs.mkdirSync('tmp/browser', { recursive: true });
    await page.screenshot({ path: 'tmp/browser/overview.png', fullPage: true });
    await page.locator('[data-view="jobs"]').click();
    await page.locator('#file').setInputFiles(process.env.TEST_PCAP);
    await page.locator('#upload').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('任务已提交：'));
    const status = await page.locator('#status').textContent();
    const task = status.match(/[a-f0-9]{32}/)[0];
    const authorization = 'Basic ' + Buffer.from('analyst:' + process.env.APP_PASSWORD).toString('base64');
    for (let i = 0; i < 90; i++) {
      const response = await page.request.get(base + '/api/tasks', { headers: { Authorization: authorization } });
      const job = (await response.json()).find(t => t.id === task);
      if (job.status === 'failed') throw Error(job.error);
      if (job.status === 'complete') break;
      if (i === 89) throw Error('task timeout');
      await new Promise(r => setTimeout(r, 1000));
    }
    await page.locator('#refresh').click();
    await page.locator('#tasks button').first().click();
    await page.locator('#alerts details').first().waitFor();
    await page.locator('#alerts summary').first().click();
    await page.getByRole('button', { name: '加载完整详情' }).first().click();
    await page.waitForFunction(() => document.querySelector('#alerts pre').textContent.includes('原始 EVE 事件'));
    const evidence = await page.locator('#alerts pre').first().textContent();
    if (!evidence.includes('onerror')) throw Error('attack marker missing from evidence');
    if (await page.locator('#alerts img').count()) throw Error('payload created an HTML image');
    if (dialogs.length || errors.length) throw Error(JSON.stringify({ dialogs, errors }));
    await page.screenshot({ path: 'tmp/browser/investigation.png', fullPage: true });
    await page.locator('[data-view="policies"]').click();
    if (await page.locator('#rules input[type=checkbox]').count() < 5) throw Error('rules missing');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('[data-view="overview"]').click();
    await page.screenshot({ path: 'tmp/browser/mobile.png', fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
    if (overflow) throw Error('mobile horizontal overflow');
    const result={ tested_at: new Date().toISOString(), url: base, login: true, navigation: true, upload: true, detail: true, xss_text_only: true, rules: true, mobile_no_overflow: true, task };
    fs.writeFileSync('validation/browser-smoke.json',JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
