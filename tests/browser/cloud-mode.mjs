import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const APP = APP_URL, SB = MOCK_URL;
const errs=[];
const b = await chromium.launch({executablePath: CHROME});

async function newDevice(name){
  const ctx = await b.newContext({viewport:{width:1280,height:900}});
  const p = await ctx.newPage();
  p.on('pageerror',e=>errs.push(name+': '+e.message));
  p.on('console',m=>{ if(m.type()==='error' && !/401|403/.test(m.text())) errs.push(name+' console: '+m.text()); });
  p.on('dialog',d=>d.accept());
  await p.addInitScript(([url])=>{ localStorage.setItem("tj-supabase", JSON.stringify({url, key:"anon-test-key"})); }, [SB]);
  return p;
}

// ── 기기 A: 가입 → 일지 작성(이미지) ──
const p = await newDevice('A');
await p.goto(APP); await p.waitForTimeout(700);
console.log('cloud login screen:', !!(await p.locator('#auth.on').count()),
            '| label:', await p.textContent('#a-user-label'),
            '| register visible:', await p.locator('#a-register').isVisible());
await p.fill('#a-user','me@example.com'); await p.fill('#a-pass','journal1234');
await p.click('#a-register'); await p.waitForTimeout(1200);
console.log('after signup — app shown:', !(await p.locator('#auth.on').count()),
            '| acct:', (await p.textContent('#acct')).replace(/\s+/g,' ').slice(0,28));

await p.click('#btn-new');
await p.fill('#f-symbol','에코프로');
await p.fill('#f-entry','98000'); await p.fill('#f-exit','101500'); await p.fill('#f-qty','30');
await p.fill('#f-tags','눌림목, 클라우드테스트');
await p.fill('#f-comment','Supabase 저장 확인');
await p.setInputFiles('#file',CHART);
await p.waitForTimeout(900);
await p.click('#btn-save'); await p.waitForTimeout(1800);
console.log('A entries:', await p.locator('.entry').count(),
            '| shot src starts blob:', (await p.getAttribute('.shots img','src')||'').slice(0,5));
await p.click('.shots img'); await p.waitForTimeout(700);
console.log('lightbox img loaded:', (await p.getAttribute('#lb-img','src')||'').slice(0,5));
await p.keyboard.press('Escape');

// 새로고침 후 세션 유지
await p.reload(); await p.waitForTimeout(1500);
console.log('A after reload:', await p.locator('.entry').count(), 'entries,',
            await p.locator('.shots img').count(), 'shots');

// ── 기기 B: 다른 브라우저에서 로그인 ──
const p2 = await newDevice('B');
await p2.goto(APP); await p2.waitForTimeout(700);
await p2.fill('#a-user','me@example.com'); await p2.fill('#a-pass','journal1234');
await p2.click('button[type=submit]'); await p2.waitForTimeout(1800);
console.log('B synced:', await p2.locator('.entry').count(), 'entries |',
            await p2.textContent('.entry .sym'), '| shots:', await p2.locator('.shots img').count());
await p2.screenshot({path:TMP+'/cloud-deviceB.png'});

// 잘못된 비밀번호
const p3 = await newDevice('C');
await p3.goto(APP); await p3.waitForTimeout(600);
await p3.fill('#a-user','me@example.com'); await p3.fill('#a-pass','nope');
await p3.click('button[type=submit]'); await p3.waitForTimeout(700);
console.log('bad password:', await p3.textContent('#auth-err'));

// ── 수정 / 삭제 / 백업 / 토큰만료 복구 ──
await p.locator('.entry .edit').first().click(); await p.waitForTimeout(700);
console.log('edit thumbs:', await p.locator('.thumb').count());
await p.fill('#f-symbol','에코프로(수정)'); await p.click('#btn-save'); await p.waitForTimeout(1500);
console.log('edited:', await p.textContent('.entry .sym'));

// 액세스 토큰을 망가뜨려 refresh 흐름 확인
await p.evaluate(()=>{ const s=JSON.parse(localStorage.getItem('tj-sb-session')); s.access_token='bad'; localStorage.setItem('tj-sb-session',JSON.stringify(s)); });
await p.reload(); await p.waitForTimeout(1800);
console.log('after expired token, entries:', await p.locator('.entry').count(), '| auth shown:', !!(await p.locator('#auth.on').count()));

p.on('download', d=>console.log('download:', d.suggestedFilename()));
await p.click('#btn-menu'); await p.click('#m-export'); await p.waitForTimeout(2500);

await p.locator('.entry .del').first().click(); await p.waitForTimeout(1500);
console.log('A after delete:', await p.locator('.entry').count());
await p2.reload(); await p2.waitForTimeout(1500);
console.log('B after delete:', await p2.locator('.entry').count());

// 로그아웃
await p.click('#btn-menu'); await p.click('#m-logout'); await p.waitForTimeout(900);
console.log('logout → auth screen:', !!(await p.locator('#auth.on').count()));
report('cloud-mode', errs);
await b.close();
