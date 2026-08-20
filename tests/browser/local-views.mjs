import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const errors=[];
const browser = await chromium.launch({ executablePath: CHROME });
const page = await browser.newPage({ viewport:{width:1280,height:900} });
page.on('console', m=>{ if(m.type()==='error') errors.push(m.text()); });
page.on('pageerror', e=>errors.push('PAGEERROR: '+e.message));
page.on('dialog', d=>d.accept());
await page.goto(FILE_URL);
await page.waitForTimeout(400);
// 빈 상태 확인
console.log('empty state:', (await page.textContent('.empty'))?.slice(0,20));
await page.click('#btn-menu'); await page.click('#m-sample'); await page.waitForTimeout(600);
// 통계 뷰: nav 숨김 확인
await page.click('#tabs button[data-view="stats"]'); await page.waitForTimeout(400);
console.log('stats nav hidden:', !(await page.locator('#prev').isVisible()));
console.log('weekday zero rows:', await page.locator('.panel:has(h3:text("요일별")) .bar-row .val').allTextContents());
// 라이트 테마
await page.click('#btn-menu'); await page.click('#m-theme'); await page.waitForTimeout(300);
await page.screenshot({path:TMP+'/shot-light.png'});
console.log('theme:', await page.getAttribute('html','data-theme'));
// 다시 다크 + 일별 nav 복귀
await page.click('#btn-menu'); await page.click('#m-theme');
await page.click('#tabs button[data-view="day"]'); await page.waitForTimeout(300);
console.log('day nav visible again:', await page.locator('#prev').isVisible());
// 삭제 흐름
const before = await page.locator('.entry').count();
if(before){ await page.locator('.entry .del').first().click(); await page.waitForTimeout(500); }
console.log('entries', before, '->', await page.locator('.entry').count());
// 전체 삭제
await page.click('#btn-menu'); await page.click('#m-wipe'); await page.waitForTimeout(600);
console.log('after wipe:', await page.locator('.entry').count(), '| empty box:', await page.locator('.empty').count());
report('local-views', errors);
await browser.close();
