import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs = [];
const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
p.on('pageerror', e=>errs.push(e.message));
p.on('console', m=>{ if(m.type()==='error') errs.push('console: '+m.text()); });
p.on('dialog', d=>d.accept());
const fail = m => errs.push('✗ '+m);
const cards = () => p.locator('.bcard').count();

await p.goto(FILE_URL); await p.waitForTimeout(500);

// ── 1) 차트북이 기본 화면인가
const firstTab = await p.textContent('#tabs button:first-child');
const onTab = await p.getAttribute('#tabs button.on','data-view');
console.log('첫 탭:', firstTab.trim(), '| 기본 화면:', onTab);
if(onTab !== 'book') fail('기본 화면이 차트북이 아닙니다: '+onTab);
const emptyTxt = (await p.textContent('.empty')||'').slice(0,12);
console.log('빈 상태:', emptyTxt);
if(!emptyTxt.includes('차트북')) fail('차트북 빈 상태 문구가 보이지 않습니다');

// ── 2) 샘플이 차트까지 채우는가
await p.click('#empty-sample'); await p.waitForTimeout(2500);
const n0 = await cards();
console.log('샘플 후 차트 카드:', n0);
if(n0 < 6) fail('샘플 차트가 모자랍니다: '+n0);
const loaded = await p.evaluate(()=>{
  const im = document.querySelector('.bcard img');
  return im ? [im.naturalWidth, im.getAttribute('src').slice(0,11)] : null;
});
console.log('카드 이미지:', loaded && loaded[0]+'px', loaded && loaded[1]);
if(!loaded || loaded[0] < 50) fail('카드 이미지가 그려지지 않았습니다');

// ── 3) 요약은 제목 옆 한 줄로 (차트가 먼저 보이도록 통계 카드는 접는다)
const sub = (await p.textContent('#period-sub')||'').trim();
console.log('요약:', sub);
if(!/차트 \d+장/.test(sub) || !/종목/.test(sub)) fail('차트북 요약이 비었습니다: '+sub);
if(await p.locator('#stats-cards .stat').count()) fail('차트북에서 통계 카드가 접히지 않았습니다');
const firstCardTop = (await p.locator('.bcard').first().boundingBox()).y;
console.log('첫 차트 위치:', Math.round(firstCardTop)+'px');
if(firstCardTop > 330) fail('차트가 너무 아래에서 시작합니다: '+Math.round(firstCardTop)+'px');

// ── 4) 패턴 태그 필터 (AND)
const chip = p.locator('#book-tags button', {hasText:'#돌파'}).first();
await chip.click(); await p.waitForTimeout(400);
const nTag = await cards();
console.log('#돌파 필터:', nTag, '장 (전체 '+n0+')');
if(nTag === 0 || nTag >= n0) fail('태그 필터가 좁히지 못했습니다: '+nTag);
const allTagged = await p.evaluate(()=>
  [...document.querySelectorAll('.bcard')].every(c=>c.textContent.includes('#돌파')));
if(!allTagged) fail('필터 결과에 태그 없는 카드가 섞였습니다');
await chip.click(); await p.waitForTimeout(400);
if(await cards() !== n0) fail('태그 해제 후 원래대로 돌아오지 않았습니다');

// ── 5) 별점 · 종류 필터
await p.click('#book-stars button[data-v="4"]'); await p.waitForTimeout(400);
const nStar = await cards();
console.log('★4+ 필터:', nStar);
if(nStar === 0 || nStar > n0) fail('별점 필터 결과가 이상합니다: '+nStar);
await p.click('#book-stars button[data-v="0"]'); await p.waitForTimeout(300);

await p.click('#book-kind button[data-v="market"]'); await p.waitForTimeout(400);
const nMarket = await cards();
console.log('장중 관찰만:', nMarket);
if(nMarket !== 1) fail('장중 관찰 필터 결과가 1장이 아닙니다: '+nMarket);
const align = await p.textContent('.bcard .bc-meta');
console.log('장중 카드 메타:', align.replace(/\s+/g,' ').trim());
if(!align.includes('→')) fail('배열 전환이 카드에 보이지 않습니다');
await p.click('#book-kind button[data-v="all"]'); await p.waitForTimeout(300);

// ── 6) 정렬 · 크기
await p.click('#book-sort button[data-v="rating"]'); await p.waitForTimeout(400);
const firstSym = await p.textContent('.bcard .sym');
console.log('별점순 첫 카드:', firstSym);
await p.click('#book-size button[data-v="sm"]'); await p.waitForTimeout(400);
const smBox = await p.locator('.bcard').first().boundingBox();
await p.click('#book-size button[data-v="lg"]'); await p.waitForTimeout(600);
const lgBox = await p.locator('.bcard').first().boundingBox();
console.log('카드 폭 촘촘/크게:', Math.round(smBox.width)+'px /', Math.round(lgBox.width)+'px');
if(!(lgBox.width > smBox.width)) fail('카드 크기 전환이 동작하지 않습니다');
await p.click('#book-size button[data-v="md"]'); await p.waitForTimeout(400);
await p.click('#book-sort button[data-v="recent"]'); await p.waitForTimeout(400);

