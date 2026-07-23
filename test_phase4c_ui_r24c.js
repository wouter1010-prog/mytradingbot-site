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
window.fetch = async () => { throw new Error('R24c UI-test gebruikt geen netwerk'); };
window.eval(script);
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const layer = (timeframe) => ({ timeframe, trend:'range', range_low:62000, range_high:66000, at:'2026-07-26T16:00:00+00:00', zones:[] });
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf)=>[tf,layer(tf)]));
const weekly = {
  enabled:true, running:true, configured:true, outgoing_only:true, weekday:6, time:'18:00', timezone:'Europe/Amsterdam',
  last_sent_week:'2026-W30',
  latest_report:{reports:{
    nl:{title:'Wekelijks mentor-rapport',period_start:'2026-07-19',period_end:'2026-07-26',trade_count:3,
      strengths:['Je legde 3 gesloten trades vast.','2 van 3 trades kregen procesgrade A of B.','Bij 2 trades zijn de regels gevolgd.'],
      pattern:'Midrange-trades keren terug in twee procesnotities.',
      lesson:{title:'Herhaalbaar gedrag',summary:'Kies één procesgedrag en beoordeel na afloop alleen of je dat gedrag hebt uitgevoerd.',role:'observation_lens_only'},
      safety:'Alleen reflectie. Dit rapport is nooit een setup, instap, stop, doel of order.'},
    en:{title:'Weekly mentor report',period_start:'2026-07-19',period_end:'2026-07-26',trade_count:3,
      strengths:['You logged 3 closed trades.','2 of 3 trades received an A or B process grade.','The rules were followed on 2 trades.'],
      pattern:'Mid-range trades return in two process notes.',
      lesson:{title:'Repeatable behaviour',summary:'Choose one process behaviour and review only whether you performed it.',role:'observation_lens_only'},
      safety:'Reflection only. This report is never a setup, entry, stop, target or order.'}
  }}
};
const overview = {
  ok:true, version:'8.2.2', engine_version:'8.2.2', schema_version:86, ux_release:'8.2.9', asset:'BTC',
  principal:{id:'owner',workspace_id:'owner',display_name:'Wouter',role:'owner',mode:'owner'},
  profile:{workspace_id:'owner',display_name:'Wouter',mode:'owner'},
  account:{equity:20000,equity_fresh:true,positions:[]},
  latest:{ok:true,asset:'BTC',symbol:'BTCUSDT',price:64000,execution_gate:{status:'NO_TRADE',orderable:false,reason:'Geen geldige setup.'},blocking_review_timeframes:[],state_id:'r24c',state_generated_at:'2026-07-26T16:00:00+00:00'},
  market_stack:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},chart_drafts:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},
  composite_map:{asset:'BTC',layers,parent_links:{}},market_map:{asset:'BTC',layers,parent_links:{}},
  stack_health:{complete:true,capture_complete:true,verified_complete:true,synced_count:4,confirmed_count:4,required_count:4,missing_timeframes:[],review_timeframes:[],fresh:true,layers:[]},
  journal:{summary:'3 records',stats:{records:3,trades:3,wins:2,losses:1,total_pnl:18,source_counts:{BYBIT_VERIFIED:3}},trades:[],curve:[],deepdives:[]},
  knowledge:[],knowledge_source:{status:'ACTIEF'},knowledge_ingestion:[],methodology_sources:{rules:[]},activity:[],lifecycles:[],risk_profiles:{scalp:.5,day:1,swing:2},commercialization:{},
  services:{weekly_mentor:weekly,post_trade_coach_loop:{enabled:true,outgoing_only:true,pending:0,sent:1}},state_id:'r24c',updated_at:'2026-07-26T16:00:00+00:00'
};

(async()=>{
  await wait(300);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'test seam ontbreekt');
  api.setOverview(overview);
  await wait(50);
  api.switchView('learn');
  await wait(20);
  const panel = window.document.getElementById('weeklyMentorPanel');
  const content = window.document.getElementById('weeklyMentorContent');
  assert(panel && !panel.hidden, 'weekrapport moet zichtbaar zijn voor owner');
  assert.match(content.textContent, /3 sterke punten/i);
  assert.match(content.textContent, /midrange-trades/i);
  assert.match(content.textContent, /Herhaalbaar gedrag/i);
  assert.match(content.textContent, /nooit een setup/i);
  assert.doesNotMatch(content.textContent, /https?:\/\//i);

  window.localStorage.setItem('mytradingbot_language_v1','en');
  api.setLanguage?.('en');
  api.setOverview(overview);
  await wait(30);
  assert.match(content.textContent, /3 strengths/i);
  assert.match(content.textContent, /Mid-range trades/i);
  assert.match(content.textContent, /Repeatable behaviour/i);
  assert.match(content.textContent, /Reflection only/i);
  console.log('test_phase4c_ui_r24c.js: echt weekrapport rendert bronvrij in NL en EN');
  window.close();
})().catch((error)=>{console.error(error);window.close();process.exitCode=1;});
