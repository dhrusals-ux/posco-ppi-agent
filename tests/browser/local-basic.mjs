import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
import fs from 'fs';

const errors = [];
const browser = await chromium.launch({ executablePath: CHROME });
const page = await browser.newPage({ viewport:{width:1280,height:900} });
page.on('console', m => { if(m.type()==='error') errors.push('CONSOLE: '+m.text()); });
page.on('pageerror', e => errors.push('PAGEERROR: '+e.message));
page.on('dialog', d => d.accept());

await page.goto(FILE_URL);
await page.waitForTimeout(400);

// 샘플 데이터
await page.click('#btn-menu');
await page.click('#m-sample');
await page.waitForTimeout(700);
const entries = await page.locator('.entry').count();
console.log('day view entries:', entries);

// 새 일지 작성 + 이미지 업로드
await page.click('#btn-new');
await page.fill('#f-symbol','테스트종목');
await page.fill('#f-entry','1000');
await page.fill('#f-exit','1100');
await page.fill('#f-qty','10');
await page.waitForTimeout(150);
const autoPnl = await page.inputValue('#f-pnl');
const autoPct = await page.inputValue('#f-pnlpct');
console.log('auto pnl/pct:', autoPnl, autoPct);
await page.click('#f-rating button[data-v="4"]');
await page.fill('#f-tags','돌파매매, 테스트');
await page.fill('#f-comment','자동 테스트 코멘트\n두번째 줄');
await page.setInputFiles('#file',CHART);
await page.waitForTimeout(900);
console.log('thumbs in form:', await page.locator('.thumb').count());
await page.click('#btn-save');
await page.waitForTimeout(700);
console.log('after save, entries:', await page.locator('.entry').count());
console.log('shots rendered:', await page.locator('.shots img').count());

// 라이트박스
await page.click('.shots img');
await page.waitForTimeout(300);
console.log('lightbox open:', await page.locator('#lightbox.on').count());
await page.keyboard.press('Escape');

// 뷰 전환
for (const v of ['week','month','stats','day']) {
  await page.click(`#tabs button[data-view="${v}"]`);
  await page.waitForTimeout(350);
  const label = await page.textContent('#period-label');
  console.log(v, '->', label, '| cards:', await page.locator('.stat').count());
  await page.screenshot({ path: `/tmp/shot-${v}.png`, fullPage:false });
}

// 월간에서 날짜 클릭 → 일별 이동
await page.click('#tabs button[data-view="month"]');
await page.waitForTimeout(300);
await page.locator('.cell:not(.out)').nth(0).click();
await page.waitForTimeout(300);
console.log('after cell click, view label:', await page.textContent('#period-label'));

// 검색
await page.click('#tabs button[data-view="stats"]');
await page.fill('#q','돌파');
await page.waitForTimeout(300);
console.log('search stats total:', await page.textContent('#stats-cards .stat .v'));
await page.fill('#q','');

// 편집
await page.click('#tabs button[data-view="day"]');
await page.click('#btn-today');
await page.waitForTimeout(300);
await page.locator('.entry .edit').first().click();
await page.waitForTimeout(300);
console.log('edit modal symbol:', await page.inputValue('#f-symbol'), '| thumbs:', await page.locator('.thumb').count());
await page.fill('#f-symbol','수정된종목');
await page.click('#btn-save');
await page.waitForTimeout(500);
console.log('edited card symbol:', await page.textContent('.entry .sym'));

// CSV/JSON export (다운로드 트리거만 확인)
page.on('download', d => console.log('download:', d.suggestedFilename()));
await page.click('#btn-menu'); await page.click('#m-csv'); await page.waitForTimeout(500);

// 재로드 후 영속성
await page.reload();
await page.waitForTimeout(700);
console.log('after reload entries:', await page.locator('.entry').count(), '| shots:', await page.locator('.shots img').count());

// 모바일 뷰
await page.setViewportSize({width:390,height:844});
await page.waitForTimeout(300);
await page.screenshot({path:TMP+'/shot-mobile.png'});

report('local-basic', errors);
await browser.close();
