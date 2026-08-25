import { chromium } from 'playwright-core';
import { CHROME, TMP, APP_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
const p = await (await b.newContext({viewport:{width:1280,height:1000}})).newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[134]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());
await p.goto(APP_URL); await p.waitForTimeout(700);

// 의도적으로 약점이 있는 데이터 주입:
//  - 이익은 작게(+8만), 손실은 크게(-25만)  → 손익비 약점
//  - 손실 직후 같은 날 재진입은 더 나쁨      → 리벤지
//  - 금요일·장 마감 전 시간대가 최악         → 요일/시간대
//  - #뇌동매매 태그, '카카오' 종목이 마이너스 → 태그/종목
//  - 시사점에 '손절' 반복                     → 반복 다짐
await p.evaluate(async ()=>{
  const db = await new Promise(r=>{const q=indexedDB.open('trading-journal');q.onsuccess=e=>r(e.target.result)});
  const st = db.transaction('entries','readwrite').objectStore('entries');
  const pad=n=>String(n).padStart(2,'0');
  const base=new Date();
  const mk=(o)=>st.put(Object.assign({
    time:'10:20', side:'long', entry:1000, exit:1010, qty:10, fee:100, pnlPct:1,
    tags:[], comment:'기록', lesson:'', isLesson:false, isMarket:false, rating:3, images:[],
    createdAt:new Date().toISOString(), updatedAt:new Date().toISOString()}, o));
  const d=(off)=>{const x=new Date(base); x.setDate(x.getDate()-off);
    return x.getFullYear()+'-'+pad(x.getMonth()+1)+'-'+pad(x.getDate());};
  let i=0;
  // 승리 12건 (작은 이익)
  for(;i<12;i++) mk({id:'w'+i, date:d(i*2+1), pnl:80000, tags:['돌파매매'], rating:5,
    lesson:i%3===0?'손절선을 지키자':'', symbol:'삼성전자'});
  // 패배 10건 (큰 손실)
  for(let j=0;j<10;j++,i++) mk({id:'l'+j, date:d(j*2+2), pnl:-250000, tags:['뇌동매매'], rating:2,
    lesson:j%2===0?'손절을 미루지 말자':'', symbol:'카카오', time:'14:40'});
  // 손실 직후 같은 날 재진입 6건 (더 큰 손실)
  for(let j=0;j<6;j++,i++) mk({id:'r'+j, date:d(j*2+2), time:'14:55', pnl:-320000,
    tags:['추격매수'], symbol:'에코프로', comment:'직전 손실 만회 시도', lesson:'손절 후 쉬어가자'});
  // 큰 사고 1건
  mk({id:'big', date:d(9), pnl:-1500000, tags:['물타기'], symbol:'카카오',
      comment:'손절 못하고 버팀', lesson:'손절을 반드시 지키자', rating:1});
  await new Promise(r=>{st.transaction.oncomplete=r});
});
await p.reload(); await p.waitForTimeout(1200);

await p.click('#tabs button[data-view="weak"]'); await p.waitForTimeout(800);
console.log('요약:', (await p.locator('#stats-cards .stat').allTextContents()).map(t=>t.replace(/\s+/g,' ').trim()).join(' | '));
const titles = await p.locator('.wk-head h4').allTextContents();
const sevs = await p.locator('.wk-tag').allTextContents();
console.log('\n발견된 항목 ' + titles.length + '개:');
titles.forEach((t,i)=>console.log('  ['+(sevs[i]||'')+'] '+t.replace(/\s+/g,' ').trim()));
console.log('\n영향 추정 문구:', (await p.locator('.wk .why').allTextContents()).filter(t=>t.includes('달랐을')).length, '건');
console.log('처방(💡) 개수:', await p.locator('.wk .fix').count());
console.log('근거 기록 행:', await p.locator('.wk-row').count());

// 기간 필터
await p.click('[data-period="3m"]'); await p.waitForTimeout(700);
console.log('\n3개월 필터 후 부제:', await p.textContent('#period-sub'));
console.log('3개월 항목 수:', await p.locator('.wk').count());
await p.click('[data-period="all"]'); await p.waitForTimeout(600);

// 근거 행 클릭 → 해당 일자로 이동
await p.locator('.wk-row').first().click(); await p.waitForTimeout(700);
console.log('행 클릭 후 화면:', await p.textContent('#period-label'), '| 일지', await p.locator('.entry').count(), '건');

await p.click('#tabs button[data-view="weak"]'); await p.waitForTimeout(700);
const joined = titles.join(' | ');
// 심어둔 약점이 실제로 검출되는지 (제목 기준)
for(const must of ['크게 키', '뇌동매매', '손실 직후', '밀렸습니다', '카카오']){
  if(!joined.includes(must)) errs.push('기대한 약점 미검출: '+must);
}
// 요약 카드의 손익비가 1 미만으로 계산되는지
const payoff = (await p.locator('#stats-cards .stat').nth(3).textContent()).replace(/\s+/g,' ');
if(!/0\.\d/.test(payoff)) errs.push('손익비 계산 이상: '+payoff);
if(titles.length < 5) errs.push('약점 항목이 너무 적음: '+titles.length);
await p.screenshot({path: TMP+'/weak.png', fullPage:false});
report('weakness-tab', errs);
await b.close();
