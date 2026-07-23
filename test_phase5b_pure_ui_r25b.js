'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'dashboard.js'),'utf8');
function extractFunction(name){
  const start=source.indexOf(`function ${name}(`); assert(start>=0,`${name} ontbreekt`);
  const brace=source.indexOf('{',start); let depth=0,quote=null,escape=false;
  for(let i=brace;i<source.length;i++){const ch=source[i];if(quote){if(escape)escape=false;else if(ch==='\\')escape=true;else if(ch===quote)quote=null;continue;}if(ch==='"'||ch==="'"||ch==='`'){quote=ch;continue;}if(ch==='{')depth++;if(ch==='}'&&--depth===0)return source.slice(start,i+1);}throw new Error('einde ontbreekt');
}
function classList(){return {values:new Set(),toggle(name,on){if(on)this.values.add(name);else this.values.delete(name);},contains(name){return this.values.has(name);}};}
const ids=['accountGuardSection','accountGuardBadge','accountGuardBuffer','accountGuardBufferMeta','accountGuardBufferFill','accountGuardBufferTrack','accountGuardPosition','accountGuardPositionMeta','accountGuardCooldown','accountGuardCooldownMeta','accountGuardReset','commitmentForm','commitmentLossLimit','commitmentActivateButton','accountGuardNotice'];
const nodes=Object.fromEntries(ids.map(id=>[id,{id,textContent:'',className:'',hidden:false,disabled:false,value:'',style:{},classList:classList(),options:[]} ]));
const card={classList:classList()}; nodes.accountGuardSection.querySelector=()=>card;
nodes.commitmentLossLimit.options=[.5,1,1.5,2].map(v=>({value:String(v)}));
const $=id=>nodes[id];
const finite=v=>(v===null||v===undefined||v==='')?null:Number(v);
const money=v=>v==null?'—':`US$ ${Number(v).toLocaleString('nl-NL',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const format=(v,d=2)=>Number(v).toLocaleString('nl-NL',{maximumFractionDigits:d});
const dateText=v=>String(v||'—');
const state={language:'nl',overview:{principal:{role:'owner'},account_guard:{active:false,ticket_blocked:false,daily_loss_limit_pct:2,buffer_remaining_usdt:300,buffer_remaining_pct:75,buffer_state:'healthy',positions_open:0,max_positions:1,position_block:false,cooldown_seconds_remaining:0,next_reset_at:'2026-07-23T22:00:00Z'}}};

eval(`(${extractFunction('renderAccountGuard')})`)();
assert.equal(nodes.accountGuardBuffer.textContent,'US$ 300,00');
assert.equal(nodes.accountGuardBufferFill.style.width,'75%');
assert.equal(nodes.commitmentActivateButton.disabled,false);
assert.match(nodes.accountGuardNotice.textContent,/niet uit of ruimer/i);
assert.equal(card.classList.contains('locked'),false);

state.overview.account_guard={...state.overview.account_guard,active:true,ticket_blocked:true,position_block:true,positions_open:1,buffer_remaining_usdt:80,buffer_remaining_pct:20,buffer_state:'low',cooldown_seconds_remaining:1200};
eval(`(${extractFunction('renderAccountGuard')})`)();
assert.equal(nodes.commitmentActivateButton.disabled,true);
assert.match(nodes.commitmentActivateButton.textContent,/Vergrendeld tot morgen/);
assert.match(nodes.accountGuardPositionMeta.textContent,/Tweede positie geblokkeerd/);
assert.match(nodes.accountGuardCooldown.textContent,/20 min/);
assert.equal(card.classList.contains('locked'),true);
assert.equal(card.classList.contains('blocked'),true);

state.language='en';
eval(`(${extractFunction('renderAccountGuard')})`)();
assert.match(nodes.commitmentActivateButton.textContent,/Locked until tomorrow/);
assert.match(nodes.accountGuardNotice.textContent,/no off switch/i);
assert.match(source,/r-breach-badge/);
assert.match(source,/\/api\/v1\/commitment\/activate/);
assert.doesNotMatch(source,/commitment\/deactivate/);
console.log('test_phase5b_pure_ui_r25b.js: 15/15 one-way account-guard render assertions green');
