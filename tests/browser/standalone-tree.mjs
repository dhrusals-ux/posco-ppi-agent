import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const b = await chromium.launch({executablePath: CHROME});
const errs=[];
async function run(name, url, register){
  const p = await (await b.newContext({viewport:{width:1280,height:950}})).newPage();
  p.on('pageerror',e=>errs.push(name+': '+e.message));
  p.on('console',m=>{ if(m.type()==='error' && !/40[13]/.test(m.text())) errs.push(name+' console: '+m.text()); });
  p.on('dialog',d=>d.accept());
  await p.goto(url); await p.waitForTimeout(800);
  if(register){
    await p.fill('#a-user','solo'); await p.fill('#a-pass','journal1234');
    await p.click(await p.locator('#a-register').isVisible() ? '#a-register' : 'button[type=submit]');
    await p.waitForTimeout(1500);
  }
  // 일지 + 시사점 + 이미지
  await p.click('#btn-new');
  await p.fill('#f-symbol','삼성전자');
  await p.fill('#f-entry','71500'); await p.fill('#f-exit','73200'); await p.fill('#f-qty','100');
  await p.fill('#f-lesson','거래량 없는 돌파는 따라가지 않는다');
  await p.setInputFiles('#file',CHART_BIG);
  await p.waitForTimeout(1000);
  await p.click('#btn-save'); await p.waitForTimeout(1800);
  const shot = await p.locator('.shots img').first().boundingBox();
  // 장중 관찰
  await p.click('#tabs button[data-view="market"]'); await p.waitForTimeout(500);
  await p.click('#add-obs'); await p.waitForTimeout(400);
  await p.fill('#f-symbol','코스피');
  await p.click('#f-from button[data-v="역배열"]'); await p.click('#f-to button[data-v="정배열"]');
  await p.fill('#f-comment','장 초반 정배열 전환');
  await p.click('#btn-save'); await p.waitForTimeout(1800);
  const obs = await p.locator('.obs').count();
  // 시사점 탭
  await p.click('#tabs button[data-view="lessons"]'); await p.waitForTimeout(600);
  const les = await p.locator('.les').count();
  // 새로고침 유지
  await p.reload(); await p.waitForTimeout(1800);
  await p.click('#tabs button[data-view="day"]'); await p.waitForTimeout(600);
  console.log(`[${name}] 일지 ${await p.locator('.entry').count()}건 · 차트 ${Math.round(shot.width)}x${Math.round(shot.height)} · 장중 ${obs}건 · 시사점 ${les}개`);
  if(name==='static') await p.screenshot({path:TMP+'/standalone.png'});
  return p;
}
await run('static', STANDALONE_URL, false);
await run('server', STANDALONE_SERVER_URL, true);
report('standalone-tree', errs);
await b.close();
