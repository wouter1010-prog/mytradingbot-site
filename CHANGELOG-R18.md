# Changelog R18

## UX 8.2.7 / Coach R18

- Nieuwe dagstart-coach op Vandaag met vijf vaste mentorsecties.
- Bilinguale briefing uit één semantische response; taalwissel vereist geen nieuwe generatie.
- Bij een lopende positie staat de TP1/TP2-managementregel bovenaan.
- Verouderde, ontbrekende of niet-gecontroleerde chartlagen blokkeren de briefing fail-closed.
- Scenario's zijn uitsluitend ALS-DAN en bevatten een tekstuele invalidatie, geen concrete orderprijzen.
- Recente verliesreeks, procesafwijkingen en midrange-notities sturen de procesfocus.
- Vervolgvragen gebruiken de bestaande actuele coachroute.
- Bronnen, URLs en dossierverwijzingen worden uit mentorantwoorden verwijderd.
- Videotitels en URLs zijn structureel verwijderd uit de LLM-lespayload.
- Engelse stophunt-termen selecteren dossier 10.
- Motor, watcher, journalwriter, Smart Review, lifecycle en orderpoorten ongewijzigd.

## UX 8.2.8 - lege views hotfix
- Sluit `dayStartSection` correct af, zodat Dagboek, Leren en Beheer geen kinderen van de verborgen Vandaag-view zijn.
- Voegt een real-overview-regressietest toe met ontbrekende optionele velden en zichtbaarheid door de volledige voorouderketen.
- Motor, dagstart-backend en kennisimport blijven byte-identiek.
