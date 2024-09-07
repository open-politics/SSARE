from fastapi import FastAPI
from contextlib import asynccontextmanager
import prefect
# from prefect import flow, task


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run before the application starts
    print("Starting up the application...")
    yield
    # Shutdown: Run when the application is shutting down
    print("Shutting down the application...")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/healthcheck")
async def healthcheck():
    return {"status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)