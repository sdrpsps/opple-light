/* Browser tests serve only static assets and mock all APIs. No real device calls. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const staticRoot = path.resolve(__dirname, '../frontend/dist');
const artifacts = path.resolve(process.env.TEST_ARTIFACTS || 'test-artifacts/browser');
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.json':'application/json'};

(async () => {
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, 'http://localhost').pathname;
    const file = path.resolve(staticRoot, '.' + (['/', '/auth/callback'].includes(name) ? '/index.html' : name));
    if (!file.startsWith(staticRoot + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, {'Content-Type': mime[path.extname(file)] || 'application/octet-stream'});
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
  try {
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage(), errors = [], writes = [];
    let authenticated = false;
    let loginEnabled = true;
    const light = {id:'bedroom',name:'测试灯具',host:'127.0.0.1',online:true,
      state:{power:true,brightness_percent:70,color_temperature_kelvin:4000},
      pending_settings:{},capabilities:{min_kelvin:3000,max_kelvin:5700},last_seen:new Date().toISOString(),timer:null};
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/v1/**', route => {
      const request = route.request(), url = new URL(request.url());
      if (url.pathname === '/api/v1/session' && request.method() === 'GET') return route.fulfill({json:{authenticated,login_enabled:loginEnabled}});
      if (url.pathname === '/api/v1/session' && request.method() === 'DELETE') {
        authenticated = false; return route.fulfill({json:{authenticated:false}});
      }
      if (request.method() !== 'GET') { writes.push(request.method() + ' ' + url.pathname); return route.abort(); }
      if (!authenticated) return route.fulfill({status:401,json:{detail:'请通过 Pocket ID 登录'}});
      if (url.pathname === '/api/v1/status') return route.fulfill({json:{name:'一室光',server_time:Date.now()/1000,lights:[light]}});
      if (['/api/v1/scenes','/api/v1/events'].includes(url.pathname)) return route.fulfill({json:[]});
      return route.fulfill({status:404,json:{detail:'Test API fixture missing'}});
    });
    const base = 'http://127.0.0.1:' + server.address().port;
    await page.goto(base);
    await page.locator('#login-dialog[open]').waitFor();
    assert.equal(await page.locator('dialog').count(), 1);
    assert.equal(await page.locator('#pocket-login').getAttribute('href'), '/auth/login');
    assert(await page.locator('#pocket-login').isVisible());
    assert.equal(await page.locator('input[type=password], #login-form').count(), 0);
    assert.match(await page.locator('#login-description').textContent(), /通行密钥/);
    for (const width of [320,390,768,1440]) {
      await page.setViewportSize({width,height:844});
      await page.waitForTimeout(500);
      const layout = await page.evaluate(() => {
        const dialog = document.querySelector('#login-dialog').getBoundingClientRect();
        const description = document.querySelector('#login-description').getBoundingClientRect();
        const button = document.querySelector('#pocket-login').getBoundingClientRect();
        return {x:dialog.x,right:dialog.right,bottom:dialog.bottom,gap:button.top-description.bottom};
      });
      assert(layout.x >= 15 && layout.right <= width-15);
      assert(layout.bottom <= 844 && layout.gap >= 18);
    }
    await page.setViewportSize({width:390,height:844});
    fs.mkdirSync(artifacts,{recursive:true});
    await page.screenshot({path:path.join(artifacts,'pocket-login.png')});
    authenticated = true;
    await page.reload();
    await page.locator('#power-button:not([disabled])').waitFor();
    assert(!(await page.locator('#login-dialog').isVisible()));
    assert.equal(await page.locator('#device-status span').textContent(), '设备在线');
    for (const width of [320,390,768,1440]) {
      await page.setViewportSize({width,height:1000});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert(await page.locator('#temperature').evaluate(el => el.getBoundingClientRect().height >= 44));
    }
    await page.locator('#settings-button').click();
    await page.waitForTimeout(600);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(70);
    await page.locator('#settings-button').evaluate(el => el.click());
    await page.waitForTimeout(700);
    assert(await page.locator('#settings-dialog').evaluate(el => el.open));
    await page.keyboard.press('Escape'); await page.waitForTimeout(650);
    assert(!(await page.locator('#settings-dialog').evaluate(el => el.open)));
    await page.setViewportSize({width:390,height:844});
    await page.locator('#settings-button').click(); await page.waitForTimeout(600);
    const header = await page.locator('#settings-dialog .dialog-heading').boundingBox();
    await page.mouse.move(header.x+90,header.y+22); await page.mouse.down();
    await page.mouse.move(header.x+90,header.y+230,{steps:12}); await page.mouse.up(); await page.waitForTimeout(700);
    assert(!(await page.locator('#settings-dialog').evaluate(el => el.open)));
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.locator('#settings-button').click();
    assert.equal(await page.locator('#settings-dialog').evaluate(el => el.style.transform),'none');
    assert(await page.locator('#logout-button').isVisible());
    await page.locator('#logout-button').click();
    await page.locator('#login-dialog[open]').waitFor();
    authenticated = true; await page.reload();
    await page.locator('#power-button:not([disabled])').waitFor();
    authenticated = false;
    await page.locator('#login-dialog[open]').waitFor({timeout:6000});
    assert(await page.locator('#power-button').isDisabled());
    assert.deepEqual(writes, []);
    assert.deepEqual(errors, []);
    loginEnabled = false; authenticated = true;
    await page.reload();
    await page.locator('#power-button:not([disabled])').waitFor();
    assert(!(await page.locator('#login-dialog').isVisible()));
    await page.locator('#settings-button').click();
    await page.locator('#settings-dialog[open]').waitFor();
    assert.equal(await page.locator('#logout-button').count(), 0);
    await page.goto(base + '/auth/callback?error=invalid_request&code=secret-code&state=secret-state');
    await page.getByRole('heading', {name:'登录未完成'}).waitFor();
    assert.match(await page.getByRole('alert').textContent(), /登录参数/);
    assert.equal(await page.getByRole('link', {name:'重新通过 Pocket ID 登录'}).getAttribute('href'), '/auth/login');
    assert.equal(page.url(), base + '/auth/callback');
    await page.goto(base + '/auth/callback?error=%3Cscript%3Esecret-code%3C%2Fscript%3E');
    await page.getByRole('heading', {name:'登录未完成'}).waitFor();
    assert(!(await page.locator('body').textContent()).includes('secret-code'));
    assert.deepEqual(errors, []);
    await require('./controls.cjs')(browser, base, artifacts);
    await require('./hooks.cjs')(browser, base);
    console.log('PASS: Pocket ID login-only UI, logout, expired session, layouts, interruptible dialogs, swipe, reduced motion; no device requests');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error);process.exitCode=1});
