"""
Skill storage constants
"""

# Redis cache TTL (seconds), default 30 minutes
SKILLS_CACHE_TTL = 1800
MCP_TOOLS_METADATA_CACHE_TTL = 1800

# Redis cache key prefixes
SKILLS_CACHE_KEY_PREFIX = "user_skills:"
MCP_TOOLS_METADATA_KEY_PREFIX = "mcp_tools_metadata:"
