from fastapi import FastAPI

app = FastAPI(title="ScriptWhisper API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
