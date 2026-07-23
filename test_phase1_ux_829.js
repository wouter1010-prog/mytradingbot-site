'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, {
  url: 'http://localhost/dashboard?demo=1&static=1',
  runScripts: 'outside-only',
  pretendToBeVisual: true
});
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
window.scrollTo = function scrollTo() {};
window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; this.setAttribute('open', ''); };
window.HTMLDialogElement.prototype.close = function close() { this.open = false; this.removeAttribute('open'); };
window.fetch = async () => { throw new Error('Phase-1 real-payload test must not call the network'); };
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const rawReason = 'trigger detected as local_reversal based on sweep and reclaim of 64234.5 zone with momentum confirmation';
const rawWarning = 'Purple zones have ambiguous role and some price levels read from label overlays or right axis';
const layers = {
  '1D': { source_timeframe:'1D', trend:'range', range_low:62000, range_high:68000, overall_confidence:84, at:'2026-07-20T08:00:00Z', zones:[], warnings:[] },
  '4H': {
    source_timeframe:'4H', trend:'range', range_low:62500, range_high:66500, overall_confidence:81, at:'2026-07-20T08:00:00Z',
    zones:[
      { id:'z1', role:'unknown', color:'green', intent:'structure', bottom:64150, top:64300, reason:rawReason, confidence:79 },
      { id:'z2', role:'resistance', color:'red', intent:'structure', bottom:64250, top:64400, reason:'Manually drawn resistance zone from TradingView', confidence:91 }
    ], warnings:[rawWarning]
  },
  '15M': { source_timeframe:'15M', trend:'down', range_low:63800, range_high:65000, overall_confidence:80, at:'2026-07-20T08:00:00Z', zones:[], warnings:[] },
  '3M': { source_timeframe:'3M', trend:'up', range_low:64000, range_high:64600, overall_confidence:77, at:'2026-07-20T08:00:00Z', zones:[], warnings:[] }
};
const layerHealth = Object.keys(layers).map((timeframe) => ({ timeframe, present:true, synced:true, confirmed:true, fresh:true, zones:layers[timeframe].zones.length }));
const overview = {
  ok:true, asset:'BTC', updated_at:'2026-07-20T08:05:00Z', principal:{role:'owner',display_name:'Wouter',workspace_id:'owner'}, profile:{mode:'owner'},
  account:{equity:9876543.21,equity_fresh:true,positions:[]},
  latest:{ price:64325, price_status:{ok:true,stale:false,price:64325,source:'bybit_public_mark',age_seconds:5}, blocking_review_timeframes:[], execution_gate:{status:'NO_TRADE',orderable:false}, setup:{} },
  market_stack:{assets:{BTC:{layers}}}, chart_drafts:{assets:{BTC:{layers}}}, composite_map:{layers,parent_links:{}}, market_map:{layers,parent_links:{}},
  stack_health:{synced_count:4,confirmed_count:4,capture_complete:true,fresh:true,layers:layerHealth},
  journal:{stats:{records:1,trades:1,wins:1,losses:0,total_pnl:9876543.21,snapshot_count:1,snapshot_coverage_pct:100,verified_source_count:1,source_counts:{BYBIT_VERIFIED:1},per_richting:{long:9876543.21},per_symbool:{BTCUSDT:9876543.21}},trades:[{id:'t1',source_class:'BYBIT_VERIFIED',symbol:'BTCUSDT',direction:'long',entry:64000,exit:65000,pnl:9876543.21,pnl_pct:12.345,closed_at:'2026-07-20T08:00:00Z'}],deepdives:[]},
  knowledge:[], knowledge_source:{}, methodology_sources:{rules:[]}, knowledge_ingestion:[],
  activity:[{type:'chart_synced',timeframe:'4H',at:'2026-07-20T08:03:00Z',note:'Chart synced · 4H — 2 zones read · 81% zekerheid'}], services:{account_watcher:{running:true}},
};

