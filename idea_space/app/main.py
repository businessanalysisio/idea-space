from fastapi import FastAPI

app = FastAPI(title="Idea Space")


@app.get("/health")
def health_check():
    return {"status": "ok"}
