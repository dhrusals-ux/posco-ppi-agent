import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[134]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());
await p.goto(APP_URL); await p.waitForTimeout(800);

// 2,000건 + 장중 관찰 300건 주입
await p.evaluate(async ()=>{
  const db = await new Promise(r=>{const q=indexedDB.open('trading-journal');q.onsuccess=e=>r(e.target.result)});
  const st = db.transaction('entries','readwrite').objectStore('entries');
  const pad=n=>String(n).padStart(2,'0'); const base=new Date();
  for(let i=0;i<2000;i++){
    const d=new Date(base); d.setDate(d.getDate()-(i%400));
    st.put({id:'p'+i, date:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()), time:'09:'+pad(i%60),
      symbol:'종목'+(i%50), side:i%2?'long':'short', entry:1000+i, exit:1003+i, qty:10, fee:100,
      pnl:(i%7-3)*1000, pnlPct:(i%7-3)*0.5, tags:['태그'+(i%8)], comment:'c'+i,
      lesson:i%5===0?'시사점 '+i:'', isLesson:false, isMarket:false, rating:i%5, images:[],
      createdAt:new Date(Date.now()-i*1000).toISOString(), updatedAt:new Date().toISOString()});
  }
  for(let i=0;i<300;i++){
    const d=new Date(base); d.setDate(d.getDate()-(i%60));
    st.put({id:'m'+i, date:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()), time:'09:0'+(i%10),
      symbol:'관찰'+(i%20), side:'long', entry:null, exit:null, qty:null, fee:null, pnl:null, pnlPct:null,
      tags:[], comment:'관찰 '+i, lesson:'', isLesson:false, isMarket:true,
      alignFrom:['역배열','평행','정배열'][i%3], alignTo:['정배열','역배열','평행'][i%3],
      rating:0, images:[], createdAt:new Date(Date.now()-i*1000).toISOString(), updatedAt:new Date().toISOString()});
  }
  await new Promise(r=>{st.transaction.oncomplete=r});
});
await p.reload(); await p.waitForTimeout(1500);

const times={};
for(const v of ['day','week','month','market','lessons','stats']){
  const t0=Date.now();
  await p.click(`#tabs button[data-view="${v}"]`);
  await p.waitForSelector('#stats-cards .stat',{timeout:15000});
  times[v]=Date.now()-t0;
}
console.log('2,300건 렌더(ms):', times);
await p.click('#tabs button[data-view="lessons"]'); await p.waitForTimeout(400);
console.log('시사점 첫 화면 카드:', await p.locator('.les').count(), '| 더 보기:', await p.locator('[data-more]').count());
const t1=Date.now(); await p.click('[data-more="lessons"]'); await p.waitForTimeout(300);
console.log('더 보기 후 카드:', await p.locator('.les').count(), `(${Date.now()-t1}ms)`);
await p.click('#tabs button[data-view="market"]'); await p.waitForTimeout(400);
console.log('장중 첫 화면:', await p.locator('.obs').count(), '| 매트릭스 합계 표시:', (await p.textContent('#stats-cards .stat .v')).trim());

// 검색 반응
const t2=Date.now(); await p.fill('#q','종목7'); await p.waitForTimeout(400);
console.log('검색 후 표시:', await p.locator('.obs, .entry, .les').count(), `(${Date.now()-t2}ms)`);
await p.fill('#q','');

// Tab 키 포커스 표시 확인
await p.click('#tabs button[data-view="day"]'); await p.waitForTimeout(300);
await p.keyboard.press('Tab'); await p.keyboard.press('Tab');
const f = await p.evaluate(()=>{ const el=document.activeElement; const cs=getComputedStyle(el);
  return {tag:el.tagName, label:el.getAttribute('aria-label')||el.textContent.trim().slice(0,10), outline:cs.outlineWidth, color:cs.outlineColor}; });
console.log('Tab 포커스:', f);
report('performance', errs);
await b.close();
