'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'dashboard.css'), 'utf8');

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
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const layer = (timeframe) => ({
  timeframe,
  trend: timeframe === '1D' ? 'range' : 'down',
  range_low: 62000,
  range_high: 66000,
  overall_confidence: 82,
  at: '2026-07-23T07:45:00+00:00',
  zones: [{
    id: `${timeframe}-z1`, role: 'support', intent: 'structure', bottom: 62500, top: 62800,
    reason: 'Prijs reageerde op de getekende steunzone.', confidence: 84
  }],
  warnings: []
});
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf) => [tf, layer(tf)]));
const trades = [
  {
    id:'close-101', source_class:'BYBIT_VERIFIED', source_label:'BYBIT GEVERIFIEERD', symbol:'BTCUSDT',
    direction:'long', direction_consistency:'verified', entry:63500, exit:64100, pnl:120, pnl_pct:0.6,
    equity_snapshot:20000, closed_at:'2026-07-22T12:00:00+00:00', process_grade:'A'
  },
  {
    id:'close-102', source_class:'UNKNOWN', source_label:'ONBEKEND', symbol:'BTCUSDT',
    direction:'short', direction_consistency:'mismatch', entry:64200, exit:64400, pnl:-40, pnl_pct:-0.2,
    equity_snapshot:20080, closed_at:'2026-07-23T12:00:00+00:00', process_grade:'B',
    process_judgement:'Richting moet handmatig worden gecontroleerd.'
  }
];
const overview = {
  ok:true, version:'8.2.2', engine_version:'8.2.2', schema_version:86, asset:'BTC',
  principal:{id:'owner',workspace_id:'owner',display_name:'Wouter',role:'owner',mode:'owner',capabilities:[]},
  profile:{workspace_id:'owner',display_name:'Wouter',mode:'owner'},
  account:{equity:20160.25,equity_fresh:true,equity_age_seconds:12,positions:[]},
  discipline:{
    release:'R25A-PROCESS-FIRST', score:82, score_band:'strong',
    rules:{count:8,followed:7,deviated:1,pct:87.5}, grades:{count:8,score:84,trend:'improving',recent_score:88,previous_score:79},
    routine:{observed_days:6,completed_days:5,pct:83.3},
    streak:{current:4,longest:7,today_complete:false,status:'available_today',earned_by_day_start:false,earned_by_no_trade:false},
    today:{day_start_completed:false,no_trade_declared:false,no_trade_allowed:true,trade_activity_present:false,open_position:false}
  },
  account_guard:{active:false,daily_loss_limit_pct:2,buffer_remaining_usdt:403.21,buffer_remaining_pct:100,positions_open:0,max_positions:1,cooldown_active:false,cooldown_seconds_remaining:0,ticket_blocked:false,next_reset_at:'2026-07-24T00:00:00+02:00'},
  journal_pattern_gates:{open_suggestions:[],active_rules:[],inactive_rules:[],audit:[],minimum_repetitions:4},
  latest:{
    ok:true, asset:'BTC', symbol:'BTCUSDT', price:64123.4,
    price_status:{ok:true,stale:false,price:64123.4,source:'bybit_public_mark',age_seconds:8},
    execution_gate:{status:'NO_TRADE',orderable:false,reason:'Er is nu geen geldige setup.'},
    blocking_review_timeframes:[], review_timeframes:[], missing_timeframes:[], state_id:'r26-real-state',
    state_generated_at:'2026-07-23T08:00:00+00:00'
  },
  market_stack:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},
  chart_drafts:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},
  composite_map:{asset:'BTC',layers,parent_links:{}}, market_map:{asset:'BTC',layers,parent_links:{}},
  stack_health:{
    asset:'BTC',complete:true,capture_complete:true,verified_complete:true,synced_count:4,confirmed_count:4,required_count:4,
    missing_timeframes:[],review_timeframes:[],fresh:true,
    layers:['1D','4H','15M','3M'].map((timeframe)=>({timeframe,present:true,synced:true,confirmed:true,review_needed:false,fresh:true,age_hours:.2,zones:1,trend:layers[timeframe].trend}))
  },
  journal:{
    summary:'2 sluitingsrecords',
    stats:{records:2,trades:2,wins:1,losses:1,winrate:50,total_pnl:80,snapshot_coverage_pct:100,snapshot_count:2,verified_source_count:1,source_counts:{BYBIT_VERIFIED:1,UNKNOWN:1},unknown_source_count:1,percentage_metrics_available:true,pnl_basis:'closed_pnl',per_richting:{long:120,short:-40},per_symbool:{BTCUSDT:80}},
    trades,curve:[],deepdives:[]
  },
  knowledge:[], knowledge_source:{status:'ACTIEF',processor_active:true,stored_videos:45,stored_lessons:118,processed:45,queue:0,queue_total:103,last_attempt_status:'ok'},
  knowledge_ingestion:[], methodology_sources:{rules:[]}, activity:[], lifecycles:[], risk_profiles:{scalp:.5,day:1,swing:2},
  commercialization:{commercial_content_clean:false},
  services:{knowledge_worker:true,account_watcher:{configured:true,running:true,last_error:null,last_success:'2026-07-23T07:59:00+00:00'},journal_writer:true,telegram_watcher:true,weekly_mentor:{enabled:false}},
  state_id:'r26-real-state', updated_at:'2026-07-23T08:00:00+00:00'
};

