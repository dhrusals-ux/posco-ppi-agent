import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const errs=[];
const b = await chromium.launch({executablePath: CHROME});
const SP = WRAP_URL;
for (const scheme of ['light','dark']) {
  const ctx = await b.newContext({colorScheme:scheme, viewport:{width:1200,height:820}});
  const p = await ctx.newPage();
  p.on('pageerror',e=>errs.push(scheme+': '+e.message));
  p.on('dialog',d=>d.accept());
  await p.goto(SP+'wrapped.html'); await p.waitForTimeout(400);
  await p.click('#btn-menu'); await p.click('#m-sample'); await p.waitForTimeout(600);
  const bg = await p.evaluate(()=>getComputedStyle(document.body).backgroundColor);
  const fg = await p.evaluate(()=>getComputedStyle(document.body).color);
  console.log(scheme,'| body bg',bg,'fg',fg,'| entries',await p.locator('.entry').count());
  await p.click('#tabs button[data-view="month"]'); await p.waitForTimeout(400);
  await p.screenshot({path:`/tmp/wrap-${scheme}.png`});
  await ctx.close();
}
// iframe(임베드) 환경: 안내문 노출 + 기본 동작
const ctx = await b.newContext({viewport:{width:1100,height:760}});
const p = await ctx.newPage();
p.on('pageerror',e=>errs.push('embed: '+e.message));
await p.goto(SP+'embed.html'); await p.waitForTimeout(600);
const f = p.frames()[1];
await f.click('#btn-menu'); await p.waitForTimeout(200);
console.log('embed note visible:', await f.locator('#embed-note').isVisible());
await f.click('#m-sample'); await p.waitForTimeout(700);
console.log('embed entries:', await f.locator('.entry').count());
report('embed-themes', errs);
await b.close();