// ── 7) 카드 클릭 → 라이트박스 + 캡션, ← → 이동
await p.click('.bcard img'); await p.waitForTimeout(900);
const capTitle = await p.textContent('#lb-cap .t b');
const capBody  = (await p.textContent('#lb-cap')||'').replace(/\s+/g,' ').trim();
const count1   = await p.textContent('#lb-count');
console.log('라이트박스 캡션:', capTitle, '|', count1, '|', capBody.slice(0,46));
if(!capTitle) fail('라이트박스에 종목 캡션이 없습니다');
if(!/\d+ \/ \d+/.test(count1)) fail('라이트박스 장수 표시가 없습니다');
await p.keyboard.press('ArrowRight'); await p.waitForTimeout(700);
const capTitle2 = await p.textContent('#lb-cap .t b');
console.log('→ 다음 차트:', capTitle2, await p.textContent('#lb-count'));
if(capTitle2 === capTitle && n0 > 1) fail('← → 로 다음 차트로 넘어가지 않습니다');
await p.click('#lb-cap-t'); await p.waitForTimeout(250);
console.log('메모 숨김:', await p.evaluate(()=>document.body.classList.contains('lb-nocap')));
await p.click('#lb-cap-t'); await p.waitForTimeout(200);
await p.keyboard.press('Escape'); await p.waitForTimeout(400);

// ── 8) 비교 모드 — 2장 골라 나란히 보기
await p.click('#book-cmp'); await p.waitForTimeout(400);
await p.locator('.bcard img').nth(0).click(); await p.waitForTimeout(350);
await p.locator('.bcard img').nth(2).click(); await p.waitForTimeout(400);
const picked = await p.locator('.bcard.picked').count();
console.log('선택된 카드:', picked, '| 번호:', await p.locator('.bcard.picked .bc-no').allTextContents());
if(picked !== 2) fail('비교 선택이 2장이 아닙니다: '+picked);
await p.click('#cmp-open'); await p.waitForTimeout(1800);
const cmpOn = await p.locator('#compare.on').count();
const cmpImgs = await p.evaluate(()=>[...document.querySelectorAll('#cmp-grid img')]
  .map(i=>i.naturalWidth));
console.log('비교 보기 열림:', !!cmpOn, '| 이미지 폭:', cmpImgs.join(','));
if(!cmpOn) fail('비교 보기가 열리지 않았습니다');
if(cmpImgs.length !== 2 || cmpImgs.some(w=>w < 50)) fail('비교 이미지가 로드되지 않았습니다: '+cmpImgs);
await p.screenshot({path:TMP+'/chartbook-compare.png'});
await p.keyboard.press('Escape'); await p.waitForTimeout(400);
if(await p.locator('#compare.on').count()) fail('Esc 로 비교 보기가 닫히지 않습니다');
await p.click('#cmp-off'); await p.waitForTimeout(400);

// ── 9) 검색 + 필터 해제
await p.fill('#q','에코프로'); await p.waitForTimeout(600);
const nQuery = await cards();
console.log('검색 "에코프로":', nQuery+'장');
if(nQuery === 0 || nQuery >= n0) fail('검색이 차트북에 적용되지 않았습니다: '+nQuery);
await p.click('#book-reset'); await p.waitForTimeout(600);
console.log('필터 해제 후:', await cards()+'장 | 검색창:', JSON.stringify(await p.inputValue('#q')));
if(await cards() !== n0) fail('필터 해제가 전체를 되돌리지 않았습니다');

// ── 10) 카드에서 바로 수정 → 차트북에 반영
await p.locator('.bcard').first().hover();
await p.locator('.bcard .bc-edit').first().click(); await p.waitForTimeout(700);
await p.fill('#f-symbol','삼성전자(수정)');
await p.click('#btn-save'); await p.waitForTimeout(1500);
const edited = await p.textContent('.bcard .sym');
console.log('카드에서 수정:', edited);
if(!edited.includes('수정')) fail('카드 수정이 반영되지 않았습니다');

// ── 11) 새로고침 후 유지 + 단축키 1
await p.reload(); await p.waitForTimeout(1200);
console.log('새로고침 후 화면:', await p.getAttribute('#tabs button.on','data-view'), '| 카드:', await cards());
await p.click('#tabs button[data-view="day"]'); await p.waitForTimeout(400);
await p.keyboard.press('1'); await p.waitForTimeout(500);
console.log('단축키 1 →', await p.getAttribute('#tabs button.on','data-view'));
if(await p.getAttribute('#tabs button.on','data-view') !== 'book') fail('단축키 1이 차트북을 열지 않습니다');
await p.screenshot({path:TMP+'/chartbook.png', fullPage:false});

// ── 12) 모바일: 필터가 화면을 먹지 않고 차트가 바로 보이는가
const m = await (await b.newContext({viewport:{width:390,height:844}, deviceScaleFactor:2})).newPage();
m.on('pageerror', e=>errs.push('mobile: '+e.message));
m.on('dialog', d=>d.accept());
await m.goto(FILE_URL); await m.waitForTimeout(500);
await m.click('#empty-sample'); await m.waitForTimeout(2500);
const mCard = await m.locator('.bcard').first().boundingBox();
const [sw, iw] = await m.evaluate(()=>[document.documentElement.scrollWidth, window.innerWidth]);
const mCols = await m.evaluate(()=>getComputedStyle(document.querySelector('.book-grid')).gridTemplateColumns.split(' ').length);
const editOpacity = await m.evaluate(()=>getComputedStyle(document.querySelector('.bc-edit')).opacity);
console.log('모바일 — 첫 카드 y:', Math.round(mCard.y)+'px | 한 줄', mCols+'장 | 가로 스크롤 없음:', sw<=iw,
            '| 수정 버튼 보임:', editOpacity);
if(mCard.y > 380) fail('모바일에서 차트가 너무 아래에 있습니다: '+Math.round(mCard.y)+'px');
if(sw > iw) fail('모바일 가로 스크롤이 생겼습니다: '+sw+'/'+iw);
if(mCols < 2) fail('모바일에서 한 줄에 2장이 아닙니다: '+mCols);
if(+editOpacity < 0.5) fail('터치 기기에서 카드 수정 버튼이 보이지 않습니다: '+editOpacity);
await m.screenshot({path:TMP+'/chartbook-mobile.png'});

await b.close();
report('chartbook', errs);
