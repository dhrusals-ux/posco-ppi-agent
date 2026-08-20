import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const BASE=SERVER_URL;
const errs=[];
const b = await chromium.launch({executablePath: CHROME});

// ---------- 기기 A: 가입 → 일지 작성(이미지 포함) ----------
const A = await b.newContext({viewport:{width:1280,height:900}});
const p = await A.newPage();
p.on('pageerror',e=>errs.push('A: '+e.message));
p.on('console',m=>{ if(m.type()==='error') errs.push('A console: '+m.text()); });
p.on('dialog',d=>d.accept());
await p.goto(BASE); await p.waitForTimeout(600);
console.log('login screen:', await p.locator('#auth.on').count(), '| register button:', await p.locator('#a-register').isVisible());
await p.fill('#a-user','trader'); await p.fill('#a-pass','journal1234');
await p.click('#a-register'); await p.waitForTimeout(1200);
console.log('after register — auth hidden:', !(await p.locator('#auth.on').count()));
console.log('account label:', (await p.textContent('#acct')).replace(/\s+/g,' ').trim().slice(0,40));

await p.click('#btn-new');
await p.fill('#f-symbol','삼성전자');
await p.fill('#f-entry','71500'); await p.fill('#f-exit','73200'); await p.fill('#f-qty','100');
await p.fill('#f-tags','돌파매매, 서버테스트');
await p.fill('#f-comment','서버 저장 확인용 일지');
await p.setInputFiles('#file',CHART);
await p.waitForTimeout(800);
await p.click('#btn-save'); await p.waitForTimeout(1500);
console.log('A entries:', await p.locator('.entry').count(), '| shots:', await p.locator('.shots img').count());
const shotSrc = await p.getAttribute('.shots img','src');
console.log('image src:', shotSrc);
const imgOk = await p.evaluate(async src=>{ const r=await fetch(src,{credentials:'same-origin'});
  return r.status+' '+r.headers.get('content-type')+' '+(await r.blob()).size; }, shotSrc);
console.log('thumb fetch:', imgOk);

// 새로고침 후에도 유지
await p.reload(); await p.waitForTimeout(1200);
console.log('A after reload entries:', await p.locator('.entry').count());

// ---------- 기기 B: 다른 브라우저 컨텍스트에서 로그인 ----------
const B = await b.newContext({viewport:{width:1280,height:900}});
const p2 = await B.newPage();
p2.on('pageerror',e=>errs.push('B: '+e.message));
p2.on('dialog',d=>d.accept());
await p2.goto(BASE); await p2.waitForTimeout(700);
console.log('B sees login screen:', !!(await p2.locator('#auth.on').count()));
await p2.fill('#a-user','trader'); await p2.fill('#a-pass','journal1234');
await p2.click('button[type=submit]'); await p2.waitForTimeout(1500);
console.log('B entries (다른 기기 동기화):', await p2.locator('.entry').count(),
            '| shots:', await p2.locator('.shots img').count(),
            '| symbol:', await p2.textContent('.entry .sym'));
await p2.screenshot({path:'/tmp/server-deviceB.png'});

// 잘못된 비밀번호
const C = await b.newContext(); const p3 = await C.newPage();
await p3.goto(BASE); await p3.waitForTimeout(600);
await p3.fill('#a-user','trader'); await p3.fill('#a-pass','wrongpass');
await p3.click('button[type=submit]'); await p3.waitForTimeout(800);
console.log('wrong password msg:', await p3.textContent('#auth-err'));
// 두번째 가입 시도(닫혀 있어야 함)
console.log('가입 개방 상태(테스트 서버는 TJ_ALLOW_REGISTER=1):', await p3.locator('#a-register').isVisible());

// ---------- 백업 / 수정 / 삭제 ----------
p.on('download', d=>console.log('download:', d.suggestedFilename()));
await p.click('#btn-menu'); await p.click('#m-export'); await p.waitForTimeout(1500);
await p.locator('.entry .edit').first().click(); await p.waitForTimeout(500);
console.log('edit modal thumbs:', await p.locator('.thumb').count());
await p.fill('#f-symbol','삼성전자(수정)'); await p.click('#btn-save'); await p.waitForTimeout(1200);
console.log('edited:', await p.textContent('.entry .sym'));
await p2.reload(); await p2.waitForTimeout(1200);
console.log('B sees edit:', await p2.textContent('.entry .sym'));
await p.locator('.entry .del').first().click(); await p.waitForTimeout(1200);
console.log('A after delete:', await p.locator('.entry').count());
// 로그아웃
await p.click('#btn-menu'); await p.click('#m-logout'); await p.waitForTimeout(900);
console.log('after logout, auth shown:', !!(await p.locator('#auth.on').count()));
report('server-mode', errs);
await b.close();
