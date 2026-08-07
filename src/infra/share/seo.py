from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

DEFAULT_SHARE_ROBOTS = "noindex, follow, max-image-preview:large"
INDEX_ROBOTS = "index, follow, max-image-preview:large"
NOINDEX_ROBOTS = "noindex, follow, max-image-preview:large"
DEFAULT_SHARE_PREVIEW_LABEL = "Shared session preview"
DEFAULT_SHARE_DESCRIPTION = "View this shared session on LambChat."
DEFAULT_SHARE_PROJECT_PREVIEW_LABEL = "Shared project preview"
PUBLIC_HOME_PATH = "/"
CRAWLER_ROBOTS_META_NAMES = (
    "googlebot",
    "bingbot",
    "Baiduspider",
    "360Spider",
    "Sogou web spider",
    "YisouSpider",
    "Bytespider",
)

_WHITESPACE_RE = re.compile(r"\s+")
_ROOT_DIV_RE = re.compile(r'<div id="root"></div>')
_SHARED_PREVIEW_RE = re.compile(
    r'(<div id="shared-server-preview">.*?</div>\s*)?<div id="root"></div>', re.S
)


@dataclass(frozen=True)
class SharedPageSeo:
    title: str
    description: str
    canonical_url: str
    robots: str
    og_type: str
    preview_label: str
    preview_title: str
    preview_summary: str
    author_name: str
    published_date: str


@dataclass(frozen=True)
class PublicRouteSeo:
    title: str
    description: str
    canonical_url: str
    robots: str
    og_type: str
    preview_html: str


@dataclass(frozen=True)
class PublicLandingRoute:
    title: str
    description: str
    eyebrow: str
    heading: str
    bullets: tuple[str, ...]


PUBLIC_LANDING_ROUTES: dict[str, PublicLandingRoute] = {
    "/": PublicLandingRoute(
        title="LambChat - AI Agent Platform | Multi-Model Chat & Skill Engine",
        description="LambChat is a pluggable, multi-tenant AI conversation platform for teams building multi-model agents with Skills, MCP tools, streaming chat, document processing, and role-based access.",
        eyebrow="AI agent workspace",
        heading="LambChat AI Agent Platform",
        bullets=(
            "Multi-model AI chat for Claude, GPT, Gemini, and other LLM providers.",
            "Skills engine and Model Context Protocol integrations for extensible agent workflows.",
            "Real-time streaming conversations, document processing, and team-ready access control.",
        ),
    ),
    "/interface": PublicLandingRoute(
        title="LambChat Interface - AI Agent Workspace",
        description="Explore the LambChat interface for streaming chat, file-aware conversations, shared sessions, and team-ready AI agent workflows.",
        eyebrow="Main interface",
        heading="LambChat AI Agent Workspace",
        bullets=(
            "Streaming conversations with multi-model AI agents.",
            "Document and image workflows built into the chat surface.",
            "Shareable sessions and responsive workspace layouts.",
        ),
    ),
    "/features": PublicLandingRoute(
        title="LambChat Core Features - AI Agent Platform",
        description="LambChat core features include Skills, MCP tools, role-based access, multi-agent orchestration, document processing, feedback, and observability.",
        eyebrow="Core features",
        heading="LambChat Core Features",
        bullets=(
            "Skills engine for reusable AI capabilities and prompt workflows.",
            "MCP tools for connecting external systems, services, and data.",
            "Role-based access, teams, feedback, notifications, and observability.",
        ),
    ),
    "/architecture": PublicLandingRoute(
        title="LambChat Architecture - Skills and MCP Dual Engine",
        description="LambChat architecture combines a Skills engine, MCP integrations, streaming sessions, sandboxed tools, and multi-tenant access control.",
        eyebrow="Architecture",
        heading="Skills and MCP Dual Engine",
        bullets=(
            "Composable agent workflows backed by Skills and MCP servers.",
            "Real-time SSE streaming with durable session and task handling.",
            "Sandboxed tool execution, storage services, and access boundaries.",
        ),
    ),
    "/dashboard": PublicLandingRoute(
        title="LambChat Management Panels - Agents, Skills, Models and Teams",
        description="Manage LambChat agents, models, Skills, MCP servers, channels, files, teams, users, roles, memory, and notifications from one workspace.",
        eyebrow="Management panels",
        heading="Agents, Skills, Models and Teams",
        bullets=(
            "Configure agents, model providers, MCP servers, and channels.",
            "Manage Skills, marketplace content, files, memory, and personas.",
            "Administer users, roles, teams, notifications, and system settings.",
        ),
    ),
    "/responsive": PublicLandingRoute(
        title="LambChat Responsive Design - Desktop, Tablet and Mobile AI Workspace",
        description="LambChat provides a responsive AI workspace for desktop, tablet, and mobile usage with adaptive chat, panels, and navigation.",
        eyebrow="Responsive design",
        heading="Desktop, Tablet and Mobile Workspace",
        bullets=(
            "Adaptive navigation and panels across desktop and mobile screens.",
            "Touch-friendly chat, file, and management workflows.",
            "PWA-ready shell with offline status and install metadata.",
        ),
    ),
    "/github": PublicLandingRoute(
        title="LambChat GitHub - Open Source AI Agent Platform",
        description="Explore LambChat on GitHub, the open source AI agent platform for multi-model chat, Skills, MCP integrations, and team workflows.",
        eyebrow="Open source",
        heading="LambChat on GitHub",
        bullets=(
            "Review the open source codebase and deployment assets.",
            "Track LambChat features, issues, and release updates.",
            "Contribute to the AI agent platform and integration ecosystem.",
        ),
    ),
}

