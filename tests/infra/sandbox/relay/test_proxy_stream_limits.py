"""Keep large authenticated binary streams out of the proxy's generic body cap."""

import re
from pathlib import Path


def test_sandbox_only_lifts_proxy_body_limit_for_bounded_binary_result_stream():
    config = (Path(__file__).resolve().parents[4] / "nginx/nginx.conf").read_text()
    sandbox = config.split("location /api/sandbox/ {", 1)[1].split("\n}", 1)[0]
    stream = re.search(
        r"location /api/sandbox/results/stream/ \{\s*proxy_pass http://backend;\s*client_max_body_size 0;\s*\}",
        sandbox,
    )
    assert stream is not None, "large binary streams must reach the app's bounded reader"
    assert "client_max_body_size 0;" not in sandbox.replace(stream.group(), "")
    assert "proxy_request_buffering off;" in sandbox
    assert "proxy_pass http://backend;" in sandbox
