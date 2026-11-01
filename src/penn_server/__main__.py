import uvicorn

if __name__ == "__main__":
    # Exactly one process owns Chromium and durable recovery incidents.
    uvicorn.run(
        "src.penn_server.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=1,
        access_log=False,
        proxy_headers=False,
    )
