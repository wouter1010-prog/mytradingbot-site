# Deploy — MyTradingBot Ronde 18

**Niet deployen vóór Fable ronde 18 een GO geeft.**

Na GO:

1. Maak een volledige back-up/export van Railway-volume `/data`.
2. Laat alle bestaande secrets en `MYTRADINGBOT_ENABLE_KNOWLEDGE_INGESTION=1` ongewijzigd; deze release reset de importqueue niet.
3. Upload het losse Railway-pakket naar de root van `production-v4`.
4. Commit: `Deploy MyTradingBot R18 day-start coach`.
5. Controleer `https://beta.mytradingbot.ai/health`:
   - `version: 8.2.2`
   - `engine_version: 8.2.2`
   - `schema_version: 86`
   - `knowledge_release: KB-R18`
   - `coach_release: R18-DAGSTART`
   - `ux_release: 8.2.7`
   - `ok: true`
6. Open `https://beta.mytradingbot.ai/dashboard?v=827` en voer `Ctrl + Shift + R` uit.
7. De Chrome-extensie blijft v8.2.6; vervang hem niet voor deze cockpit-only release.
8. Test eerst met een verouderde kaart: de knop moet **Eerst charts vernieuwen** tonen en geen scenario's produceren.
9. Synchroniseer en controleer daarna alle vier lagen; open de briefing opnieuw.
10. Controleer NL en EN, een lopende positie, midrange, een losing-streakfixture en een vervolgcoachvraag.

De optionele Telegram-ochtendbriefing zit bewust niet in deze release.


## UX 8.2.8 hotfix
1. Maak een back-up van `/data`.
2. Upload het volledige Railway-pakket naar `production-v4`.
3. Commit: `Deploy MyTradingBot UX v8.2.8 empty views hotfix`.
4. Controleer `/health`: motor blijft 8.2.2 en schema 86.
5. Open `/dashboard?v=828` en doe Ctrl+Shift+R.
6. Controleer Vandaag, Dagboek, Leren en Beheer.
