"""Keep directly opened uploads outside the application's authenticated origin."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class UploadIsolationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/upload/file/"):
            await self.app(scope, receive, send)
            return

        async def send_isolated(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": list(message.get("headers", []))}
                headers = MutableHeaders(raw=message["headers"])
                # HTTP sandbox also covers top-level navigation and MIME-sniffed documents.
                headers["Content-Security-Policy"] = (
                    "sandbox allow-scripts allow-popups allow-forms allow-modals allow-downloads"
                )
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self.app(scope, receive, send_isolated)
