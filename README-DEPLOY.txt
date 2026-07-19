MyTradingBot marketing site — Railway static service

Bestanden (moeten ALLEMAAL samen in de repo-root):
  app.py                 tiny Flask static server (gunicorn app:app)
  requirements.txt       flask + gunicorn
  Procfile               start command
  index.html             landingspagina  ->  mytradingbot.ai
  login.html             login           ->  mytradingbot.ai/login
  mtb-hero.mp4           video-achtergrond
  mtb-hero-poster.jpg    poster/fallback

Railway:
  1. Nieuw project/service -> Deploy from GitHub repo (of upload deze map).
  2. Railway detecteert Python -> start met "gunicorn app:app".
  3. Settings -> Networking -> Custom Domain -> mytradingbot.ai (en www).
  4. Zet bij je DNS de CNAME/A-records die Railway toont.
