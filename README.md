# MyTradingBot backend v8.2.2 — Kennisbank Ronde 17

Private-beta handelscockpit met vier tijdframes, Smart Review, geïsoleerde testerwerkruimtes, read-only brokerdata, orderdagboek en een door de gebruiker gehouden eindklik.

Deze release houdt de uitvoerbare handelsmotor op **v8.2.2 / schema 86**, maar voegt een geauditeerde coach-kennislaag toe:

- vaste coachinstructie en productmethodiek bij iedere coachvraag;
- selectie van maximaal 2–3 gecureerde themadossiers via de situatie-index;
- videolessen uitsluitend als aanvullende, lagere kennislaag;
- alle 103 YouTube-bronnen door dezelfde transcriptcontrole;
- permanente quarantaine alleen na een werkelijke `TranscriptUnavailable`;
- bronherkomst intern auditbaar, standaard niet zichtbaar in coachantwoorden;
- externe content blijft privé en niet commercieel vrijgegeven.

## Bindende hiërarchie

1. OPERATORBELEID en PRODUCTVEILIGHEID
2. operationele productmethodiek
3. coachinstructie en gecureerde dossiers
4. aanvullende, gestructureerde videolessen

Geen kennislaag kan een actuele setup, entry, stop, target of order vrijgeven. TradingView-zones en de bestaande mechanische poorten blijven de enige uitvoerbare waarheid.

## Kennisimport

De import staat standaard uit. Activeer pas na Fable ronde 17 en controle van bronrechten/API-kosten:

```bash
MYTRADINGBOT_ENABLE_KNOWLEDGE_INGESTION=1
```

Een bestaande `/data/knowledge_queue.json` wordt veilig gemerged met de verpakte 103-bronnenqueue, zodat een oude 89-bronnenqueue de veertien livestreams niet stil kan verbergen.

## Lokale tests

```bash
python -m unittest discover -p 'test_*.py'
node test_dashboard.js
node test_focus_states.js
node test_i18n.js
node test_i18n_full.js
node test_i18n_payloads.js
node test_smart_review.js
```
