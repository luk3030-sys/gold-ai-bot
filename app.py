from flask import Flask

app = Flask(__name__)

@app.get("/")
def home():
    return "Gold AI Bot działa"

@app.get("/health")
def health():
    return {"status": "ok"}
