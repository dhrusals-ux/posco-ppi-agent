import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const MODE = process.argv[2] || 'local';
const errs=[];
const ctx = await b.newContext({viewport:{width:1280,height:950}});
const p = await ctx.newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[13]|404/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());

let url = FILE_URL;
if(MODE==='server') url = SERVER_URL;
if(MODE==='cloud'){
  url = APP_URL;
  await p.addInitScript(u=>localStorage.setItem("tj-supabase", JSON.stringify({url:u, key:"anon-test-key"})), MOCK_URL);
}
await p.goto(url); await p.waitForTimeout(700);
if(MODE!=='local'){
  const email = MODE==='cloud' ? 'les@example.com' : 'lestrader';
  await p.fill('#a-user', email); await p.fill('#a-pass','journal1234');
  await p.click(await p.locator('#a-register').isVisible() ? '#a-register' : 'button[type=submit]');
  await p.waitForTimeout(1500);
}

// 1) 매매 일지에 시사점 작성
await p.click('#btn-new');
await p.fill('#f-symbol','삼성전자');
await p.fill('#f-entry','71500'); await p.fill('#f-exit','73200'); await p.fill('#f-qty','100');
await p.fill('#f-comment','전고점 돌파 진입');
await p.fill('#f-lesson','거래량 없는 돌파는 따라가지 않는다.\n다음엔 20일선 눌림까지 기다린다.');
await p.fill('#f-tags','돌파매매');
await p.click('#btn-save'); await p.waitForTimeout(1500);
console.log('[%s] 카드에 시사점 표시:', MODE, (await p.locator('.entry .lesson').count())>0,
            '|', ((await p.textContent('.entry .lesson'))||'').slice(0,22).replace(/\s+/g,' '));

// 2) 시사점 탭
await p.click('#tabs button[data-view="lessons"]'); await p.waitForTimeout(700);
console.log('[%s] 아카이브 항목:', MODE, await p.locator('.les').count(),
            '| 누적 카운트:', await p.textContent('#stats-cards .stat .v'));

// 3) 단독 시사점 추가
await p.click('#add-lesson'); await p.waitForTimeout(400);
await p.fill('#les-title-in','손절 원칙');
await p.fill('#les-text','손절선은 진입 전에 정하고, 정한 뒤에는 절대 옮기지 않는다.');
await p.fill('#les-tags','원칙, 리스크관리');
await p.click('#les-save'); await p.waitForTimeout(1500);
console.log('[%s] 메모 추가 후 항목:', MODE, await p.locator('.les').count(),
            '| 메모 표식:', await p.locator('.les.memo').count());

// 4) 매매 통계에 메모가 섞이지 않는지
await p.click('#tabs button[data-view="stats"]'); await p.waitForTimeout(600);
const totalTrades = await p.locator('#stats-cards .stat').nth(1).textContent();
console.log('[%s] 통계 총 거래:', MODE, totalTrades.replace(/\s+/g,' ').trim());
await p.click('#tabs button[data-view="month"]'); await p.waitForTimeout(600);
console.log('[%s] 월간 거래 수:', MODE, (await p.locator('#stats-cards .stat').nth(1).textContent()).replace(/\s+/g,' ').trim());

// 5) 검색이 시사점에도 걸리는지
await p.click('#tabs button[data-view="lessons"]'); await p.waitForTimeout(500);
await p.fill('#q','손절선'); await p.waitForTimeout(600);
console.log('[%s] "손절선" 검색 결과:', MODE, await p.locator('.les').count());
await p.fill('#q',''); await p.waitForTimeout(500);

// 6) 시사점 수정 / 원본 이동
await p.locator('.les .edit-les').first().click(); await p.waitForTimeout(600);
const memoOpen = await p.locator('#lesson-modal[open]').count();
if(memoOpen){ await p.fill('#les-text','수정된 시사점'); await p.click('#les-save'); }
else { await p.fill('#f-lesson','수정된 시사점'); await p.click('#btn-save'); }
await p.waitForTimeout(1500);
const texts = (await p.locator('.les .txt').allTextContents()).map(t=>t.slice(0,14));
console.log('[%s] 수정 반영:', MODE, texts.some(t=>t.includes('수정된 시사점')), '|', texts);

// 7) 마크다운 내보내기
p.on('download', d=>console.log('[%s] download:', MODE, d.suggestedFilename()));
await p.click('#export-lessons'); await p.waitForTimeout(1500);

// 8) 새로고침 후 유지
await p.reload(); await p.waitForTimeout(1800);
await p.click('#tabs button[data-view="lessons"]'); await p.waitForTimeout(800);
console.log('[%s] 새로고침 후 항목:', MODE, await p.locator('.les').count());
if(MODE==='local') await p.screenshot({path:TMP+'/lessons.png', fullPage:false});
report(`lessons-tab (${MODE})`, errs);
await b.close();
