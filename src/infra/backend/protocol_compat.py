from __future__ import annotations

from dataclasses import dataclass

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    WriteResult,
)
from deepagents.backends.protocol import (
    ReadResult as _UpstreamReadResult,
)

# Detect whether the upstream ReadResult is a dataclass (deepagents ≥0.5)
# or the legacy str-subclass.
_UPSTREAM_IS_DATACLASS = hasattr(_UpstreamReadResult, "__dataclass_fields__")

if _UPSTREAM_IS_DATACLASS:

    @dataclass
    class ReadResult(_UpstreamReadResult):  # type: ignore[no-redef]
        """Extended ReadResult that also stores a rendered string representation.

        Compatible with the dataclass-based upstream ``ReadResult`` introduced
        in deepagents 0.5.
        """

        rendered_content: str | None = None

        def __post_init__(self) -> None:
            if self.rendered_content is None:
                if self.error is not None:
                    self.rendered_content = (
                        self.error if self.error.startswith("Error:") else f"Error: {self.error}"
                    )
                else:
                    self.rendered_content = str(
                        (self.file_data or {}).get("content", "")  # type: ignore[call-overload]
                    )

        # Allow ``str(result)`` to return the rendered content.
        def __str__(self) -> str:
            return self.rendered_content or ""

        def __contains__(self, item: str) -> bool:
            return item in str(self)

        def __iter__(self):
            return iter(str(self))

        def __len__(self) -> int:
            return len(str(self))

else:

    class ReadResult(str, _UpstreamReadResult):  # type: ignore[no-redef]
        file_data: FileData | None
        error: str | None

        def __new__(
            cls,
            *,
            file_data: FileData | None = None,
            error: str | None = None,
            rendered_content: str | None = None,
        ) -> "ReadResult":
            if rendered_content is None:
                if error is not None:
                    rendered_content = error if error.startswith("Error:") else f"Error: {error}"
                else:
                    rendered_content = str(
                        (file_data or {}).get("content", "")  # type: ignore[call-overload]
                    )

            obj = str.__new__(cls, rendered_content)
            obj.file_data = file_data
            obj.error = error
            return obj


def is_read_result(value: object) -> bool:
    """Return True for both upstream and compatibility-layer read results."""
    return isinstance(value, _UpstreamReadResult)


def read_result_to_string(value: object) -> str:
    """Render upstream or compatibility-layer read results as user-facing text."""
    if not is_read_result(value):
        return str(value)

    error = getattr(value, "error", None)
    if error:
        return error if str(error).startswith("Error:") else f"Error: {error}"

    rendered = getattr(value, "rendered_content", None)
    if rendered is not None:
        return str(rendered)

    file_data = getattr(value, "file_data", None) or {}
    return str(file_data.get("content", ""))


# Re-export upstream protocol types so that mypy treats our aliases as
# identical to the ones used in BaseSandbox / BackendProtocol signatures.
__all__ = [
    "BackendProtocol",
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileUploadResponse",
    "GlobResult",
    "GrepMatch",
    "GrepResult",
    "LsResult",
    "ReadResult",
    "WriteResult",
    "is_read_result",
    "read_result_to_string",
]
