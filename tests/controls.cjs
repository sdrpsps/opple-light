/* Exercise Vue state and mutations using an isolated, fully mocked API. */
const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function testControls(browser, base, artifacts) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const errors = [], unexpected = [], patches = [], operations = new Map();
  const dialogRequests = [];
  page.on('request', request => {
    const asset = new URL(request.url()).pathname;
    if (/\/(Login|Scene|Timer|Settings)Dialog-[^/]+\.js$/.test(asset)) dialogRequests.push(asset);
  });
  const assertLoadedDialogs = names => {
    assert.deepEqual(dialogRequests.map(asset => asset.match(/\/(\w+Dialog)-/)[1]).sort(), [...names].sort());
  };
  let sequence = 0, scenes = [], rejectNext = false, disconnectNext = false;
  const light = {
    id: 'bedroom', name: '测试灯具', host: '127.0.0.1', online: true,
    state: { power: true, brightness_percent: 70, color_temperature_kelvin: 4000 },
    pending_settings: {}, capabilities: { min_kelvin: 3000, max_kelvin: 5700 },
    last_seen: new Date().toISOString(), timer: null,
  };
  page.on('pageerror', error => errors.push(error.message));
  const operation = (route, body) => {
    const id = String(++sequence);
    operations.set(id, { body, reads: 0 });
    return route.fulfill({ status: 202, json: { id, status: 'pending' } });
  };
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), method = req.method();
    const endpoint = url.pathname.replace('/api/v1', '');
    const json = data => route.fulfill({ json: data });
    if (endpoint === '/session' && method === 'GET') return json({ authenticated: true });
    if (endpoint === '/status' && method === 'GET') return json({ server_time: Date.now()/1000, lights: [light] });
    if (endpoint === '/scenes' && method === 'GET') return json(scenes);
    if (endpoint === '/events' && method === 'GET') return json([{ at: new Date().toISOString(), kind: 'confirmed', message: '灯光已更新' }]);
    if (endpoint === '/lights/bedroom/state' && method === 'PATCH') {
      const body = req.postDataJSON(); patches.push(body);
      if (disconnectNext) { disconnectNext = false; return route.abort('failed'); }
      if (rejectNext) { rejectNext = false; return route.fulfill({ status: 503, json: { detail: '测试连接中断' } }); }
      return operation(route, body);
    }
    if (endpoint.startsWith('/operations/') && method === 'GET') {
      const id = endpoint.split('/').at(-1), entry = operations.get(id);
      if (++entry.reads < 2) return json({ id, status: 'running' });
      const staged = !light.state.power && entry.body.power == null;
      if (staged) Object.assign(light.pending_settings, entry.body);
      else {
        Object.assign(light.state, entry.body.power ? light.pending_settings : {}, entry.body);
        if (entry.body.power) light.pending_settings = {};
      }
      return json({ id, status: staged ? 'staged' : 'confirmed', message: staged ? '已保存下次开灯设置' : '灯光已更新' });
    }
    if (endpoint === '/lights/bedroom/scenes' && method === 'POST') {
      const scene = { ...req.postDataJSON(), id: 'scene-1', light_id: 'bedroom' };
      scenes.push(scene); return json(scene);
    }
    if (endpoint === '/scenes/scene-1' && method === 'PUT') {
      Object.assign(scenes[0], req.postDataJSON()); return json(scenes[0]);
    }
    if (endpoint === '/scenes/scene-1' && method === 'DELETE') {
      scenes = []; return route.fulfill({ status: 204 });
    }
    if (endpoint === '/scenes/scene-1/apply' && method === 'POST') {
      return operation(route, { power: true, color_temperature_kelvin: scenes[0].color_temperature_kelvin, brightness_percent: scenes[0].brightness_percent });
    }
    if (endpoint === '/lights/bedroom/timer' && method === 'PUT') {
      light.timer = { status: 'active', due_at: Date.now()/1000 + req.postDataJSON().minutes*60 };
      return json(light.timer);
    }
    if (endpoint === '/lights/bedroom/timer' && method === 'DELETE') {
      light.timer = null; return route.fulfill({ status: 204 });
    }
    if (endpoint === '/lights/bedroom/refresh' && method === 'POST') return json({ queued: true });
    if (endpoint === '/backup' && method === 'GET') return json({ lights: [light], scenes });
    unexpected.push(`${method} ${endpoint}`);
    return route.fulfill({ status: 404, json: { detail: 'Unexpected test request' } });
  });
  const switchState = async value => {
    await page.waitForFunction(value => {
      const button = document.querySelector('#power-button');
      return button && !button.disabled && button.getAttribute('aria-checked') === String(value);
    }, value);
  };
  const range = async (selector, value, commit = true) => {
    await page.locator(selector).evaluate((el, { value, commit }) => {
      el.value = value; el.dispatchEvent(new Event('input', { bubbles: true }));
      if (commit) el.dispatchEvent(new Event('change', { bubbles: true }));
    }, { value, commit });
  };
  const idle = () => page.waitForFunction(() => document.querySelector('#power-description').textContent !== '正在更新灯光…');
  try {
    await page.goto(base); await switchState(true);
    assert.equal(await page.locator('dialog').count(), 0);
    assertLoadedDialogs([]);
    // Initial preset alignment must be correct even when the first value is 4000 K.
    const indicator = await page.locator('.preset-indicator').boundingBox();
    const middle = await page.locator('[data-kelvin="4000"]').boundingBox();
    assert(Math.abs(indicator.x - middle.x) < 2);
    const initialWrites = patches.length;
    await range('#brightness', 62, false);
    assert.match(await page.locator('#brightness-value').textContent(), /62/);
    assert.equal(patches.length, initialWrites, 'preview must not send API writes');
    await range('#brightness', 64);
    await page.waitForFunction(() => document.querySelector('#power-description').textContent === '正在更新灯光…');
    await range('#brightness', 83);
    await idle();
    assert.equal(light.state.brightness_percent, 83);
    assert.deepEqual(patches.slice(-2), [{ brightness_percent: 64 }, { brightness_percent: 83 }]);
    await page.locator('#power-button').click(); await switchState(false);
    await page.locator('[data-kelvin="3000"]').click(); await idle();
    assert.equal(light.state.color_temperature_kelvin, 4000);
    assert.equal(light.pending_settings.color_temperature_kelvin, 3000);
    assert.match(await page.locator('#control-hint').textContent(), /已保存下次开灯设置/);
    await page.locator('#power-button').click(); await switchState(true);
    assert.equal(light.state.color_temperature_kelvin, 3000);
    const writesBeforeFailure = patches.length;
    rejectNext = true; await range('#brightness', 15); await idle();
    assert.match(await page.locator('#toast').textContent(), /测试连接中断/);
    assert.equal(await page.locator('#brightness').inputValue(), '83');
    assert.equal(patches.length, writesBeforeFailure + 1, 'HTTP failure must not replay a command');
    disconnectNext = true; await range('#brightness', 20); await idle();
    assert.match(await page.locator('#toast').textContent(), /服务暂时无法连接/);
    assert.equal(patches.length, writesBeforeFailure + 2, 'network failure must not replay a command');
    assert.equal(light.state.brightness_percent, 83);
    await page.locator('#add-scene').click();
    await page.locator('#scene-dialog[open]').waitFor();
    assertLoadedDialogs(['SceneDialog']);
    assert.equal(await page.locator('#scene-kelvin').inputValue(), '3000');
    assert.equal(await page.locator('#scene-brightness').inputValue(), '83');
    await page.locator('#scene-name').fill('睡前阅读');
    await page.locator('#scene-kelvin').fill('3300');
    await page.locator('#scene-brightness').fill('25');
    await page.locator('#scene-icon').selectOption('book');
    await page.locator('#scene-form button[type=submit]').click();
    await page.locator('.scene-apply').waitFor();
    assert.equal(scenes[0].color_temperature_kelvin, 3300);
    await page.locator('.scene-edit').click();
    assert.equal(await page.locator('#scene-name').inputValue(), '睡前阅读');
    assert.equal(await page.locator('#scene-kelvin').inputValue(), '3300');
    assert.equal(await page.locator('#scene-brightness').inputValue(), '25');
    await page.locator('#scene-name').fill('夜间阅读');
    await page.locator('#scene-form button[type=submit]').click();
    await page.getByRole('button', { name: '应用夜间阅读场景' }).click(); await idle();
    assert.equal(light.state.brightness_percent, 25);
    assert.equal(await page.locator('.scene-apply').getAttribute('aria-pressed'), 'true');
    await page.locator('[data-minutes="15"]').click();
    await page.locator('#timer-active').waitFor();
    assert.match(await page.locator('#timer-remaining').textContent(), /^1[45]:\d\d$/);
    await page.locator('#cancel-timer').click(); await page.locator('#timer-options').waitFor();
    // Completion is detected while applying a fresh snapshot, without a timer watcher.
    light.timer = { status: 'executing', due_at: Date.now()/1000 };
    await page.locator('#refresh-button').click();
    await page.waitForFunction(() => document.querySelector('#timer-description').textContent.includes('正在确认关灯'));
    light.timer.status = 'completed';
    await page.locator('#refresh-button').click();
    await page.waitForFunction(() => document.querySelector('#toast')?.textContent.includes('倒计时结束，已关灯'));
    await page.locator('#timer-options').waitFor();
    await page.locator('#custom-timer').click();
    await page.locator('#timer-dialog[open]').waitFor();
    assertLoadedDialogs(['SceneDialog', 'TimerDialog']);
    await page.locator('#timer-minutes').fill('60');
    await page.keyboard.press('Escape');
    await page.locator('#timer-dialog').waitFor({ state: 'hidden' });
    await page.locator('#custom-timer').click();
    await page.locator('#timer-dialog[open]').waitFor();
    assert.equal(await page.locator('#timer-minutes').inputValue(), '60');
    assertLoadedDialogs(['SceneDialog', 'TimerDialog']);
    await page.locator('#timer-minutes').fill('45');
    await page.locator('#timer-form button[type=submit]').click(); await page.locator('#timer-active').waitFor();
    assert(light.timer.due_at > Date.now()/1000 + 2600);
    await page.locator('#cancel-timer').click(); await page.locator('#timer-options').waitFor();
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => scrollTo(0, 0));
    await page.locator('#toast').waitFor({ state: 'detached' });
    await page.screenshot({ path: path.join(artifacts, 'vue-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: path.join(artifacts, 'vue-mobile.png'), fullPage: true });
    await page.locator('#settings-button').click();
    await page.locator('#settings-dialog[open]').waitFor();
    await page.waitForFunction(() => document.querySelector('#event-list').textContent.includes('灯光已更新'));
    assertLoadedDialogs(['SceneDialog', 'TimerDialog', 'SettingsDialog']);
    assert.match(await page.locator('#event-list').textContent(), /灯光已更新/);
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#backup-button').click();
    assert.equal((await downloadPromise).suggestedFilename(), 'opple-backup.json');
    await page.keyboard.press('Escape');
    await page.locator('#settings-dialog').waitFor({ state: 'hidden' });
    await page.locator('.scene-edit').click();
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#delete-scene').click();
    await page.locator('.scene-apply').waitFor({ state: 'detached' });
    assert.equal(scenes.length, 0);
    light.online = false;
    await page.waitForFunction(() => document.querySelector('#power-button').disabled);
    assert(await page.locator('#temperature').isDisabled());
    assert.match(await page.locator('#connection-warning').textContent(), /正在连接灯具/);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
    console.log('PASS: Vue preview, queued slider changes, power, staged settings, error recovery, scene CRUD/apply, timers, backup, offline state and responsive layouts');
  } finally { await context.close(); }
};
