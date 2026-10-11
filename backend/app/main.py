from fastapi import FastAPI

app = FastAPI(title="Daki Replica")

@app.get("/health")
def health():
    return {"status": "ok"}
