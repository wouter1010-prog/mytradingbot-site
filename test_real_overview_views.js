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
window.fetch = async () => { throw new Error('Real-schema test must not use network data'); };
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const visibleThroughAncestors = (element) => {
  for (let node = element; node; node = node.parentElement) {
    if (node.hidden || node.hasAttribute?.('hidden')) return false;
  }
  return true;
};
const layer = (timeframe) => ({
  timeframe,
  trend: timeframe === '1D' ? 'range' : 'down',
  range_low: 62000,
  range_high: 66000,
  overall_confidence: 82,
  at: '2026-07-20T07:45:00+00:00',
  zones: [{ id:`${timeframe}-z1`, role:'support', intent:'structure', bottom:62500, top:62800, reason:'Getekende zone' }],
  warnings: []
});
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf) => [tf, layer(tf)]));
const trades = Array.from({ length: 6 }, (_, index) => ({
  id: `closed-${index + 1}`,
  source_class: index === 5 ? 'UNKNOWN' : 'BYBIT_VERIFIED',
  source_label: index === 5 ? 'ONBEKEND' : 'BYBIT GEVERIFIEERD',
  symbol: 'BTCUSDT',
  direction: index % 2 ? 'short' : 'long',
  close_side: index % 2 ? 'Buy' : 'Sell',
  direction_consistency: index === 5 ? 'unavailable' : 'verified',
  entry: 63000 + index * 100,
  exit: 63100 + index * 100,
  qty: 0.1,
  pnl: index === 4 ? -45 : 80 + index,
  equity_snapshot: index < 4 ? 20000 : null,
  pnl_pct: index < 4 ? 0.4 : null,
  closed_at: `2026-07-${String(10 + index).padStart(2, '0')}T12:00:00+00:00`,
  process_grade: index < 3 ? 'A' : undefined,
  // Real historic rows may omit fees, funding, MAE/MFE and lesson.
}));

const realOverview = {
  ok: true,
  version: '8.2.2',
  engine_version: '8.2.2',
  schema_version: 86,
  ux_release: '8.2.7',
  coach_release: 'R18-DAGSTART',
  asset: 'BTC',
  workflow: ['1D','4H','15M','3M'],
  principal: { id:'owner', workspace_id:'owner', display_name:'Wouter', role:'owner', mode:'owner', capabilities:[] },
  profile: { workspace_id:'owner', display_name:'Wouter', mode:'owner' },
  account: { equity:20123.45, equity_fresh:true, equity_age_seconds:20, positions:[] },
  latest: {
    ok:true,
    asset:'BTC',
    symbol:'BTCUSDT',
    price:64123.4,
    price_status:{ ok:true, stale:false, price:64123.4, source:'bybit_public_mark', age_seconds:8 },
    execution_gate:{ status:'NO_TRADE', orderable:false, reason:'Er is nu geen geldige setup.' },
    blocking_review_timeframes:[],
    state_id:'real-overview-state',
    state_generated_at:'2026-07-20T08:00:00+00:00'
  },
  market_stack:{ assets:{ BTC:{ layers } }, latest:{ asset:'BTC', timeframe:'3M' } },
  chart_drafts:{ assets:{ BTC:{ layers } }, latest:{ asset:'BTC', timeframe:'3M' } },
  composite_map:{ asset:'BTC', layers, parent_links:{} },
  market_map:{ asset:'BTC', layers, parent_links:{} },
  stack_health:{
    asset:'BTC', complete:true, capture_complete:true, verified_complete:true,
    synced_count:4, confirmed_count:4, required_count:4, missing_timeframes:[], review_timeframes:[], fresh:true,
    layers:['1D','4H','15M','3M'].map((timeframe) => ({ timeframe, present:true, synced:true, confirmed:true, review_needed:false, fresh:true, age_hours:0.3, zones:1, trend:layers[timeframe].trend }))
  },
  journal:{
    summary:'6 sluitingsrecords',
    stats:{
      records:6, trades:6, wins:5, losses:1, winrate:83.33, total_pnl:365,
      snapshot_coverage_pct:66.67, snapshot_count:4, verified_source_count:5,
      source_counts:{BYBIT_VERIFIED:5,UNKNOWN:1}, unknown_source_count:1,
      percentage_metrics_available:false, percentage_metrics_reason:'Onvoldoende historische equitydata — 4 van 6 records.',
      pnl_basis:'closed_pnl', sample_label:'onvoldoende trades', per_richting:{long:245,short:120}, per_symbool:{BTCUSDT:365}
    },
    trades,
    curve:[],
    deepdives:[]
  },
  knowledge:[{
    id:'lesson-1', type:'context', category:'context', title:'Werk vanuit scenario’s',
    summary:'Gebruik conditionele scenario’s en wacht op bevestiging.', source_label:'PRIVÉ KENNIS',
    source_title:'Interne kennisbank', confidence:92, official_status:'gecontroleerd', date:'2026-07-20'
  }],
  knowledge_source:{
    status:'ACTIEF', processor_active:true, stored_videos:45, stored_lessons:118,
    processed:45, queue:58, queue_total:103, last_video_date:'2026-07-19',
    last_video_title:'Privébron', last_attempt_at:'2026-07-20T07:55:00+00:00'
    // last_error, warning and extractor_version are intentionally absent.
  },
  knowledge_ingestion:[],
  methodology_sources:{ rules:[] },
  activity:[],
  lifecycles:[],
  risk_profiles:{scalp:0.5,day:1,swing:2},
  commercialization:{ commercial_content_clean:false },
  services:{
    knowledge_worker:true,
    account_watcher:{ configured:true, running:true, last_error:null, last_success:'2026-07-20T07:59:00+00:00' },
    journal_writer:true,
    telegram_watcher:true
  },
  state_id:'real-overview-state',
  updated_at:'2026-07-20T08:00:00+00:00'
};

