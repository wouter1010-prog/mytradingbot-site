# Acceptatietest v8.2.2

1. `/health` toont 8.2.2 / engine 8.2.2 / schema 86.
2. Synchroniseer een reeds goedgekeurde, inhoudelijk ongewijzigde chart opnieuw: de goedkeuring blijft staan.
3. Wijzig alleen de 4H-structuur materieel: uitsluitend 4H verschijnt als gerichte controle.
4. Synchroniseer 15M zonder setup: geen formulier; status wacht op setup.
5. Synchroniseer 3M zonder trigger: geen formulier; status wacht op trigger.
6. Laat een nieuwe 3M-trigger detecteren: uitsluitend 3M vraagt menselijke controle.
7. Open positie blijft voorrang houden op chartbeheer.
8. Testerwerkruimte blijft paper-only en geïsoleerd.
9. Definitieve orderklik blijft uitsluitend bij de gebruiker.

## Kennisbank Ronde 17

- [ ] `/health` toont `knowledge_release: KB-R17`.
- [ ] Coach in NL noemt geen bronnen, dossiers, video’s, modules of `[1]`-verwijzingen.
- [ ] Coach in EN noemt geen bronnen, dossiers, video’s, modules of `[1]`-verwijzingen.
- [ ] Stoploss/stophunt-vraag selecteert dossiers 06 en 10 in debugtest.
- [ ] Per coachvraag worden minimaal 2 en maximaal 3 primaire dossiers geladen.
- [ ] Ingestionstatus toont 103 kandidaten en 0 vooraf uitgesloten bronnen.
- [ ] Oude 89-bronnenqueue op `/data` verbergt geen verpakte bronnen.
- [ ] Permanente transcriptfout wordt `excluded_no_transcript`.
- [ ] Tijdelijke Supadata-fout wordt `retryable_error`.
- [ ] Geen transcriptveld zichtbaar via coach- of kennis-API.
- [ ] `MYTRADINGBOT_ENABLE_KNOWLEDGE_INGESTION` blijft 0 tot na Fable GO.
