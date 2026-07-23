'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const token = 'r23-owner-token-with-at-least-thirty-two-chars';
const requests = [];
const layer = (timeframe) => ({timeframe,trend:'range',range_low:62000,range_high:66000,overall_confidence:82,at:'2026-07-20T08:00:00+00:00',zones:[],warnings:[]});
const layers = Object.fromEntries(['1D','4H','15M','3M'].map((tf)=>[tf,layer(tf)]));
const overview = {
  ok:true,asset:'BTC',updated_at:'2026-07-20T08:05:00+00:00',
  principal:{role:'owner',display_name:'Owner',workspace_id:'owner'},profile:{mode:'live',manual_equity:10000},
  account:{equity:10000,equity_fresh:true,positions:[]},
  latest:{price:64123.4,price_status:{ok:true,stale:false,price:64123.4,source:'bybit_public_mark',age_seconds:6},blocking_review_timeframes:[],execution_gate:{status:'NO_TRADE',orderable:false,reason:'Er is nu geen geldige setup.'},setup:{}},
  market_stack:{assets:{BTC:{layers}}},chart_drafts:{assets:{BTC:{layers}}},composite_map:{layers,parent_links:{}},market_map:{layers,parent_links:{}},
  stack_health:{synced_count:4,confirmed_count:4,capture_complete:true,fresh:true,layers:Object.keys(layers).map((timeframe)=>({timeframe,present:true,synced:true,confirmed:true,fresh:true,zones:0}))},
  journal:{stats:{records:0,trades:0,wins:0,losses:0,total_pnl:0,source_counts:{}},trades:[],deepdives:[]},knowledge:[],methodology_sources:{rules:[]},knowledge_ingestion:[],activity:[],
  knowledge_source:{status:'ACTIEF',processor_active:true,worker_running:true,rss_enabled:true,channel_id_configured:true,last_rss_check_at:'2026-07-20T08:01:00+00:00',last_auto_fetched_at:'2026-07-20T08:02:00+00:00',last_auto_video_title:'Nieuwe openbare video',processed:103,stored_lessons:220,queue:0,queue_total:103,excluded_no_transcript:4},
  services:{account_watcher:{running:true}}
};
const response = (body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body,blob:async()=>new Blob()});
const dom = new JSDOM(html,{url:`http://localhost/dashboard?static=1#access=${token}`,runScripts:'outside-only',pretendToBeVisual:true});
const {window}=dom;
window.AbortController=global.AbortController;
window.URL.createObjectURL=()=> 'blob:preview';window.URL.revokeObjectURL=()=>{};
window.HTMLElement.prototype.scrollIntoView=function(){};window.scrollTo=function(){};
window.HTMLDialogElement.prototype.showModal=function(){this.open=true;this.setAttribute('open','');};
window.HTMLDialogElement.prototype.close=function(){this.open=false;this.removeAttribute('open');};
window.fetch=async(url,options={})=>{
  const pathname=String(url);
  if(pathname.includes('/api/v1/config')) return response({ok:true,version:'8.2.2'});
  if(pathname.includes('/api/v1/overview')) return response(overview);
  if(pathname.includes('/api/v2/beta/invites')) return response({ok:true,invites:[]});
  if(pathname.includes('/api/v2/beta/testers')) return response({ok:true,testers:[]});
  if(pathname.includes('/api/v1/knowledge/queue')){
    const body=JSON.parse(options.body||'{}'); requests.push({pathname,body});
    return response({ok:true,result:{video_id:'abcdefghijk',status:'queued',queued:true},status:overview.knowledge_source},202);
  }
  throw new Error(`Onverwachte request in R23 UI-test: ${pathname}`);
};
window.eval(script);
const wait=(ms)=>new Promise((resolve)=>setTimeout(resolve,ms));
const click=(node)=>node.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));

(async()=>{
  await wait(300);
  const {document}=window;
  assert(document.getElementById('loginLayer').classList.contains('hidden'),'owner overview moet laden');
  click(document.querySelector('[data-view="manage"]'));
  await wait(30);
  const section=document.getElementById('knowledgeManagementSection');
  assert(section && !section.classList.contains('hidden'),'Kennisbronbeheer moet alleen voor owner zichtbaar zijn');
  assert.match(document.getElementById('knowledgeAutoFetchLine').textContent,/Laatst automatisch opgehaald/i);
  assert.match(document.getElementById('knowledgeAutoFetchLine').textContent,/Nieuwe openbare video/i);
  assert.equal(document.getElementById('knowledgeManagementBadge').textContent,'ACTIEF');
  document.getElementById('knowledgeManagementPanel').open=true;
  const input=document.getElementById('platinumVideoUrl');
  input.value='https://youtube.com/live/abcdefghijk?feature=share';
  document.getElementById('platinumQueueForm').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await wait(80);
  assert.equal(requests.length,1,'Platinum-formulier moet exact één owner-only queue-call doen');
  assert.equal(requests[0].pathname.includes('/api/v1/knowledge/queue'),true);
  assert.equal(requests[0].body.url,'https://youtube.com/live/abcdefghijk?feature=share');
  assert.match(document.getElementById('platinumQueueResult').textContent,/Toegevoegd aan de kenniswachtrij/i);
  assert.match(document.querySelector('#knowledgeManagementSection .small-copy').textContent,/Geen Discord-scraping/i);
  click(document.querySelector('[data-language="en"]'));
  await wait(40);
  assert.match(document.getElementById('knowledgeManagementSummary').textContent,/Public channel monitoring/i);
  assert.equal(document.getElementById('footerVersion').textContent,'UX v8.4.0');
  console.log('PASS R23 UI: owner-only Platinum queue, automatic fetch status, NL/EN and existing overview flow');
  window.close();
  process.exit(0);
})().catch((error)=>{console.error(error);window.close();process.exit(1);});
