'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const token = 'r22-real-payload-token-with-at-least-32-chars';
const requests = [];

const layer = (timeframe) => ({
  timeframe, trend:'range', range_low:62000, range_high:66000, overall_confidence:82,
  at:'2026-07-20T08:00:00+00:00', zones:[], warnings:[]
});
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf) => [tf, layer(tf)]));
const overview = {
  ok:true, asset:'BTC', updated_at:'2026-07-20T08:05:00+00:00',
  principal:{role:'tester',display_name:'R22 Tester',workspace_id:'r22-tester'}, profile:{mode:'tester',manual_equity:10000},
  account:{equity:null,equity_fresh:false,positions:[]},
  latest:{price:64123.4,price_status:{ok:true,stale:false,price:64123.4,source:'bybit_public_mark',age_seconds:6},blocking_review_timeframes:[],execution_gate:{status:'NO_TRADE',orderable:false,reason:'Er is nu geen geldige setup.'},setup:{}},
  market_stack:{assets:{BTC:{layers}}}, chart_drafts:{assets:{BTC:{layers}}}, composite_map:{layers,parent_links:{}}, market_map:{layers,parent_links:{}},
  stack_health:{synced_count:4,confirmed_count:4,capture_complete:true,fresh:true,layers:Object.keys(layers).map((timeframe)=>({timeframe,present:true,synced:true,confirmed:true,fresh:true,zones:0}))},
  journal:{stats:{records:0,trades:0,wins:0,losses:0,total_pnl:0,source_counts:{}},trades:[],deepdives:[]},
  knowledge:[{
    id:'lesson-stop-hunt', type:'risk', category:'risk', title:'Waarom een wick je stop kan raken',
    summary:'Een wick kan kort door een druk stopgebied prikken zonder dat de candle daar sluit.',
    source_label:'PRIVÉ KENNIS', source_title:'Interne bron die niet in de coachvraag mag komen',
    source_url:'https://example.invalid/private-source', confidence:94, official_status:'gecontroleerd', date:'2026-07-20'
  }],
  knowledge_source:{status:'ACTIEF',processor_active:true,stored_videos:45,stored_lessons:118,processed:45,queue:58,queue_total:103},
  methodology_sources:{rules:[]}, knowledge_ingestion:[], activity:[], services:{account_watcher:{running:true}}
};

const response = (body, status = 200) => ({ ok:status >= 200 && status < 300, status, json:async()=>body, blob:async()=>new Blob() });
const dom = new JSDOM(html, {
  url:`http://localhost/dashboard?static=1#access=${token}`,
  runScripts:'outside-only', pretendToBeVisual:true
});
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
window.scrollTo = function scrollTo() {};
window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; this.setAttribute('open',''); };
window.HTMLDialogElement.prototype.close = function close() { this.open = false; this.removeAttribute('open'); };
window.fetch = async (url, options = {}) => {
  const pathname = String(url);
  if (pathname.includes('/api/v1/config')) return response({ok:true,version:'8.2.2'});
  if (pathname.includes('/api/v1/overview')) return response(overview);
  if (pathname.includes('/api/v1/coach')) {
    const body = JSON.parse(options.body || '{}');
    requests.push(body);
    const expert = /expert(?:modus| mode)/i.test(body.question || '');
    return response({ok:true,answer:expert
      ? 'Een wick is een tijdelijke prijsuitstap buiten de candle-body. Technisch telt de bevestiging pas op candle-close. Voorbeeld: prijs prikt onder steun, maar sluit erboven.'
      : 'Een wick is een korte prik van de prijs. Denk aan iemand die even één voet buiten de deur zet en meteen terugstapt. Pas wanneer de candle buiten sluit, is de deur echt achter hem dicht.'});
  }
  throw new Error(`Onverwachte request in R22B-test: ${pathname}`);
};
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const click = (node) => { node.dispatchEvent(new window.MouseEvent('click',{bubbles:true})); };

(async () => {
  await wait(300);
  const { document } = window;
  assert(document.getElementById('loginLayer').classList.contains('hidden'), 'token-auth met echt overview-schema moet slagen');
  click(document.querySelector('[data-view="learn"]'));
  await wait(30);

  const explain = document.querySelector('.explain-lesson-button');
  assert(explain, 'iedere kennisles moet een Leg uit-knop krijgen');
  assert.equal(explain.textContent.trim(), 'Leg uit');
  assert.equal(document.getElementById('coachExpertMode').checked, false, 'heldere modus moet standaard actief zijn');
  assert.equal(document.getElementById('coachModeBadge').textContent, 'HELDER');

  click(explain);
  await wait(60);
  assert.equal(requests.length, 1, 'Leg uit moet exact één bestaande coach-call doen');
  assert.match(requests[0].question, /16-jarige/i);
  assert.match(requests[0].question, /analogie/i);
  assert.match(requests[0].question, /fictief voorbeeld/i);
  assert(!requests[0].question.includes('Interne bron'), 'brontitel mag niet in de coachprompt komen');
  assert(!requests[0].question.includes('example.invalid'), 'bron-URL mag niet in de coachprompt komen');
  assert.match(document.getElementById('coachMessages').textContent, /één voet buiten de deur/i, 'echt antwoordformaat moet in de coachchat renderen');
  assert(!document.getElementById('coachMessages').textContent.includes('16-jarige'), 'de verborgen stuurprompt mag niet als gebruikersbericht worden getoond');
  assert.equal(document.getElementById('coachPanel').open, true, 'Leg uit moet het bestaande coachpaneel openen');

  const toggle = document.getElementById('coachExpertMode');
  toggle.checked = true;
  toggle.dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(document.getElementById('coachModeBadge').textContent, 'EXPERT');
  click(document.querySelector('.explain-lesson-button'));
  await wait(60);
  assert.equal(requests.length, 2);
  assert.match(requests[1].question, /^Expertmodus\./);
  assert.match(requests[1].question, /kort en technisch/i);
  assert.match(document.getElementById('coachMessages').textContent, /bevestiging pas op candle-close/i);

  toggle.checked = false;
  toggle.dispatchEvent(new window.Event('change',{bubbles:true}));
  click(document.querySelector('[data-language="en"]'));
  await wait(40);
  assert.equal(document.querySelector('.explain-lesson-button').textContent.trim(), 'Explain');
  assert.equal(document.getElementById('coachModeBadge').textContent, 'CLEAR');
  click(document.querySelector('.explain-lesson-button'));
  await wait(60);
  assert.equal(requests.length, 3);
  assert.match(requests[2].question, /16-year-old/i);
  assert.match(requests[2].question, /one simple analogy/i);
  assert.match(requests[2].question, /do not create a current setup, entry, stop or target/i);

  assert.equal(document.getElementById('footerVersion').textContent, 'UX v8.4.0');
  console.log('PASS R22B: real overview + real coach response shape, Explain button, clear/expert modes and NL/EN use the existing /api/v1/coach endpoint');
  window.close();
})().catch((error) => {
  console.error(error);
  window.close();
  process.exitCode = 1;
});
