import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error') errs.push('console: '+m.text()); });
p.on('dialog',d=>d.accept());
await p.goto(FILE_URL); await p.waitForTimeout(500);

await p.click('#btn-new');
await p.fill('#f-symbol','삼성전자');
await p.fill('#f-entry','71500'); await p.fill('#f-exit','73200'); await p.fill('#f-qty','100');
await p.fill('#f-comment','전고점 돌파');
await p.setInputFiles('#file', [CHART_BIG]);
await p.waitForTimeout(1200);
console.log('작성창 미리보기 썸네일 크기:', await p.locator('.thumb img').first().boundingBox().then(b=>b&&Math.round(b.width)+'x'+Math.round(b.height)));
await p.click('#btn-save'); await p.waitForTimeout(1500);

const box = await p.locator('.shots img').first().boundingBox();
console.log('카드 이미지 크기(크게):', Math.round(box.width)+'x'+Math.round(box.height));
console.log('실제 로드된 원본 해상도:', await p.locator('.shots img').first().evaluate(el=>el.naturalWidth+'x'+el.naturalHeight));
await p.screenshot({path:TMP+'/img-big.png'});

// 두 장일 때 2열 배치
await p.locator('.entry .edit').first().click(); await p.waitForTimeout(500);
await p.setInputFiles('#file', [CHART]);
await p.waitForTimeout(900);
await p.click('#btn-save'); await p.waitForTimeout(1500);
const boxes = await p.locator('.shots img').all();
const sizes = [];
for(const el of boxes){ const bb = await el.boundingBox(); sizes.push(Math.round(bb.width)+'x'+Math.round(bb.height)); }
console.log('이미지 2장 배치:', sizes.join(' , '));

// 작게 보기 토글
await p.click('#btn-menu'); await p.click('#m-imgsize'); await p.waitForTimeout(900);
const small = await p.locator('.shots img').first().boundingBox();
console.log('토글 후(작게):', Math.round(small.width)+'x'+Math.round(small.height),
            '| 메뉴 라벨:', await p.textContent('#m-imgsize'));
await p.screenshot({path:TMP+'/img-small.png'});
// 새로고침해도 유지
await p.reload(); await p.waitForTimeout(1200);
console.log('새로고침 후 작게 유지:', await p.evaluate(()=>document.body.classList.contains('img-sm')));
await p.click('#btn-menu'); await p.click('#m-imgsize'); await p.waitForTimeout(900);
console.log('다시 크게:', await p.locator('.shots img').first().boundingBox().then(b=>Math.round(b.width)+'x'+Math.round(b.height)));

// 라이트박스
await p.click('.shots img'); await p.waitForTimeout(800);
const lb = await p.locator('#lb-img').boundingBox();
console.log('라이트박스:', Math.round(lb.width)+'x'+Math.round(lb.height));
report('image-size', errs);
await b.close();
