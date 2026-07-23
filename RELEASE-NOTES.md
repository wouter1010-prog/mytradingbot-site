# Release notes — MyTradingBot Ronde 18

Presentatie- en coachrelease bovenop motor v8.2.2 / schema 86, kennisbank KB-R17 en dashboard UX v8.2.6.

## Drie auditrestpunten gesloten

1. Mechanische en LLM-antwoorden worden na generatie ontdaan van URL's, broncodes en verwijzingen zoals `zie dossier 07`.
2. Aanvullende videolessen gaan naar het taalmodel zonder videotitel, bronnaam of URL. Alleen een interne lesson-id, korte samenvatting, type, confidence en status blijven over.
3. Engelse vragen met `stop hunt`, `stop hunted`, `hunt` of `hunted` activeren de liquiditeits-/stophuntkennis uit dossier 10.

## Dagstart-coach

Op Vandaag staat nu **Neem de dag met me door**. De briefing leest uitsluitend de bestaande overview-state en levert:

1. Waar staan we — trends per laag en positie in de 4H-range.
2. Maximaal drie ALS-DAN-scenario's, ieder met invalidatie.
3. Een expliciet geen-trade-scenario.
4. Eén procesfocus uit recente journaldata.
5. Drie dagstart-toetsvragen.

Bij een lopende positie staat positie-management vóór de vijf dagstartsecties. TP1 verandert de technische stop niet; pas na TP2 en alleen bij een winstgevend restant mag de stop handmatig in profit.

## Harde grenzen

- Geen scenario's bij ontbrekende, verouderde of niet meer geverifieerde chartlagen.
- Geen concrete entry-, stop-loss- of take-profitprijzen als advies.
- Geen voorspellende taal; scenario's blijven conditioneel.
- Geen order-, lifecycle-, chart-, journal- of riskmutaties vanuit de dagstartroute.
- De bestaande coachchat blijft beschikbaar voor vervolgvragen met dezelfde actuele cockpitdata.

## Niet in deze ronde

De optionele geplande Telegram-ochtendbriefing is bewust niet toegevoegd. Eerst wordt de handmatige dagstart live geverifieerd; een scheduler hoort in een afzonderlijke, opnieuw geauditeerde onderhoudsronde.

## Versies

- motor: `8.2.2`
- schema: `86`
- kennislaag: `KB-R18`
- coach: `R18-DAGSTART`
- cockpit UX: `8.2.7`
- Chrome-extensie: ongewijzigd `8.2.6`

## UX 8.2.8 hotfix
- Herstelt lege Dagboek-, Leren- en Beheertabs door de ontbrekende afsluiting van de dagstartsectie toe te voegen.
- Nieuwe real-overview regressietest controleert zichtbaarheid via de volledige voorouderketen en ontbrekende optionele velden.
- Motor, dagstart-backend en kennisimport zijn niet gewijzigd.