(async () => {
  await wait(300);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'test seam ontbreekt');
  api.setOverview(overview);
  await wait(40);
  const { document } = window;

  // Select the real 4H payload, not demo strings.
  document.querySelector('#timeframeTabs [data-timeframe="4H"]').click();
  await wait(20);
  const cards = [...document.querySelectorAll('#layerZones .zone-card')];
  assert.equal(cards.length, 2, 'beide echte visionzones moeten renderen');
  assert.match(cards[0].querySelector('.vision-zone-grid').textContent, /Rol|Prijsniveau|Reden|Zekerheid/);
  assert.match(cards[0].querySelector('.vision-reason').textContent, /sweep.*heroverde|lokale kanteling/i, 'ruwe modelzin moet worden genormaliseerd');
  assert(!cards[0].querySelector('.vision-reason').textContent.includes('trigger detected'), 'ruwe Engelse modeltekst mag niet in de hoofdreden staan');
  const rawDetails = cards[0].querySelector('.vision-technical-details');
  assert(rawDetails && !rawDetails.open, 'ruwe modeltekst moet standaard dicht staan');
  assert.match(rawDetails.textContent, /trigger detected as local_reversal/i, 'ruwe tekst moet auditbaar blijven achter details');
  assert.match(cards[0].querySelector('.badge').textContent, /Steun/i, 'kleur moet naar vaste rol worden vertaald');

  const warning = document.querySelector('#draftWarnings .vision-warning');
  assert(warning, 'genormaliseerde visionwaarschuwing ontbreekt');
  assert.match(warning.querySelector(':scope > span').textContent, /paarse zone|prijsas/i);
  assert(!warning.querySelector(':scope > span').textContent.includes('Purple zones'), 'ruwe waarschuwing mag niet vooraan staan');
  assert.match(warning.querySelector('details').textContent, /Purple zones have ambiguous role/i);

  const readiness = document.getElementById('ticketReadiness').textContent;
  assert.match(readiness, /Zoneketen 4H → 15M → 3M/);
  assert.match(readiness, /overlappende 4H-zone|Ontbreekt:/i, 'poorttekst moet een concrete oorzaak noemen');
  assert(!/nog niet duidelijk/i.test(readiness), 'vage poorttekst mag niet terugkomen');

  assert.match(document.getElementById('auditStatusLine').textContent, /Laatste run OK.*0 fouten/i, 'auditstatus moet zonder uitklappen zichtbaar zijn');
  assert.equal(document.getElementById('auditMeta').classList.contains('good'), true);

  api.switchView('journal');
  await wait(20);
  const totalValue = document.querySelector('#performanceSummaryKpis .performance-kpi strong');
  assert(totalValue?.classList.contains('full-value'), 'grote KPI-waarden moeten de niet-afkappenstijl krijgen');
  assert.equal(totalValue.title, totalValue.textContent, 'volledige waarde moet ook als tooltip beschikbaar zijn');
  const resultCell = document.querySelector('#journalTableBody td.result-value');
  assert(resultCell?.title && resultCell.title !== 'US$ 9…', 'journaalcel moet de volledige waarde als tooltip bevatten');

  api.setLanguage('en');
  await wait(30);
  document.querySelector('#timeframeTabs [data-timeframe="4H"]').click();
  await wait(20);
  assert.match(document.querySelector('#layerZones .vision-zone-grid').textContent, /Role|Price level|Reason|Confidence/);
  assert(!document.querySelector('#layerZones .vision-reason').textContent.includes('trigger detected'));
  assert.match(document.getElementById('auditStatusLine').textContent, /Last run OK.*0 errors/i);

  assert.equal(document.getElementById('footerVersion').textContent, 'UX v8.4.0');
  console.log('test_phase1_ux_829.js: real-payload vision normalisation, concrete gates, audit status and full values passed');
  window.close();
})().catch((error) => {
  console.error(error);
  window.close();
  process.exitCode = 1;
});
