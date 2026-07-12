from fastapi import FastAPI

app = FastAPI(title="oto-brain")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
