#!/usr/bin/env python3
"""
Production entrypoint for Resume Builder Pro.

Wraps the Gradio Blocks app in a FastAPI server so we can expose a `/health`
endpoint, apply optional basic auth, and serve under a single uvicorn process.

Usage:
  python app.py            # start server
  APP_USERNAME=u APP_PASSWORD=p python app.py   # enable basic auth

Local dev without uvicorn: `python web_ui.py`.
"""

import logging

import gradio as gr
import uvicorn
from fastapi import FastAPI

import config
from web_ui import demo  # builds the Blocks demo (import-time side effect)

APP_VERSION = "4.0.0"


def setup_logging() -> None:
    """Configure console logging from LOG_LEVEL."""
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def build_app() -> FastAPI:
    """Build the FastAPI app: /health + mounted Gradio UI (optional auth)."""
    log = logging.getLogger(__name__)
    fastapi_app = FastAPI(title="Resume Builder Pro", version=APP_VERSION)

    @fastapi_app.get("/health")
    def health() -> dict:
        return {"status": "ok", "app": "resume-builder", "version": APP_VERSION}

    auth = None
    if config.auth_enabled():
        auth = (config.auth_user(), config.auth_password())
        log.info("Basic auth ENABLED for user: %s", config.auth_user())

    mounted = gr.mount_gradio_app(
        fastapi_app,
        demo,
        path="/",
        server_name=config.HOST,
        server_port=config.PORT,
        auth=auth,
        auth_message="Resume Builder Pro requires login.",
    )
    return mounted


def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)
    app = build_app()
    log.info(
        "Serving Resume Builder Pro on http://%s:%s (auth=%s)",
        config.HOST,
        config.PORT,
        config.auth_enabled(),
    )
    uvicorn.run(
        app, host=config.HOST, port=config.PORT, log_level=config.LOG_LEVEL.lower()
    )


if __name__ == "__main__":
    main()
