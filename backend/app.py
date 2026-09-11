import os

from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv


load_dotenv()


app = Flask(
    __name__,
    static_folder="../frontend",
    static_url_path=""
)


CORS(app)


from backend.routes.chat import chat_bp

app.register_blueprint(chat_bp)


@app.route("/")
def home():

    return send_from_directory(
        "../frontend",
        "index.html"
    )


@app.route("/login.html")
def login():

    return send_from_directory(
        "../frontend",
        "login.html"
    )


@app.route("/signup.html")
def signup():

    return send_from_directory(
        "../frontend",
        "signup.html"
    )


@app.route("/config.js")
def config():

    return send_from_directory(
        "../frontend",
        "config.js"
    )

@app.route("/downloads/<path:filename>")
def download_apk(filename):

    return send_from_directory(
        "../frontend/downloads",
        filename,
        as_attachment=True
    )


@app.route("/api/health")
def health():

    return {
        "success": True,
        "name": "JeffAI",
        "status": "online"
    }


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )