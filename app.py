import os, csv, json, datetime
from flask import Flask, send_from_directory, request, jsonify

app = Flask(__name__, static_folder=None)
try:
    from flask_compress import Compress
    app.config["COMPRESS_STREAMS"] = True  # ook bestands-responses (send_from_directory)
    app.config["COMPRESS_MIMETYPES"] = [
        "text/html", "text/css", "text/javascript", "application/javascript",
        "application/json", "image/svg+xml",
    ]
    Compress(app)  # gzip/brotli voor html/js/css/json (media blijft ongecomprimeerd)
except Exception:
    pass  # site werkt ook zonder
ROOT = os.path.dirname(os.path.abspath(__file__))
WAITLIST = os.path.join(ROOT, "waitlist.csv")


@app.route("/")
def home():
    return send_from_directory(ROOT, "index.html")


@app.route("/login")
def login():
    return send_from_directory(ROOT, "login.html")


@app.route("/start")
def start():
    return send_from_directory(ROOT, "getting-started.html")


@app.route("/trades")
def trades():
    return send_from_directory(ROOT, "trades.html")


# De cursus-build staat PLAT in de repo-root (GitHub web-upload kan geen mappen
# slepen): cursus-index.html + index-*.js/css + cursus-favicon.* + alle media
# (les*.mp3, mtb-*.webp/mp4) als losse bestanden.
CURSUS_INDEX = "cursus-index.html"


def _cursus_index():
    if os.path.exists(os.path.join(ROOT, CURSUS_INDEX)):
        return send_from_directory(ROOT, CURSUS_INDEX)
    return send_from_directory(ROOT, "cursus.html")  # fallback: oude pagina


@app.route("/cursus")
@app.route("/cursus/")
@app.route("/course")
def cursus():
    return _cursus_index()


@app.route("/cursus/<path:sub>")
def cursus_app(sub):
    # /cursus/assets/x.js en /cursus/favicon.* -> platte bestanden in de root;
    # /cursus/manus-storage/x -> media in de root; al het overige (les/3,
    # examen, certificaat) -> index (history-router).
    base = os.path.basename(sub)
    if sub.startswith("assets/") and os.path.isfile(os.path.join(ROOT, base)):
        return send_from_directory(ROOT, base)
    if sub in ("favicon.ico", "favicon.png"):
        cf = "cursus-" + sub
        return send_from_directory(ROOT, cf if os.path.exists(os.path.join(ROOT, cf)) else "favicon.ico")
    if sub.startswith("manus-storage/") and os.path.isfile(os.path.join(ROOT, base)):
        return send_from_directory(ROOT, base)
    return _cursus_index()


@app.route("/manus-storage/<path:fname>")
def cursus_media(fname):
    # Media van de cursus; staan plat in de root (of in manus-storage/ als die bestaat).
    sub = os.path.join(ROOT, "manus-storage", os.path.basename(fname))
    if os.path.isfile(sub):
        return send_from_directory(os.path.join(ROOT, "manus-storage"), os.path.basename(fname))
    return send_from_directory(ROOT, os.path.basename(fname))


CURSUS_DATA = os.path.join(ROOT, "cursus-data.csv")


@app.route("/cursus-data", methods=["POST"])
def cursus_data():
    # Anonieme leer-events van de cursus-app (geen namen/ID's/cookies).
    data = request.get_json(silent=True) or {}
    allowed = {"les_gestart", "les_afgerond", "quiz_antwoord", "examen_gestart", "examen_resultaat"}
    event = str(data.get("event") or "")[:32]
    if event not in allowed:
        return jsonify(ok=False), 400
    row = {
        "ts": str(data.get("ts") or datetime.datetime.utcnow().isoformat())[:32],
        "event": event,
        "les": str(data.get("les") if data.get("les") is not None else "")[:8],
        "vraag": str(data.get("vraag") if data.get("vraag") is not None else "")[:8],
        "correct": str(data.get("correct") if data.get("correct") is not None else "")[:8],
    }
    print("CURSUS-DATA:", json.dumps(row, ensure_ascii=False), flush=True)
    try:
        new = not os.path.exists(CURSUS_DATA)
        with open(CURSUS_DATA, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "event", "les", "vraag", "correct"])
            if new:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        print("CURSUS-DATA WRITE ERROR:", e, flush=True)
    return jsonify(ok=True)


@app.route("/cockpit")
def cockpit_entry():
    # Premium entry/gate preview for the (future) users cockpit.
    return send_from_directory(ROOT, "cockpit-entry-PREMIUM.html")


@app.route("/cockpit-demo")
def cockpit_demo():
    # Clickable static preview of the users cockpit dashboard.
    return send_from_directory(ROOT, "cockpit-demo.html")


@app.route("/waitlist", methods=["POST"])
def waitlist():
    data = request.get_json(silent=True) or request.form.to_dict()
    row = {
        "ts": data.get("ts") or datetime.datetime.utcnow().isoformat(),
        "name": (data.get("name") or "").strip()[:120],
        "email": (data.get("email") or "").strip()[:160],
        "trades": (data.get("trades") or "").strip()[:160],
        "lang": (data.get("lang") or "").strip()[:5],
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
    }
    # Always log so signups are visible in the Railway logs.
    print("WAITLIST SIGNUP:", json.dumps(row, ensure_ascii=False), flush=True)
    # Best-effort append to CSV (note: Railway's disk is ephemeral without a volume).
    try:
        new = not os.path.exists(WAITLIST)
        with open(WAITLIST, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "name", "email", "trades", "lang", "ip"])
            if new:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        print("WAITLIST WRITE ERROR:", e, flush=True)
    return jsonify(ok=True)


@app.route("/<path:path>")
def assets(path):
    return send_from_directory(ROOT, path)


@app.after_request
def cache(resp):
    if resp.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript", "application/json"):
        resp.direct_passthrough = False  # zodat flask-compress bestandsresponses kan gzippen
    if resp.mimetype in ("video/mp4", "image/jpeg", "image/png", "image/svg+xml", "image/webp",
                         "text/css", "application/javascript", "text/javascript", "font/woff2"):
        # gehashte bestandsnamen -> agressief cachen
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif resp.mimetype == "audio/mpeg":
        # mp3's hebben geen hash in de naam -> korte cache (1 dag)
        resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
