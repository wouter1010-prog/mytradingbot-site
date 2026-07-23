'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, 'dashboard.js'), 'utf8');
function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, `${name} ontbreekt`);
  const brace = source.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escape = false;
  for (let i = brace; i < source.length; i++) {
    const ch = source[i];
    if (quote) {
      if (escape) escape = false;
      else if (ch === '\\') escape = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`einde ${name} niet gevonden`);
}

const ids = [
  'disciplineScore','disciplineScoreLabel','disciplineBadge','disciplineStreak','disciplineStreakMeta',
  'disciplineRules','disciplineRulesMeta','disciplineTrend','disciplineTrendMeta','disciplineBreakdownRules',
  'disciplineBreakdownGrades','disciplineBreakdownRoutine','disciplineTodayTitle','disciplineTodayText','noTradeDayButton'
];
const nodes = Object.fromEntries(ids.map((id) => [id, {
  id, textContent:'', className:'', disabled:false,
  classList:{ values:new Set(), toggle(name,on){ if(on)this.values.add(name);else this.values.delete(name); }, contains(name){return this.values.has(name);} }
}]));
const $ = (id) => nodes[id];
const finite = (value) => value === null || value === undefined || value === '' ? null : Number(value);
const format = (value, digits=2) => Number(value).toLocaleString('nl-NL',{maximumFractionDigits:digits,minimumFractionDigits:0});
const state = { language:'nl', overview:{ discipline:{
  score:82,score_band:'steady',rules:{count:8,followed:7,pct:87.5},
  grades:{count:8,score:79,trend:'improving',recent_score:86,previous_score:70,delta:16},
  routine:{observed_days:7,completed_days:5,pct:71.4},
  streak:{current:4,longest:6,today_complete:false,status:'available_today',earned_by_day_start:false,earned_by_no_trade:false},
  today:{day_start_completed:false,no_trade_declared:false,no_trade_allowed:true,trade_activity_present:false,open_position:false}
}}};

eval(`(${extractFunction('renderDiscipline')})`)();
assert.equal(nodes.disciplineScore.textContent, '82');
assert.match(nodes.disciplineStreak.textContent, /4 dagen/);
assert.match(nodes.disciplineRules.textContent, /88%/);
assert.equal(nodes.disciplineTrend.textContent, 'Verbeterend');
assert.match(nodes.disciplineStreakMeta.textContent, /Verdien vandaag/);
assert.equal(nodes.noTradeDayButton.disabled, false);
assert.equal(nodes.noTradeDayButton.classList.contains('hidden'), false);

state.language = 'en';
state.overview.discipline = {
  ...state.overview.discipline,
  score:42,score_band:'earn_back',
  streak:{...state.overview.discipline.streak,current:0,status:'earn_back'},
  today:{...state.overview.discipline.today,trade_activity_present:true,no_trade_allowed:false}
};
eval(`(${extractFunction('renderDiscipline')})`)();
assert.equal(nodes.disciplineScoreLabel.textContent, 'Earn-back');
assert.match(nodes.disciplineStreakMeta.textContent, /Earn-back/);
assert.match(nodes.disciplineTodayText.textContent, /Trading activity/);
assert.equal(nodes.noTradeDayButton.disabled, true);

state.overview.discipline = {
  ...state.overview.discipline,
  score:90,score_band:'strong',
  streak:{...state.overview.discipline.streak,current:5,status:'earned_today',today_complete:true,earned_by_day_start:false,earned_by_no_trade:true},
  today:{...state.overview.discipline.today,trade_activity_present:false,no_trade_allowed:false,no_trade_declared:true}
};
eval(`(${extractFunction('renderDiscipline')})`)();
assert.match(nodes.disciplineTodayText.textContent, /process profit/);
assert.equal(nodes.noTradeDayButton.classList.contains('hidden'), true);
console.log('test_phase5a_pure_ui_r25a.js: 14/14 process-first render assertions green');
