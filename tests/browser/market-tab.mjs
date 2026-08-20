import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const MODE = process.argv[2] || 'local';
const errs=[];
const ctx = await b.newContext({viewport:{width:1280,height:1000}});
const p = await ctx.newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[0134]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());

let url = FILE_URL;
if(MODE==='server') url=SERVER_URL;
if(MODE==='cloud'){
  url=APP_URL;
  await p.addInitScript(u=>localStorage.setItem("tj-supabase", JSON.stringify({url:u, key:"anon-test-key"})), MOCK_URL);
}
await p.goto(url); await p.waitForTimeout(700);
if(MODE!=='local'){
  await p.fill('#a-user', MODE==='cloud'?'mk@example.com':'mktrader'); await p.fill('#a-pass','journal1234');
  await p.click(await p.locator('#a-register').isVisible() ? '#a-register' : 'button[type=submit]');
  await p.waitForTimeout(1500);
}

async function addObs(symbol, from, to, note, withImage){
  await p.click('#add-obs'); await p.waitForTimeout(400);
  await p.fill('#f-symbol', symbol);
  await p.click(`#f-from button[data-v="${from}"]`);
  await p.click(`#f-to button[data-v="${to}"]`);
  await p.fill('#f-comment', note);
  if(withImage){ await p.setInputFiles('#file',CHART); await p.waitForTimeout(700); }
  await p.click('#btn-save'); await p.waitForTimeout(MODE==='local'?800:1500);
}

// 장중 탭
await p.click('#tabs button[data-view="market"]'); await p.waitForTimeout(600);
console.log('[%s] 빈 상태:', MODE, ((await p.textContent('.empty'))||'').slice(0,18));
// 관찰 모드에서 가격 입력 숨김 확인
await p.click('#add-obs'); await p.waitForTimeout(400);
console.log('[%s] 관찰 모달 — 제목:', MODE, await p.textContent('#modal-title'),
            '| 진입가 숨김:', !(await p.locator('#f-entry').isVisible()),
            '| 배열칸 보임:', await p.locator('#market-row').isVisible());
await p.click('#btn-cancel'); await p.waitForTimeout(300);

await addObs('삼성전자','역배열','정배열','장 초반 거래량 실려 20/60일선 정배열 전환', true);
await addObs('에코프로','정배열','정배열','정배열 유지, 눌림 후 재상승');
await addObs('카카오','평행','정배열','평행 구간에서 위로 뚫음');
await addObs('NVDA','정배열','역배열','갭 하락 후 배열 붕괴');

await p.waitForTimeout(500);
console.log('[%s] 기록 수:', MODE, await p.locator('.obs').count(),
            '| 개선:', (await p.locator('#stats-cards .stat').nth(2).textContent()).replace(/\s+/g,' ').trim(),
            '| 악화:', (await p.locator('#stats-cards .stat').nth(3).textContent()).replace(/\s+/g,' ').trim());
console.log('[%s] 전환 칩:', MODE, (await p.locator('.obs').first().textContent()).replace(/\s+/g,' ').slice(0,40));
console.log('[%s] 이미지:', MODE, await p.locator('.obs .shots img').count());

// 매트릭스 필터
const cells = await p.locator('.mx .cell-m').allTextContents();
console.log('[%s] 매트릭스 셀 9개:', MODE, cells.length===9, '| 역배열→정배열 칸:', cells[2].replace(/\s+/g,' ').trim());
await p.click('.mx .cell-m[data-mx="역배열>정배열"]'); await p.waitForTimeout(600);
console.log('[%s] 필터 적용 후:', MODE, await p.locator('.obs').count(), '건');
await p.click('#mx-clear'); await p.waitForTimeout(500);
console.log('[%s] 필터 해제 후:', MODE, await p.locator('.obs').count(), '건');

// 매매 통계에 섞이지 않는지
await p.click('#tabs button[data-view="stats"]'); await p.waitForTimeout(600);
console.log('[%s] 통계 총 거래:', MODE, (await p.locator('#stats-cards .stat').nth(1).textContent()).replace(/\s+/g,' ').trim());
await p.click('#tabs button[data-view="day"]'); await p.waitForTimeout(600);
console.log('[%s] 일별 거래 수:', MODE, (await p.locator('#stats-cards .stat').nth(0).textContent()).replace(/\s+/g,' ').trim());

// 수정 / 검색 / 새로고침
await p.click('#tabs button[data-view="market"]'); await p.waitForTimeout(600);
await p.locator('.obs .edit-obs').first().click(); await p.waitForTimeout(600);
await p.click('#f-to button[data-v="평행"]');
await p.click('#btn-save'); await p.waitForTimeout(1500);
console.log('[%s] 수정 후 첫 기록:', MODE, (await p.locator('.obs').first().textContent()).replace(/\s+/g,' ').slice(0,32));
await p.fill('#q','에코프로'); await p.waitForTimeout(600);
console.log('[%s] 검색 결과:', MODE, await p.locator('.obs').count());
await p.fill('#q',''); await p.waitForTimeout(400);
await p.reload(); await p.waitForTimeout(1800);
await p.click('#tabs button[data-view="market"]'); await p.waitForTimeout(800);
console.log('[%s] 새로고침 후:', MODE, await p.locator('.obs').count(), '건 | 이미지:', await p.locator('.obs .shots img').count());
if(MODE==='local') await p.screenshot({path:TMP+'/market.png'});
report(`market-tab (${MODE})`, errs);
await b.close();
