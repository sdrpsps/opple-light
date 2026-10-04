/* Run against the isolated DEMO service only. Requires `playwright`. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const url = process.env.TEST_URL || 'http://127.0.0.1:8086';
const artifacts = path.resolve(process.env.TEST_ARTIFACTS || 'test-artifacts/browser');

(async () => {
  const session = await (await fetch(url + '/api/v1/session')).json();
  assert.equal(session.mode, 'demo', 'Browser write tests MUST run against demo mode');
  assert.equal(session.authenticated, true, 'Start the demo with OPPLE_DEMO_OPEN=1');
  fs.mkdirSync(artifacts, {recursive:true});
  const browser = await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL ? {channel:process.env.PLAYWRIGHT_CHANNEL} : {})});
  const context = await browser.newContext({viewport:{width:1440,height:1100},deviceScaleFactor:1});
  const page = await context.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = async () => (await page.request.get(url + '/api/v1/lights/bedroom')).json();
  const until = async (predicate, timeout = 10000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) { if (await predicate()) return; await page.waitForTimeout(100); }
    throw new Error('Condition not met before deadline');
  };
  try {
    await page.goto(url);
    await page.getByText('演示在线', {exact:true}).waitFor();
    await page.screenshot({path:path.join(artifacts,'desktop.png'),fullPage:true});
    await page.getByRole('switch').click();
    await until(async () => !(await state()).state.power);
    await page.waitForTimeout(500);
    await page.locator('#temperature').evaluate(input => { input.value = '3200'; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); });
    await until(async () => (await state()).pending_settings.color_temperature_kelvin === 3200);
    assert.equal((await state()).state.power,false);
    await page.getByRole('switch').click();
    await until(async () => (await state()).state.power && (await state()).state.color_temperature_kelvin === 3200);
    await until(async () => await page.getByRole('button',{name:'应用阅读场景'}).isEnabled());
    await page.getByRole('button',{name:'应用阅读场景'}).click();
    await until(async () => (await state()).state.color_temperature_kelvin === 5000 && (await state()).state.brightness_percent === 90);
    await page.getByRole('button',{name:'保存当前灯光'}).click();
    await page.locator('#scene-name').fill('晨间测试');
    await page.locator('#scene-kelvin').fill('4200');
    await page.locator('#scene-brightness').fill('65');
    await page.getByRole('button',{name:'保存场景',exact:true}).click();
    await page.getByRole('button',{name:'应用晨间测试场景'}).waitFor();
    await page.getByRole('button',{name:'编辑晨间测试场景'}).click();
    await page.locator('#scene-name').fill('晨间测试已编辑');
    await page.getByRole('button',{name:'保存场景',exact:true}).click();
    await page.getByRole('button',{name:'编辑晨间测试已编辑场景'}).click();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button',{name:'删除场景',exact:true}).click();
    await until(async () => await page.getByRole('button',{name:'应用晨间测试已编辑场景'}).count() === 0);
    await page.getByRole('button',{name:'15 分钟',exact:true}).click();
    await page.getByRole('button',{name:'取消倒计时',exact:true}).waitFor();
    await page.getByRole('button',{name:'取消倒计时',exact:true}).click();
    await until(async () => (await state()).timer.status === 'cancelled');
    await context.setOffline(true);
    await page.getByText('服务连接中断。请检查运行服务的设备，页面会自动重连。').waitFor({timeout:18000});
    assert.equal(await page.getByRole('switch').isDisabled(),true);
    await context.setOffline(false);
    await page.getByText('演示在线',{exact:true}).waitFor({timeout:18000});
    await page.getByRole('button',{name:'设置与记录'}).click();
    await page.getByRole('heading',{name:'最近操作',exact:true}).waitFor();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button',{name:'导出配置备份'}).click();
    const download = await downloadPromise;
    await download.saveAs(path.join(artifacts,'test-backup.json'));
    const backup = JSON.parse(fs.readFileSync(path.join(artifacts,'test-backup.json'),'utf8'));
    assert.equal(backup.config.mode,'demo');
    assert.equal(JSON.stringify(backup).includes('access-token'),false);
    await page.getByRole('button',{name:'关闭设置'}).click();
    await page.getByRole('button',{name:'自定义',exact:true}).click();
    await page.locator('#timer-minutes').fill('1');
    await page.getByRole('button',{name:'开始倒计时',exact:true}).click();
    await until(async () => (await state()).timer.status === 'active');
    console.log('Interactions passed; verifying actual 60-second countdown…');
    for (const width of [390, 320, 768]) {
      await page.setViewportSize({width,height:844});
      await page.waitForTimeout(100);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false, `Overflow at ${width}px`);
      if (width === 390) await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
    }
    await until(async () => (await state()).timer.status === 'completed',75000);
    assert.equal((await state()).state.power,false,'Countdown must really turn the demo lamp off');
    await page.setViewportSize({width:1440,height:1100});
    await page.getByRole('button',{name:'应用日常场景'}).click();
    await until(async () => (await state()).state.power && (await state()).state.color_temperature_kelvin === 4000);
    await page.waitForTimeout(3500);
    await page.screenshot({path:path.join(artifacts,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
    assert.deepEqual(errors,[],'No JavaScript errors');
    console.log('Browser checks passed: controls, staging, scenes CRUD, timer expiry/cancel, reconnect, backup, responsive 320/390/768/1440, no JS errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
