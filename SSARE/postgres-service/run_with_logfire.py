import logfire

# Configure Logfire and set up auto-tracing
logfire.configure()
logfire.install_auto_tracing(modules=['app'], min_duration=0.01)

# Use uvicorn to run the FastAPI app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5434)