import { chromium } from 'playwright-core';
import { CHROME, CHART, TMP, APP_URL, report } from '../lib/env.mjs';

const b = await chromium.launch({executablePath: CHROME});
const errs = [];
const log = (...a)=>console.log(...a);

/* ── 모바일 상단바 높이 ── */
{
  const p = await (await b.newContext({viewport:{width:390,height:844}})).newPage();
  p.on('pageerror', e=>errs.push('mobile: '+e.message));
  await p.goto(APP_URL); await p.waitForTimeout(600);
  const m = await p.evaluate(()=>({
    barH: Math.round(document.querySelector('.topbar').getBoundingClientRect().height),
    sideScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    tabsFit: document.querySelector('#tabs').scrollWidth <= document.querySelector('#tabs').clientWidth + 2,
  }));
  log('모바일 390px → 상단바', m.barH+'px', '| 가로스크롤', m.sideScroll, '| 탭 한 화면', m.tabsFit);
  if(m.barH > 130) errs.push('모바일 상단바가 아직 높음: '+m.barH+'px');
  if(m.sideScroll) errs.push('모바일에서 가로 스크롤 발생');
  await p.screenshot({path: TMP+'/mobile-topbar.png'});
  await p.close();
}

/* ── 자동완성 · 백업 알림 · 기간 필터 ── */
const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
p.on('pageerror', e=>errs.push(e.message));
p.on('console', m=>{ if(m.type()==='error' && !/40[134]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog', d=>d.accept());
await p.goto(APP_URL); await p.waitForTimeout(600);

await p.click('#btn-menu'); await p.click('#m-sample'); await p.waitForTimeout(1000);

// 자동완성: 기존 종목이 datalist 에, 자주 쓴 태그가 칩으로
await p.click('#btn-new'); await p.waitForTimeout(400);
const syms = await p.locator('#symbol-list option').count();
const tagChips = await p.locator('#tag-picks button').count();
log('자동완성 → 종목 후보', syms+'개', '| 태그 칩', tagChips+'개');
if(syms < 3) errs.push('종목 자동완성 후보 부족: '+syms);
if(tagChips < 3) errs.push('태그 칩 부족: '+tagChips);
// 태그 칩 클릭 → 입력창 반영 → 다시 클릭 → 제거
const firstTag = (await p.locator('#tag-picks button').first().textContent()).replace('#','');
await p.locator('#tag-picks button').first().click(); await p.waitForTimeout(200);
const after = await p.inputValue('#f-tags');
await p.locator('#tag-picks button').first().click(); await p.waitForTimeout(200);
const removed = await p.inputValue('#f-tags');
log('태그 칩 토글 →', JSON.stringify(after), '→', JSON.stringify(removed));
if(!after.includes(firstTag)) errs.push('태그 칩이 입력창에 반영되지 않음');
if(removed.includes(firstTag)) errs.push('태그 칩 해제가 동작하지 않음');
await p.click('#btn-cancel'); await p.waitForTimeout(300);

// 백업 알림: 기록 10건 이상 + 백업 이력 없음
await p.evaluate(async ()=>{
  const db = await new Promise(r=>{const q=indexedDB.open('trading-journal');q.onsuccess=e=>r(e.target.result)});
  const st = db.transaction('entries','readwrite').objectStore('entries');
  const pad=n=>String(n).padStart(2,'0'); const base=new Date();
  for(let i=0;i<12;i++){
    const d=new Date(base); d.setDate(d.getDate()-i);
    st.put({id:'bk'+i, date:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()), time:'09:30',
      symbol:'종목'+i, side:'long', entry:100, exit:110, qty:1, fee:0, pnl:1000, pnlPct:1,
      tags:['백업테스트'], comment:'', lesson:'', isLesson:false, isMarket:false, rating:3, images:[],
      createdAt:new Date().toISOString(), updatedAt:new Date().toISOString()});
  }
  await new Promise(r=>{st.transaction.oncomplete=r});
});
await p.reload(); await p.waitForTimeout(1200);
const noticeShown = await p.locator('#backup-note').isVisible();
log('백업 알림 표시:', noticeShown, '|', (await p.textContent('#backup-note .msg')).replace(/\s+/g,' ').slice(0,52));
if(!noticeShown) errs.push('백업 알림이 표시되지 않음');
// 닫으면 7일 스누즈
await p.click('#notice-close'); await p.waitForTimeout(500);
await p.reload(); await p.waitForTimeout(1000);
log('닫은 뒤 재방문 표시:', await p.locator('#backup-note').isVisible());
if(await p.locator('#backup-note').isVisible()) errs.push('스누즈가 동작하지 않음');

// 기간 필터가 통계 탭에도 적용되는지
await p.click('#tabs button[data-view="stats"]'); await p.waitForTimeout(600);
log('통계 기본 제목:', await p.textContent('#period-label'));
await p.click('[data-period="3m"]'); await p.waitForTimeout(600);
log('3개월 선택 후:', await p.textContent('#period-label'), '| 칩 개수', await p.locator('.periods button').count());
if(!(await p.textContent('#period-label')).includes('3개월')) errs.push('통계 탭 기간 필터 미반영');
// 약점 탭과 선택이 공유되는지
await p.click('#tabs button[data-view="weak"]'); await p.waitForTimeout(600);
if(!(await p.textContent('#period-sub')).includes('3개월')) errs.push('약점 탭과 기간 선택이 공유되지 않음');
log('약점 탭 기간 공유:', await p.textContent('#period-sub'));

report('daily-use', errs);
await b.close();