(async () => {
  await wait(350);
  const { document } = window;
  const testApi = window.__MYTRADINGBOT_TEST__;
  assert(testApi, 'test seam ontbreekt');
  testApi.setOverview(realOverview);
  await wait(50);

  // Structural regression guard: a view section may never live inside a different view section.
  for (const section of document.querySelectorAll('[data-view-section]')) {
    const parentView = section.parentElement?.closest?.('[data-view-section]');
    assert(!parentView || parentView.dataset.viewSection === section.dataset.viewSection,
      `${section.id || section.dataset.viewSection} is genest in ${parentView?.id || parentView?.dataset.viewSection}`);
  }

  const expectations = [
    ['journal', 'prestaties', 'performanceSummaryKpis', /Totaal resultaat/i],
    ['learn', 'learnView', 'knowledgeList', /Werk vanuit scenario/i],
    ['manage', 'manageView', 'betaWorkspaceSummary', /Wouter|OWNER LIVE|Live eigenaar/i],
  ];
  for (const [view, sectionId, contentId, pattern] of expectations) {
    testApi.switchView(view);
    await wait(30);
    const section = document.getElementById(sectionId);
    const content = document.getElementById(contentId);
    assert.equal(section.hidden, false, `${view}: eigen section staat verborgen`);
    assert.equal(visibleThroughAncestors(section), true, `${view}: een verborgen ancestor maakt de hele view leeg`);
    assert.match(section.textContent, /\S/, `${view}: statische kop of empty state ontbreekt`);
    assert.match(content.textContent, pattern, `${view}: real-schema renderer leverde geen inhoud`);
  }

  testApi.switchView('journal');
  assert.equal(document.querySelectorAll('#journalTableBody tr').length, 6, 'alle zes real-schema journaalrijen moeten renderen');
  testApi.switchView('learn');
  assert.match(document.getElementById('deepdivesList').textContent, /Nog geen deepdives/i, 'ontbrekende optionele deepdives moeten een empty state tonen');
  testApi.switchView('manage');
  assert.match(document.getElementById('activityTimeline').textContent, /Nog geen systeemmeldingen/i, 'ontbrekende activity moet een empty state tonen');

  assert.equal(document.getElementById('footerVersion').textContent, 'UX v8.4.0');
  console.log('test_real_overview_views.js: real overview-schema toont Dagboek, Leren en Beheer zonder verborgen ancestors');
  window.close();
})().catch((error) => {
  console.error(error);
  window.close();
  process.exitCode = 1;
});