(async () => {
  await wait(350);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'demo-only test seam ontbreekt');
  api.setOverview(overview);
  await wait(60);
  const { document } = window;

  assert.equal(document.getElementById('footerVersion').textContent, 'UX v8.4.0');
  const todayNodes = [...document.querySelectorAll('[data-view-section="today"]')];
  assert.equal(todayNodes[0].id, 'todaySummary', 'de focuskaart moet als eerste Vandaag-element renderen');
  assert.equal(document.getElementById('focusTitle').textContent, 'Begin met je dagstart');
  assert.equal(document.getElementById('focusActionButton').textContent, 'Neem de dag met me door');

  for (const id of ['dayStartCard','disciplinePanel','accountGuardPanel','accountPanel','positionPanel','chartWorkflowPanel']) {
    assert.equal(document.getElementById(id).open, false, `${id} moet standaard ingeklapt zijn`);
  }

  const visibleTopItems = [...document.querySelector('.top-summary').children].filter((node) => !node.classList.contains('sr-only'));
  assert.equal(visibleTopItems.length, 2, 'topbar toont alleen markt en status');
  assert.equal(document.getElementById('headerStatus').textContent, 'Begin met je dagstart');
  assert.match(document.getElementById('headerStatus').parentElement.title, /Rekening .* gecontroleerd/i, 'volledige details horen in de tooltip');

  api.switchView('journal');
  await wait(20);
  assert.equal(document.querySelector('#prestaties > .journal-card'), document.querySelector('#prestaties').querySelector('.journal-card'), 'dagboek is de primaire kaart');
  assert.equal(document.querySelector('#prestaties > .performance-board').open, false, 'resultaten en patronen zijn standaard ingeklapt');
  assert.equal(document.querySelectorAll('#journalTableBody tr').length, 2);
  const secondRow = document.querySelectorAll('#journalTableBody tr')[1];
  const sourceIcon = secondRow.querySelector('.source-icon');
  const directionIcon = secondRow.querySelector('.direction-warning');
  assert.equal(sourceIcon.textContent, '●');
  assert.match(sourceIcon.title, /ONBEKEND|UNKNOWN/i);
  assert.equal(directionIcon.textContent, '!');
  assert.match(directionIcon.title, /RICHTING ONGEVERIFIEERD|DIRECTION UNVERIFIED/i);
  assert.doesNotMatch(secondRow.textContent, /RICHTING ONGEVERIFIEERD/, 'lange waarschuwingsbadge mag niet zichtbaar zijn');
  assert.match(secondRow.querySelector('td:nth-child(9)').textContent, /B/, 'proceskolom moet aanwezig blijven');

  api.switchView('today');
  const positionText = document.getElementById('positionsArea').textContent.replace(/\s+/g, ' ').trim();
  assert.match(positionText, /Geen open positie\. Dat is prima\./, 'lege positietekst moet een punt en spatie bevatten');

  document.getElementById('chartWorkflowPanel').open = true;
  document.getElementById('marketMapPanel').open = true;
  const zoneLabels = [...document.querySelectorAll('#layerZones dt')].map((node)=>node.textContent.trim());
  assert.deepEqual(zoneLabels.slice(0,4), ['Rol','Prijsniveau / zone','Reden','Zekerheid']);

  api.setLanguage('en');
  await wait(20);
  assert.equal(document.getElementById('focusTitle').textContent, 'Start with your day briefing');
  assert.equal(document.querySelector('#prestaties > .section-heading h2').textContent, 'Your trade journal');

  assert.match(css, /#todaySummary\.focus-only\{display:block/);
  assert.match(css, /\.journal-table\{width:100%;min-width:0!important;table-layout:fixed\}/);
  assert.match(css, /\.direction-unverified\{box-shadow:none;background:transparent\}/);
  assert.match(css, /#decisionCard \.button\.primary/);
  assert.match(css, /top-summary>\.top-status/);

  console.log('test_ux840_one_focus_r26.js: real payload, one-focus Today, topbar diet, calm journal and NL/EN green');
  window.close();
})().catch((error) => {
  console.error(error);
  window.close();
  process.exitCode = 1;
});
