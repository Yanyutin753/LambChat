"""Old direct streams no longer own an independent execution/heartbeat path."""

from src.api.routes import agent as agent_routes


def test_direct_agent_stream_has_no_public_route():
    paths = {route.path for route in agent_routes.router.routes}
    assert "/{agent_id}/stream" not in paths
    assert "/{agent_id}/chat" not in paths
