import os, csv, json, datetime
from flask import Flask, send_from_directory, request, jsonify

app = Flask(__name__, static_folder=None)
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


@app.route("/cursus")
@app.route("/course")
def cursus():
    return send_from_directory(ROOT, "cursus.html")


@app.route("/cockpit")
def cockpit_entry():
    # Premium entry/gate preview for the (future) users cockpit.
    return send_from_directory(ROOT, "cockpit-entry-PREMIUM.html")


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
    if resp.mimetype in ("video/mp4", "image/jpeg", "image/png", "image/svg+xml"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
