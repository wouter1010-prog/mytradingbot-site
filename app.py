import os
from flask import Flask, send_from_directory

app = Flask(__name__, static_folder=None)
ROOT = os.path.dirname(os.path.abspath(__file__))

@app.route("/")
def home():
    return send_from_directory(ROOT, "index.html")

@app.route("/login")
def login():
    return send_from_directory(ROOT, "login.html")

@app.route("/<path:path>")
def assets(path):
    return send_from_directory(ROOT, path)

@app.after_request
def cache(resp):
    if resp.mimetype in ("video/mp4", "image/jpeg", "image/png"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