PUBLIC_NAVIGATION_ITEMS: tuple[tuple[str, str], ...] = (
    ("Features", "/features"),
    ("Architecture", "/architecture"),
    ("Management Panels", "/dashboard"),
    ("Responsive Design", "/responsive"),
    ("GitHub", "/github"),
)


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    clipped = value[: max_length + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if not clipped:
        clipped = value[:max_length]
    return f"{clipped}..."


def _extract_preview_lines(events: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    first_user = ""
    first_assistant = ""

    for event in events:
        event_type = event.get("event_type", "")
        data = event.get("data") or {}
        content = _normalize_text(data.get("content"))
        if not content:
            continue

        if event_type == "user:message" and not first_user:
            first_user = content
            continue

        if event_type in {"message:chunk", "assistant:message"} and not first_assistant:
            first_assistant = content

        if first_user and first_assistant:
            break

    return first_user, first_assistant


def _format_date(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def build_shared_page_seo(
    *,
    base_url: str,
    share_id: str,
    session: Mapping[str, Any],
    owner: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
    app_name: str = "LambChat",
    indexable: bool = False,
) -> SharedPageSeo:
    first_user, first_assistant = _extract_preview_lines(events)

    raw_title = _normalize_text(session.get("name")) or _truncate_text(
        first_user or "Shared session",
        60,
    )
    preview_title = raw_title or "Shared session"
    title = f"{preview_title} - {app_name} Shared Session"

    description_parts = [
        _truncate_text(first_user, 140) if first_user else "",
        _truncate_text(first_assistant, 140) if first_assistant else "",
    ]
    description = " ".join(part for part in description_parts if part).strip()
    if not description:
        description = DEFAULT_SHARE_DESCRIPTION

    summary = description
    if summary == DEFAULT_SHARE_DESCRIPTION and _normalize_text(session.get("agent_name")):
        summary = f"{summary} Agent: {_normalize_text(session.get('agent_name'))}."

    robots = "index, follow, max-image-preview:large" if indexable else DEFAULT_SHARE_ROBOTS
    canonical_url = f"{base_url.rstrip('/')}/shared/{share_id}"

    return SharedPageSeo(
        title=title,
        description=description,
        canonical_url=canonical_url,
        robots=robots,
        og_type="article",
        preview_label=DEFAULT_SHARE_PREVIEW_LABEL,
        preview_title=preview_title,
        preview_summary=summary,
        author_name=_normalize_text((owner or {}).get("username")),
        published_date=_format_date(session.get("created_at")),
    )


def build_shared_project_seo(
    *,
    base_url: str,
    share_id: str,
    project: Any,
    sessions: Sequence[Any],
    owner: Mapping[str, Any] | None,
    app_name: str = "LambChat",
    indexable: bool = False,
) -> SharedPageSeo:
    """Build SEO metadata for a shared project (scope=project).

    Returns the same ``SharedPageSeo`` shape as session shares so the existing
    HTML injection works unchanged.
    """
    project_name = _normalize_text(
        project.get("name") if isinstance(project, dict) else getattr(project, "name", "")
    )
    session_count = len(sessions) if sessions is not None else 0

    preview_title = project_name or "Shared project"
    title = f"{preview_title} - {app_name} Shared Project"

    if session_count:
        description = (
            f"Shared project '{preview_title}' with {session_count} conversation(s) on {app_name}."
        )
    else:
        description = f"Shared project '{preview_title}' on {app_name}."

    robots = "index, follow, max-image-preview:large" if indexable else DEFAULT_SHARE_ROBOTS
    canonical_url = f"{base_url.rstrip('/')}/shared/{share_id}"

    return SharedPageSeo(
        title=title,
        description=description,
        canonical_url=canonical_url,
        robots=robots,
        og_type="article",
        preview_label=DEFAULT_SHARE_PROJECT_PREVIEW_LABEL,
        preview_title=preview_title,
        preview_summary=description,
        author_name=_normalize_text((owner or {}).get("username")),
        published_date="",
    )


def build_shared_page_error_seo(
    *,
    base_url: str,
    share_id: str,
    app_name: str = "LambChat",
    reason: str,
) -> SharedPageSeo:
    messages = {
        "not_found": (
            "Shared session not found",
            "This shared session was not found or is no longer available.",
        ),
        "auth_required": (
            "Login required for shared session",
            "Sign in to view this shared session.",
        ),
    }
    preview_title, description = messages.get(
        reason,
        ("Shared session unavailable", "This shared session is currently unavailable."),
    )

    return SharedPageSeo(
        title=f"{preview_title} - {app_name}",
        description=description,
        canonical_url=f"{base_url.rstrip('/')}/shared/{share_id}",
        robots=DEFAULT_SHARE_ROBOTS,
        og_type="article",
        preview_label=DEFAULT_SHARE_PREVIEW_LABEL,
        preview_title=preview_title,
        preview_summary=description,
        author_name="",
        published_date="",
    )


def _canonical_url(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if normalized_path == "/":
        return f"{base_url.rstrip('/')}/"
    return f"{base_url.rstrip('/')}{normalized_path}"


def _is_public_indexable_path(path: str) -> bool:
    normalized_path = PUBLIC_HOME_PATH if path == "" else path
    return normalized_path in PUBLIC_LANDING_ROUTES


def _build_public_preview_html(route: PublicLandingRoute) -> str:
    feature_items = "\n".join(f"      <li>{html.escape(feature)}</li>" for feature in route.bullets)
    nav_items = "\n".join(
        f'      <li><a href="{path}">{html.escape(label)}</a></li>'
        for label, path in PUBLIC_NAVIGATION_ITEMS
    )
    return f"""<main data-public-preview="server" style="max-width: 920px; margin: 0 auto; padding: 48px 24px; font-family: 'Source Sans 3', Arial, sans-serif; color: #1c1917; background: #faf9f7;">
    <p style="margin: 0 0 12px; font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; color: #78716c;">{html.escape(route.eyebrow)}</p>
    <h1>{html.escape(route.heading)}</h1>
    <p style="font-size: 18px; line-height: 1.7; color: #44403c;">{html.escape(route.description)}</p>
    <ul style="font-size: 16px; line-height: 1.8; color: #44403c;">
{feature_items}
    </ul>
    <nav aria-label="LambChat public sections">
      <ul style="font-size: 15px; line-height: 1.8; color: #44403c;">
{nav_items}
      </ul>
    </nav>
  </main>"""


def _public_route_structured_data(seo: PublicRouteSeo) -> str:
    origin_match = re.match(r"^(https?://[^/]+)", seo.canonical_url)
    origin = origin_match.group(1) if origin_match else seo.canonical_url.rstrip("/")

    navigation = [
        {
            "@type": "SiteNavigationElement",
            "name": label,
            "url": _canonical_url(origin, path),
        }
        for label, path in PUBLIC_NAVIGATION_ITEMS
    ]
    breadcrumb_items = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": _canonical_url(origin, "/"),
        }
    ]
    if seo.canonical_url.rstrip("/") != _canonical_url(origin, "/").rstrip("/"):
        breadcrumb_items.append(
            {
                "@type": "ListItem",
                "position": 2,
                "name": seo.title.split(" - ", 1)[0].removeprefix("LambChat "),
                "item": seo.canonical_url,
            }
        )

    data = [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "LambChat",
            "url": _canonical_url(origin, "/"),
            "hasPart": navigation,
        },
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": "LambChat",
            "applicationCategory": "ChatApplication",
            "operatingSystem": "Web",
            "url": _canonical_url(origin, "/"),
            "description": PUBLIC_LANDING_ROUTES[PUBLIC_HOME_PATH].description,
            "codeRepository": "https://github.com/Yanyutin753/LambChat",
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items,
        },
    ]
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_public_route_seo(*, base_url: str, path: str) -> PublicRouteSeo:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if normalized_path == "":
        normalized_path = PUBLIC_HOME_PATH

    landing_route = PUBLIC_LANDING_ROUTES.get(normalized_path)
    is_public_landing = landing_route is not None
    title = landing_route.title if landing_route else "LambChat"
    description = landing_route.description if landing_route else "LambChat application route."

    return PublicRouteSeo(
        title=title,
        description=description,
        canonical_url=_canonical_url(base_url, normalized_path),
        robots=INDEX_ROBOTS if is_public_landing else NOINDEX_ROBOTS,
        og_type="website",
        preview_html=_build_public_preview_html(landing_route) if landing_route else "",
    )


