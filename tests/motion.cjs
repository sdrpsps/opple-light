const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext(); const page=await context.newPage(); const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.TEST_URL||'http://127.0.0.1:8086';
 const out=process.env.TEST_ARTIFACTS||'screenshots/motion';fs.mkdirSync(out,{recursive:true});
 await page.route('**/api/v1/**',route=>route.request().method()==='GET'?route.continue():route.abort());
 try{
  await page.goto(base); await page.locator('#power-button:not([disabled])').waitFor();
  for(const width of [320,390,768,1440]) {
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Overflow '+width);
   assert.equal(await page.locator('#temperature').evaluate(e=>e.getBoundingClientRect().height>=44),true);
  }
  await page.screenshot({path:out+'/desktop.png',fullPage:true});
  await page.locator('#settings-button').click();
  await page.waitForTimeout(600);
  await page.evaluate(()=>{const d=document.querySelector('#settings-dialog');LightMotion.close(d);setTimeout(()=>LightMotion.open(d),70)});
  await page.waitForTimeout(700);assert.equal(await page.locator('#settings-dialog').evaluate(e=>e.open),true);
  await page.keyboard.press('Escape');await page.waitForTimeout(700);
  assert.equal(await page.locator('#settings-dialog').evaluate(e=>e.open),false);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#settings-button').click();await page.waitForTimeout(600);
  await page.screenshot({path:out+'/mobile-sheet.png',fullPage:true});
  const header=await page.locator('#settings-dialog .dialog-heading').boundingBox();
  await page.mouse.move(header.x+90,header.y+22);await page.mouse.down();
  await page.mouse.move(header.x+90,header.y+230,{steps:12});await page.mouse.up();await page.waitForTimeout(750);
  assert.equal(await page.locator('#settings-dialog').evaluate(e=>e.open),false,'Swipe dismiss');
  await page.screenshot({path:out+'/mobile.png',fullPage:true});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.locator('#settings-button').click();
  assert.equal(await page.locator('#settings-dialog').evaluate(e=>e.style.transform),'none');
  await page.locator('[data-close="settings-dialog"]').click();assert.equal(await page.locator('#settings-dialog').evaluate(e=>e.open),false);
  assert.deepEqual(errors,[]);
  console.log('Passed: 320/390/768/1440 layout, 44px slider hit area, interrupt and reopen, Escape, mobile swipe dismissal, reduced motion, no JS errors. No API writes.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
