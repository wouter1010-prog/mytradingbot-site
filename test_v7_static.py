from pathlib import Path
from html.parser import HTMLParser
import re

ROOT = Path(__file__).resolve().parent

class IdParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=set(); self.details=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if d.get('id'): self.ids.add(d['id'])
        if tag=='details': self.details.append(d)

html=(ROOT/'mytradingbot-dashboard.html').read_text(encoding='utf-8')
js=(ROOT/'dashboard.js').read_text(encoding='utf-8')
css=(ROOT/'dashboard.css').read_text(encoding='utf-8')
p=IdParser(); p.feed(html)
required={
 'decisionCard','decisionReason','nextAction','parentChain','ticketReadinessCard','ticketReadiness',
 'startReviewButton','reviewProgress','performanceSummaryKpis','performanceAdvancedKpis','performanceDetailsPanel','journalTableBody','tradeInspector',
 'knowledgeSourceGrid','journalSourceStatus','methodologyPolicy','ingestionTimeline','knowledgePanel','auditPanel',
 'betaWorkspaceSection','betaWorkspaceSummary','ownerBetaAdmin','testerBetaTools','inviteList','inviteCount','feedbackDialog','feedbackForm'
}
missing=sorted(required-p.ids)
assert not missing, f'Ontbrekende dashboardonderdelen: {missing}'
assert 'UX v8.4.0' in html and "const VERSION = '8.4.0'" in js and "const MOTOR_VERSION = '8.2.2'" in js
assert 'Prijsbeweging richting de zone' in html and '>Stijgend richting zone<' in html and '>Dalend richting zone<' in html
assert 'Benadering<select' not in html
assert '/api/v2/beta/invites/revoke' in js and 'Trek uitnodiging in' in js
assert '.innerHTML' not in js, 'Cockpit mag API/modeldata niet via innerHTML renderen'
assert "value === null || value === undefined || String(value).trim() === ''" in js, 'Lege waarden mogen nooit als numerieke nul worden getoond'
assert "clear($('parentChain'))" in js, 'Parent-chain moet voor iedere render worden leeggemaakt'
assert 'sessionStorage' in js and "fragment.get('access')" in js and 'history.replaceState' in js, 'Dashboardtoken moet via URL-fragment naar sessieopslag worden overgedragen'
assert 'stopPolling();' in js and "logoutButton" in js, 'Polling moet bij logout stoppen'
assert "formulaSafe" in js or re.search(r"^[^\n]*[=+\-@]", js, re.M), 'CSV-export moet formule-injectie afvangen'
for panel in ('knowledgeSourcePanel','coachPanel','knowledgePanel','auditPanel','deepdivesPanel','performanceDetailsPanel'):
    assert f'id="{panel}"' in html
    fragment=html.split(f'id="{panel}"',1)[1].split('>',1)[0]
    assert ' open' not in fragment, f'{panel} hoort standaard dicht te staan'
for token in ('beta-workspace','feedback', 'decision-flow','ticket-readiness','review-progress','trade-inspector','methodology-policy','ingestion-timeline'):
    assert token in css, f'CSS ontbreekt voor {token}'
assert 'id="appNav"' in html and all(f'data-view="{view}"' in html for view in ('today','journal','learn','manage'))
assert 'id="chartWorkflowPanel"' in html and 'id="marketMapPanel"' in html and 'id="chartTechPanel"' in html
assert 'Wat je trade nu doet' in html and 'Open resultaat' in html
assert 'Open orders, entry/SL/TP-lijnen, signalen en de actuele prijs tellen nooit als zone.' in html
assert "function deriveUserState()" in js and "function switchView(view" in js
print('test_v8_static.py: v8.4.0 one-focus UX, kernpoorten en DOM-safety geslaagd')