def _replace_title(html_doc: str, value: str) -> str:
    replacement = f"<title>{html.escape(value, quote=True)}</title>"
    return re.sub(r"<title>.*?</title>", replacement, html_doc, count=1, flags=re.S)


def _replace_link(html_doc: str, rel: str, href: str) -> str:
    escaped_href = html.escape(href, quote=True)
    replacement = f'<link rel="{rel}" href="{escaped_href}" />'
    pattern = re.compile(rf'<link\s+rel="{re.escape(rel)}"\s+href="[^"]*"\s*/?>', re.I)
    if pattern.search(html_doc):
        return pattern.sub(replacement, html_doc, count=1)
    return html_doc.replace("</head>", f"    {replacement}\n  </head>", 1)


def _replace_meta(html_doc: str, attr: str, name: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    replacement = f'<meta {attr}="{name}" content="{escaped}" />'
    pattern = re.compile(
        rf'<meta\s+[^>]*{attr}="{re.escape(name)}"[^>]*content="[^"]*"[^>]*>',
        re.I,
    )
    if pattern.search(html_doc):
        return pattern.sub(replacement, html_doc, count=1)
    return html_doc.replace("</head>", f"    {replacement}\n  </head>", 1)


def _replace_crawler_robots_meta(html_doc: str, robots: str) -> str:
    rendered = html_doc
    for crawler in CRAWLER_ROBOTS_META_NAMES:
        rendered = _replace_meta(rendered, "name", crawler, robots)
    return rendered


def inject_share_seo_into_html(html_doc: str, seo: SharedPageSeo) -> str:
    rendered = html_doc
    rendered = _replace_title(rendered, seo.title)
    rendered = _replace_link(rendered, "canonical", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "description", seo.description)
    rendered = _replace_meta(rendered, "name", "robots", seo.robots)
    rendered = _replace_crawler_robots_meta(rendered, seo.robots)
    rendered = _replace_meta(rendered, "property", "og:type", seo.og_type)
    rendered = _replace_meta(rendered, "property", "og:title", seo.title)
    rendered = _replace_meta(rendered, "property", "og:description", seo.description)
    rendered = _replace_meta(rendered, "property", "og:url", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "twitter:title", seo.title)
    rendered = _replace_meta(rendered, "name", "twitter:description", seo.description)
    rendered = _replace_meta(rendered, "property", "og:image:alt", seo.preview_title)
    rendered = _replace_meta(rendered, "name", "twitter:image:alt", seo.preview_title)

    byline_parts = [part for part in [seo.author_name, seo.published_date] if part]
    byline = " · ".join(byline_parts)
    summary_html = html.escape(seo.preview_summary, quote=True)
    byline_html = html.escape(byline, quote=True)

    preview_markup = f"""<div id="shared-server-preview">
  <main data-shared-preview="server" style="max-width: 760px; margin: 0 auto; padding: 48px 24px; font-family: 'Source Sans 3', sans-serif; color: #1c1917; background: #faf9f7; min-height: 100vh;">
    <p style="margin: 0 0 12px; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: #78716c;">{html.escape(seo.preview_label, quote=True)}</p>
    <h1 style="margin: 0 0 16px; font-size: 40px; line-height: 1.15; color: #1c1917;">{html.escape(seo.preview_title, quote=True)}</h1>
    <p style="margin: 0 0 16px; font-size: 18px; line-height: 1.7; color: #44403c;">{summary_html}</p>
    <p style="margin: 0; font-size: 14px; color: #78716c;">{byline_html}</p>
  </main>
</div>"""

    replacement = f'{preview_markup}\n<div id="root"></div>'
    if _SHARED_PREVIEW_RE.search(rendered):
        return _SHARED_PREVIEW_RE.sub(replacement, rendered, count=1)
    if _ROOT_DIV_RE.search(rendered):
        return _ROOT_DIV_RE.sub(replacement, rendered, count=1)
    return rendered


def inject_public_route_seo_into_html(html_doc: str, seo: PublicRouteSeo) -> str:
    rendered = html_doc
    rendered = _replace_title(rendered, seo.title)
    rendered = _replace_link(rendered, "canonical", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "description", seo.description)
    rendered = _replace_meta(rendered, "name", "robots", seo.robots)
    rendered = _replace_crawler_robots_meta(rendered, seo.robots)
    rendered = _replace_meta(rendered, "property", "og:type", seo.og_type)
    rendered = _replace_meta(rendered, "property", "og:title", seo.title)
    rendered = _replace_meta(rendered, "property", "og:description", seo.description)
    rendered = _replace_meta(rendered, "property", "og:url", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "twitter:title", seo.title)
    rendered = _replace_meta(rendered, "name", "twitter:description", seo.description)
    if seo.robots == INDEX_ROBOTS:
        structured_data = _public_route_structured_data(seo)
        script = f'<script type="application/ld+json">\n{structured_data}\n</script>'
        rendered = rendered.replace("</head>", f"    {script}\n  </head>", 1)

    if not seo.preview_html:
        return rendered

    replacement = f'<div id="root">\n  {seo.preview_html}\n</div>'
    if _ROOT_DIV_RE.search(rendered):
        return _ROOT_DIV_RE.sub(replacement, rendered, count=1)
    return rendered
