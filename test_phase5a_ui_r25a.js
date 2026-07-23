'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost/dashboard?static=1', runScripts:'outside-only', pretendToBeVisual:true });
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function() {};
window.scrollTo = function() {};
window.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
window.HTMLDialogElement.prototype.close = function() { this.open = false; };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const layer = (timeframe) => ({ timeframe, trend:'range', range_low:62000, range_high:66000, at:'2026-07-22T10:00:00+00:00', zones:[] });
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf)=>[tf,layer(tf)]));
const overview = {
  ok:true,version:'8.2.2',engine_version:'8.2.2',schema_version:86,ux_release:'8.2.9',asset:'BTC',
  principal:{workspace_id:'owner',display_name:'Wouter',role:'owner',mode:'owner'},profile:{workspace_id:'owner',display_name:'Wouter',mode:'owner'},
  account:{equity:20000,equity_fresh:true,equity_age_seconds:20,positions:[]},
  latest:{price:64000,price_status:{ok:true,stale:false,price:64000,source:'bybit_public'},execution_gate:{status:'NO_TRADE',orderable:false,reason:'Geen geldige setup.'},state_id:'r25a',state_generated_at:'2026-07-22T10:00:00Z'},
  discipline:{release:'R25A-PROCESS-FIRST',score:82,score_band:'steady',rules:{count:8,followed:7,deviated:1,pct:87.5},grades:{count:8,score:79,trend:'improving',recent_score:86,previous_score:70,delta:16},routine:{observed_days:7,completed_days:5,pct:71.4},streak:{current:4,longest:6,today_complete:false,status:'available_today',earned_by_day_start:false,earned_by_no_trade:false},today:{day_start_completed:false,no_trade_declared:false,no_trade_allowed:true,trade_activity_present:false,open_position:false},sample:{eligible_trades:8,rules_assessed:8,grades_assessed:8,routine_days_observed:7},read_only_to_trading_engine:true},
  market_stack:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},chart_drafts:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},composite_map:{asset:'BTC',layers,parent_links:{}},market_map:{asset:'BTC',layers,parent_links:{}},
  stack_health:{complete:true,capture_complete:true,verified_complete:true,synced_count:4,confirmed_count:4,required_count:4,missing_timeframes:[],review_timeframes:[],fresh:true,layers:[]},
  journal:{summary:'8 records',stats:{records:8,trades:8,total_pnl:900},trades:[],curve:[],deepdives:[]},knowledge:[],knowledge_source:{},knowledge_ingestion:[],methodology_sources:{},activity:[],lifecycles:{records:{}},risk_profiles:{scalp:.5,day:1,swing:2},commercialization:{},services:{},state_id:'r25a',updated_at:'2026-07-22T10:00:00Z'
};

let posted = false;
window.fetch = async (url, options={}) => {
  if (String(url).includes('/api/v1/discipline/no-trade')) {
    posted = true;
    return { ok:true, status:200, json:async()=>({ok:true,discipline:{...overview.discipline,score:84,streak:{...overview.discipline.streak,current:5,today_complete:true,status:'earned_today',earned_by_no_trade:true},today:{...overview.discipline.today,no_trade_declared:true,no_trade_allowed:false}}}) };
  }
  throw new Error(`Unexpected network call: ${url}`);
};
window.eval(script);

(async()=>{
  await wait(250);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'test seam ontbreekt');
  api.setOverview(overview);
  await wait(40);

  const score = window.document.getElementById('disciplineScore');
  const streak = window.document.getElementById('disciplineStreak');
  const rules = window.document.getElementById('disciplineRules');
  const trend = window.document.getElementById('disciplineTrend');
  assert.equal(score.textContent.trim(), '82');
  assert.match(streak.textContent, /4 dagen/i);
  assert.match(rules.textContent, /88%/);
  assert.match(trend.textContent, /Verbeterend/i);
  assert.match(window.document.getElementById('disciplineSummary').textContent, /winst of verlies telt niet mee/i);

  const pnl = window.document.getElementById('accountPnlDisclosure');
  assert(pnl && !pnl.open, 'P&L moet standaard ingeklapt zijn');
  assert(window.document.getElementById('accountOpenPnl'), 'bestaande P&L-id moet behouden zijn');

  const button = window.document.getElementById('noTradeDayButton');
  assert.equal(button.disabled, false);
  button.click();
  await wait(60);
  assert(posted, 'no-trade endpoint moet worden aangeroepen');
  assert.match(window.document.getElementById('disciplineTodayTitle').textContent, /Vandaag is verdiend/i);
  assert.match(window.document.getElementById('disciplineStreak').textContent, /5 dagen/i);
  assert(button.classList.contains('hidden'), 'actieknop verdwijnt nadat de dag verdiend is');

  api.setLanguage?.('en');
  api.setOverview({...overview,discipline:{...overview.discipline,streak:{...overview.discipline.streak,status:'earn_back',current:0}}});
  await wait(30);
  assert.match(window.document.getElementById('disciplineTitle').textContent, /Your discipline today/i);
  assert.match(window.document.getElementById('disciplineStreakMeta').textContent, /Earn-back/i);
  assert.match(window.document.getElementById('accountPnlDisclosure').textContent, /P&L deliberately secondary/i);

  const css = fs.readFileSync(path.join(root, 'dashboard.css'), 'utf8');
  assert.match(css, /\.discipline-card/);
  assert.match(css, /\.pnl-disclosure/);
  assert.match(css, /@media\(max-width:680px\)/);
  console.log('test_phase5a_ui_r25a.js: proces-eerst, streak, no-trade en P&L-collapse werken met echte payload');
  window.close();
})().catch((error)=>{console.error(error);window.close();process.exitCode=1;});
