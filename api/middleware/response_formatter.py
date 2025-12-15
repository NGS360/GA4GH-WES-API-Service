"""Response formatting middleware."""

from typing import Callable

from fastapi import FastAPI
from starlette.types import ASGIApp


class AddNewlineMiddleware:
    """Middleware to add a newline character to JSON responses."""
    def __init__(self, app: ASGIApp):
        """Initialize middleware with app."""
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """Process response and add newline if JSON."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send_with_newline(message: dict) -> None:
            if message["type"] == "http.response.body":
                if message.get("more_body", False) is False:  # Last chunk
                    # Check content type to only modify JSON responses
                    is_json = False
                    for header in headers:
                        if header[0].decode() == "content-type" and b"application/json" in header[1]:
                            is_json = True
                            break

                    if is_json and message["body"] and not message["body"].endswith(b"\n"):
                        # Add a newline at the end
                        message["body"] = message["body"] + b"\n"

                        # Update content length
                        for i, header in enumerate(headers):
                            if header[0].decode() == "content-length":
                                headers[i] = (
                                    b"content-length",
                                    str(len(message["body"])).encode()
                                )
                                break

            await original_send(message)

        # Keep track of headers for checking content type
        headers = []

        async def _receive_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                nonlocal headers
                headers = message.get("headers", [])
            await _send_with_newline(message)

        original_send = send
        await self.app(scope, receive, _receive_headers)


def add_response_formatter(app: FastAPI) -> None:
    """Add response formatting middleware to FastAPI app."""
    app.add_middleware(AddNewlineMiddleware)
