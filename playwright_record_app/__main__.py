import os
import uvicorn
from fastapi import FastAPI
from .routes import build_routes

app = FastAPI()
app.mount("/api/apps/playwright-record", build_routes())

def main():
    uvicorn.run(app, host=os.environ.get("AW_APP_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "9414")))

if __name__ == "__main__":
    main()
