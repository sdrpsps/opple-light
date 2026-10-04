// Isolated UI verification; the backend runs in demo mode. No lamp writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
  try {
    for (const mode of ['pocketid', 'token', 'open']) {
      const page = await browser.newPage({viewport: {width: 390, height: 844}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/v1/session', route => route.fulfill({json: {
        authenticated: mode === 'open', auth_required: mode !== 'open', auth_mode: mode
      }}));
      await page.route('**/api/v1/**', route => {
        if (!['GET', 'HEAD'].includes(route.request().method())) throw new Error('Unexpected API write');
        return route.fallback();
      });
      await page.goto(process.env.TEST_URL || 'http://127.0.0.1:8087/');
      await page.waitForFunction(mode => mode === 'open' ? !document.querySelector('#login-dialog').open : document.querySelector('#login-dialog').open, mode);
      if (mode === 'pocketid') {
        assert(await page.locator('#pocket-login').isVisible());
        assert(!(await page.locator('#login-form').isVisible()));
        assert.equal(await page.locator('#pocket-login').getAttribute('href'), '/auth/login');
        assert.match(await page.locator('#login-description').textContent(), /通行密钥/);
      } else if (mode === 'token') {
        assert(await page.locator('#login-form').isVisible());
        assert(!(await page.locator('#pocket-login').isVisible()));
      } else {
        assert(!(await page.locator('#login-dialog').isVisible()));
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS: Pocket ID, token and open login UI; no API writes or JavaScript errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
