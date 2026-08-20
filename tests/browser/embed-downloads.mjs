import { chromium } from 'playwright-core';
import { CHROME, CHART, CHART_BIG, TMP, FILE_URL, WRAP_URL, APP_URL, SERVER_URL, MOCK_URL,
         STANDALONE_URL, STANDALONE_SERVER_URL, report } from '../lib/env.mjs';
const errs=[];
const b = await chromium.launch({executablePath: CHROME});
const ctx = await b.newContext({viewport:{width:1100,height:800}});
const p = await ctx.newPage();
p.on('pageerror',e=>errs.push(e.message));
p.on('dialog',d=>d.accept());
// claude.ai 아티팩트 호스트 흉내: window.claude.use("downloads")
await p.addInitScript(()=>{
  window.__saves=[];
  window.claude = { use: async (n)=> n==="downloads" ? {
      save: async ({filename,data})=>{
        const size = typeof data==='string' ? data.length : (data.size||data.byteLength);
        if(/\.csv$/.test(filename)){ const e=new Error('extended type off'); e.code='extension_not_enabled'; throw e; }
        window.__saves.push({filename,size}); return {status:'saved'};
      }} : null };
});
await p.goto(WRAP_URL+'wrapped.html');
await p.waitForTimeout(400);
await p.click('#btn-menu'); await p.click('#m-sample'); await p.waitForTimeout(600);
await p.click('#btn-menu'); await p.click('#m-export'); await p.waitForTimeout(1200);
await p.click('#btn-menu'); await p.click('#m-csv'); await p.waitForTimeout(1000);
console.log('saves:', await p.evaluate(()=>window.__saves));
console.log('last toast:', await p.textContent('#toast'));
await p.click('#btn-menu'); await p.waitForTimeout(200);
console.log('embed note hidden (downloads available):', !(await p.locator('#embed-note').isVisible()));
report('embed-downloads', errs);
await b.close();
