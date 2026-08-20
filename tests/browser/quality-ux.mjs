import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[134]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());
await p.goto(APP_URL); await p.waitForTimeout900 ?? await p.waitForTimeout(900);

// ── 빈 상태 버튼
console.log('빈 상태 버튼:', await p.locator('#empty-new').isVisible(), await p.locator('#empty-sample').isVisible());
await p.click('#empty-sample'); await p.waitForTimeout(1200);
console.log('샘플 후 일지:', await p.locator('.entry').count());

// ── 이미지 있는 일지 만들고 라이트박스 확대 테스트
await p.click('#btn-new');
await p.fill('#f-symbol','삼성전자'); await p.fill('#f-entry','71500'); await p.fill('#f-exit','73200'); await p.fill('#f-qty','100');
await p.setInputFiles('#file',CHART_BIG); await p.waitForTimeout(1000);
await p.click('#btn-save'); await p.waitForTimeout(1500);
await p.click('.shots img'); await p.waitForTimeout(700);
console.log('라이트박스 열림:', await p.locator('#lightbox.on').count(), '| 카운터:', await p.textContent('#lb-count'), '| 배율:', await p.textContent('#lb-zoom'));
await p.click('#lb-in'); await p.waitForTimeout(300);
console.log('확대 버튼 후:', await p.textContent('#lb-zoom'));
await p.mouse.move(640, 500); await p.mouse.wheel(0, -400); await p.waitForTimeout(300);
const zoomed = await p.textContent('#lb-zoom');
const t = await p.locator('#lb-img').evaluate(el=>getComputedStyle(el).transform);
console.log('휠 확대 후:', zoomed, '| transform 적용:', t.startsWith('matrix'));
// 드래그로 이동
const before = await p.locator('#lb-img').evaluate(el=>el.style.transform);
await p.mouse.move(640,500); await p.mouse.down(); await p.mouse.move(520,420,{steps:6}); await p.mouse.up();
await p.waitForTimeout(200);
const after = await p.locator('#lb-img').evaluate(el=>el.style.transform);
console.log('드래그 이동:', before!==after);
await p.keyboard.press('0'); await p.waitForTimeout(300);
console.log('0키 맞춤:', await p.textContent('#lb-zoom'));
await p.keyboard.press('Escape'); await p.waitForTimeout(300);
console.log('Esc 닫힘:', (await p.locator('#lightbox.on').count())===0);

// ── 삭제 되돌리기
const n0 = await p.locator('.entry').count();
await p.locator('.entry .del').first().click(); await p.waitForTimeout(600);
const n1 = await p.locator('.entry').count();
console.log('삭제 직후:', n0, '->', n1, '| 되돌리기 버튼:', await p.locator('#toast button').isVisible());
await p.click('#toast button'); await p.waitForTimeout(800);
console.log('되돌린 뒤:', await p.locator('.entry').count(), '(원상복구 =', (await p.locator('.entry').count())===n0, ')');
// 실제 삭제(되돌리지 않음)도 확인
await p.locator('.entry .del').first().click(); await p.waitForTimeout(7500);
await p.reload(); await p.waitForTimeout(1200);
console.log('되돌리지 않으면 삭제 확정:', await p.locator('.entry').count(), '건');

// ── 접근성: 포커스 표시 / aria
const outline = await p.locator('#btn-new').evaluate(el=>{ el.focus(); return getComputedStyle(el).outlineWidth; });
console.log('키보드 포커스 outline:', outline, '| aria-label 개수:', await p.locator('[aria-label]').count());

// ── PWA
const mf = await p.evaluate(async ()=>{ const r = await fetch('manifest.json'); const j = await r.json(); return j.name+' / icons '+j.icons.length; });
console.log('manifest:', mf);
console.log('sw.js 응답:', await p.evaluate(async ()=>(await fetch('sw.js')).status));

// ── 성능: 2,000건 렌더링
const perf = await p.evaluate(async ()=>{
  const db = await new Promise(r=>{const q=indexedDB.open('trading-journal');q.onsuccess=e=>r(e.target.result)});
  const tx = db.transaction('entries','readwrite').objectStore('entries');
  const base = new Date();
  for(let i=0;i<2000;i++){
    const d = new Date(base); d.setDate(d.getDate() - (i%400));
    const pad = n=>String(n).padStart(2,'0');
    tx.put({id:'perf'+i, date:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()),
      time:'09:'+pad(i%60), symbol:'종목'+(i%50), side:i%2?'long':'short',
      entry:1000+i, exit:1000+i+(i%7-3), qty:10, fee:100, pnl:(i%7-3)*1000, pnlPct:(i%7-3)*0.5,
      tags:['태그'+(i%8)], comment:'자동 생성 '+i, lesson:i%5===0?'시사점 '+i:'', isLesson:false, isMarket:false,
      rating:i%5, images:[], createdAt:new Date().toISOString(), updatedAt:new Date().toISOString()});
  }
  await new Promise(r=>{tx.transaction.oncomplete=r});
  return true;
});
await p.reload(); await p.waitForTimeout(1500);
const times = {};
for(const v of ['day','week','month','market','lessons','stats']){
  const t0 = Date.now();
  await p.click(`#tabs button[data-view="${v}"]`);
  await p.waitForSelector('#stats-cards .stat', {timeout:15000});
  await p.waitForTimeout(150);
  times[v] = Date.now()-t0-150;
}
console.log('2,000건 렌더 시간(ms):', times);
await p.click('#tabs button[data-view="stats"]'); await p.waitForTimeout(500);
console.log('통계 총 거래:', (await p.locator('#stats-cards .stat').nth(1).textContent()).replace(/\s+/g,' ').trim());
report('quality-ux', errs);
await b.close();
