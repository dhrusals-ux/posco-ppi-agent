import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
const p = await (await b.newContext({viewport:{width:1280,height:900}})).newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('console',m=>{ if(m.type()==='error' && !/40[13]/.test(m.text())) errs.push('console: '+m.text()); });
p.on('dialog', async d=>{
  if(d.type()==='prompt') await d.accept('삭제');
  else await d.accept();
});
await p.goto(SERVER_URL); await p.waitForTimeout(700);
await p.fill('#a-user','quit'); await p.fill('#a-pass','journal1234');
await p.click('#a-register'); await p.waitForTimeout(1500);

// 일지 + 이미지 생성
await p.click('#btn-new');
await p.fill('#f-symbol','삼성전자'); await p.fill('#f-entry','100'); await p.fill('#f-exit','110'); await p.fill('#f-qty','10');
await p.setInputFiles('#file',CHART); await p.waitForTimeout(800);
await p.click('#btn-save'); await p.waitForTimeout(1500);
console.log('가입 후 일지:', await p.locator('.entry').count());

// 메뉴에 탈퇴 항목 노출
await p.click('#btn-menu'); await p.waitForTimeout(300);
console.log('탈퇴 메뉴 보임:', await p.locator('#m-close-account').isVisible());

// 탈퇴 실행
await p.click('#m-close-account'); await p.waitForTimeout(2000);
console.log('탈퇴 후 로그인 화면:', !!(await p.locator('#auth.on').count()));

// 같은 계정으로 재로그인 시도 → 실패해야 정상
await p.fill('#a-user','quit'); await p.fill('#a-pass','journal1234');
await p.click('button[type=submit]'); await p.waitForTimeout(1200);
console.log('재로그인 결과(거부되어야 정상):', (await p.textContent('#auth-err')).trim());
report('account-delete', errs);
await b.close();
