/* Mount feature hooks in effect scopes without App.vue or a controller. */
const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function testHooks(browser, base) {
  const { build } = await import('vite');
  const entry = path.resolve(__dirname, '__hook_harness.js');
  const source = `
    export { effectScope } from 'vue';
    export { useLightUI } from '../frontend/src/composables/useLightUI.ts';
    export { useLightSettings } from '../frontend/src/composables/useLightSettings.ts';
    export { useLightSync } from '../frontend/src/composables/useLightSync.ts';
  `;
  const bundle = await build({
    configFile: false, logLevel: 'silent',
    plugins: [{ name: 'hook-harness',
      resolveId: id => id === 'virtual:hook-harness' ? entry : undefined,
      load: id => id === entry ? source : undefined,
    }],
    build: { write: false, minify: false,
      rollupOptions: { input: 'virtual:hook-harness', preserveEntrySignatures: 'strict', output: { format: 'iife', name: 'HookHarness' } },
    },
  });
  const script = bundle.output.find(item => item.type === 'chunk').code;
  const context = await browser.newContext();
  const page = await context.newPage();
  const requests = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/__hooks', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Hooks</title>' }));
  await page.route('**/api/v1/**', route => {
    const endpoint = new URL(route.request().url()).pathname.replace('/api/v1', '');
    requests.push(endpoint);
    if (endpoint === '/session') return route.fulfill({ json: { authenticated: true } });
    if (endpoint === '/events') return route.fulfill({ json: [{ at: new Date().toISOString(), message: '独立记录', kind: 'confirmed' }] });
    if (endpoint === '/status') return route.fulfill({ json: { server_time: Date.now()/1000, lights: [] } });
    return route.fulfill({ status: 404 });
  });
  try {
    await page.goto(base + '/__hooks');
    await page.addScriptTag({ content: script });
    await page.evaluate(() => {
      const { effectScope, useLightUI } = HookHarness;
      const first = effectScope(), second = effectScope();
      const a = first.run(useLightUI), b = second.run(useLightUI);
      if (a !== b) throw new Error('Consumers must share one feature instance');
      a.openDialog('timer');
      first.stop();
      if (b.dialog.value !== 'timer') throw new Error('Remaining consumer lost state');
      second.stop();
      const fresh = effectScope();
      const c = fresh.run(useLightUI);
      if (c === a || c.dialog.value !== null || c.loadedDialogs.timer) throw new Error('Disposed feature state must reset');
      fresh.stop();
    });
    assert.deepEqual(requests, [], 'UI alone must not initialize API features');
    await page.evaluate(async () => {
      const scope = HookHarness.effectScope();
      const settings = scope.run(HookHarness.useLightSettings);
      await settings.openSettings();
      if (settings.events.value[0]?.message !== '独立记录') throw new Error('Settings hook failed without App/controller');
      scope.stop();
    });
    assert.deepEqual([...requests].sort(), ['/events', '/session'], 'Settings must not start lights or scenes');
    requests.length = 0;
    await page.evaluate(() => {
      window.syncScope = HookHarness.effectScope();
      window.syncHook = syncScope.run(HookHarness.useLightSync);
    });
    await page.waitForFunction(() => syncHook.snapshot.value !== null);
    assert.deepEqual([...requests].sort(), ['/session', '/status'], 'Sync must not initialize unrelated features');
    await page.evaluate(() => syncScope.stop());
    const before = requests.length;
    await page.waitForTimeout(3300);
    assert.equal(requests.length, before, 'Disposing the last consumer must stop polling');
    assert.deepEqual(errors, []);
    console.log('PASS: independent hooks without App/controller, shared instances, scope reset, lazy dependencies and polling cleanup');
  } finally { await context.close(); }
};

if (require.main === module) {
  (async () => {
    const { chromium } = require('playwright');
    const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
    try { await module.exports(browser, 'http://hooks.test'); }
    finally { await browser.close(); }
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
