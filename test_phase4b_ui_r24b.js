'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost/dashboard?demo=1&static=1', runScripts:'outside-only', pretendToBeVisual:true });
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function() {};
window.scrollTo = function() {};
window.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
window.HTMLDialogElement.prototype.close = function() { this.open = false; };
window.fetch = async () => { throw new Error('R24b UI-test gebruikt geen netwerk'); };
window.eval(script);
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const layer = (timeframe) => ({ timeframe, trend:'range', range_low:62000, range_high:66000, at:'2026-07-21T08:00:00+00:00', zones:[] });
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf)=>[tf,layer(tf)]));
const overview = {
  ok:true, version:'8.2.2', engine_version:'8.2.2', schema_version:86, ux_release:'8.2.9', asset:'BTC',
  principal:{id:'owner',workspace_id:'owner',display_name:'Wouter',role:'owner',mode:'owner'},
  profile:{workspace_id:'owner',display_name:'Wouter',mode:'owner'},
  account:{equity:20000,equity_fresh:true,positions:[]},
  latest:{ok:true,asset:'BTC',symbol:'BTCUSDT',price:64000,execution_gate:{status:'NO_TRADE',orderable:false,reason:'Geen geldige setup.'},blocking_review_timeframes:[],state_id:'r24b',state_generated_at:'2026-07-21T08:00:00+00:00'},
  market_stack:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}}, chart_drafts:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},
  composite_map:{asset:'BTC',layers,parent_links:{}}, market_map:{asset:'BTC',layers,parent_links:{}},
  stack_health:{complete:true,capture_complete:true,verified_complete:true,synced_count:4,confirmed_count:4,required_count:4,missing_timeframes:[],review_timeframes:[],fresh:true,layers:[]},
  journal:{summary:'1 record',stats:{records:1,trades:1,wins:1,losses:0,total_pnl:21.84,source_counts:{BYBIT_VERIFIED:1}},trades:[],curve:[],deepdives:[{
    _id:'close-r24b-001',symbol:'BTCUSDT',direction:'long',pnl:21.84,time:'2026-07-21T08:00:00+00:00',proces_grade:'B',
    oordeel:'De richting klopte, maar de bevestiging was nog niet af.',wat_ging_goed:'Goede 4H-locatie.',wat_kan_beter:'Wacht op de 3M-hertest.',les:'Een richting is nog geen entry.',
    coach_loop_lesson:{id:'rule-confirmation',title:'Wacht op bevestiging',summary:'Laat de 3M-close en hertest de lokale kanteling bevestigen.',role:'observation_lens_only'}
  }]},
  knowledge:[],knowledge_source:{status:'ACTIEF'},knowledge_ingestion:[],methodology_sources:{rules:[]},activity:[],lifecycles:[],risk_profiles:{scalp:.5,day:1,swing:2},commercialization:{},services:{post_trade_coach_loop:{enabled:true,outgoing_only:true,pending:0,sent:1}},state_id:'r24b',updated_at:'2026-07-21T08:00:00+00:00'
};

(async()=>{
  await wait(300);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'test seam ontbreekt');
  api.setOverview(overview);
  await wait(50);
  api.switchView('learn');
  await wait(20);
  const card = window.document.querySelector('.coach-loop-lens');
  assert(card, 'kennislens ontbreekt in cockpit-deepdive');
  assert.match(card.textContent, /KENNISLENS/i);
  assert.match(card.textContent, /Wacht op bevestiging/i);
  assert.match(card.textContent, /3M-close en hertest/i);
  assert.match(card.textContent, /nooit een handelssignaal/i);
  assert.doesNotMatch(card.textContent, /https?:\/\//i);

  window.localStorage.setItem('mytradingbot_language_v1','en');
  api.setLanguage?.('en');
  api.setOverview(overview);
  await wait(30);
  assert.match(window.document.querySelector('.coach-loop-lens').textContent, /KNOWLEDGE LENS/i);
  assert.match(window.document.querySelector('.coach-loop-lens').textContent, /never a trading signal/i);
  console.log('test_phase4b_ui_r24b.js: echte deepdive toont gekoppelde kennislens in NL en EN');
  window.close();
})().catch((error)=>{console.error(error);window.close();process.exitCode=1;});
