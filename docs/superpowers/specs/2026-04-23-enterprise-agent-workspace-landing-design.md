# LambChat Enterprise Agent Workspace Landing Design

## Goal

Reposition the landing page from a generic "production-ready AI Agent system" to a sharper enterprise product story:

LambChat is a self-hosted AI Agent workspace for teams. AI platform teams use it to govern models, MCP servers, Skills, permissions, sandboxes, and channels. Business teams use it from the web UI or Feishu/Lark to produce reports, presentations, analysis, and workflow automation.

## Audience

Primary buyer and operator:

- Enterprise AI platform teams
- Internal platform engineers
- Teams responsible for model access, tool governance, security, and deployment

Primary end user:

- Business teams that need AI-assisted deliverables and internal workflow automation
- Teams using web chat, documents, and Feishu/Lark channels

## Positioning

Recommended line:

> Self-hosted AI Agent workspace for enterprise teams.

Chinese version:

> 面向企业团队的自托管 AI Agent 工作台。

Supporting message:

> Govern models, MCP tools, Skills, permissions, and channels in one place, while business teams deliver reports, presentations, analysis, and workflow automation from web and Feishu/Lark.

Chinese version:

> 统一治理模型、MCP 工具、Skills、权限和企业渠道，让业务团队在网页与飞书/Lark 中交付报告、演示、分析和自动化流程。

## Landing Narrative

Keep the existing landing structure and rewrite the story around two connected themes:

1. Platform governance
   Model management, MCP access control, Skills lifecycle, RBAC, sandbox execution, feedback, tracing, and settings.

2. Business delivery
   Chat-based work, files and documents, report/PPT/data analysis workflows, session sharing, and Feishu/Lark integration.

This avoids competing directly with Claude Code, Cursor, or Codex as a coding tool. LambChat should read as an internal Agent platform and workspace that can complement those tools.

## Section Design

### Hero

Purpose:

Make the product category clear within the first viewport.

Content direction:

- Badge: "Self-hosted AI Agent Workspace"
- H1: "LambChat"
- Description: "Deploy a private AI Agent workspace for your enterprise. Govern models, MCP tools, Skills, permissions, and channels, while business teams deliver reports, presentations, analysis, and workflow automation from web and Feishu/Lark."
- CTA labels can stay close to the current wording: "Start Using" and "View on GitHub"
- Tech stack chips should signal product value, not only implementation: "Model Governance", "MCP Control", "Skills", "RBAC", "Sandbox", "Feishu/Lark"

### Interface Section

Purpose:

Describe the main UI as the business team's unified Agent entry point.

Content direction:

- Title: "Workspace for business delivery"
- Description: "A web workspace for streaming Agent work, rich documents, files, shared sessions, and reusable workflows."

### Features Section

Purpose:

Convert the feature grid from a generic checklist into a governance and delivery map.

Content direction:

- Agent Orchestration: multi-agent execution and task handoff
- Model Governance: providers, routing, visibility, defaults, fallback
- MCP Control: system and user servers, encrypted secrets, transport and tool permissions
- Skills Marketplace: reusable internal workflows, GitHub sync, authoring, batch operations
- Feedback Loop: capture quality signals tied to sessions and runs
- Document Workspace: PDF, Word, Excel, PPT, Markdown, Mermaid, image preview, cloud storage
- Realtime Work: Redis/MongoDB dual-write, WebSocket, resumable sessions
- Security & RBAC: JWT, role permissions, OAuth, verification, sandbox boundaries
- Task Operations: cancellation, heartbeat, concurrency, notifications
- Enterprise Channels: Feishu/Lark and extensible channels
- Observability: tracing, logs, health checks
- Frontend Experience: responsive, multilingual, dark/light UI

### Architecture Section

Purpose:

Give platform teams confidence that this can be deployed and extended internally.

Content direction:

- Self-hosted FastAPI + React architecture
- LangGraph/deepagents execution
- Redis/MongoDB persistence and realtime events
- Sandbox backends for isolated execution
- MCP, Skills, memory, and provider adapters as extension layers

### Dashboard Section

Purpose:

Show that administrators can operate the platform after deployment.

Content direction:

- Unified control plane for Agents, models, Skills, MCP servers, roles, feedback, settings, and shared sessions
- Emphasize that platform teams can manage access and capabilities centrally

### Responsive Section

Purpose:

Keep this section, but frame it as "same workspace across devices" rather than generic responsive design.

Content direction:

- Web, tablet, and mobile access for teams
- Useful for reviewing shared sessions and approving or monitoring work

### CTA

Purpose:

Close with deployment and team adoption.

Content direction:

- Title: "Deploy your enterprise Agent workspace"
- Description: "Connect your models, MCP servers, Skills, and enterprise channels, then give teams a governed place to use AI in daily work."

## Implementation Scope

Initial implementation should stay intentionally small:

- Update `frontend/src/i18n/locales/zh.json`
- Update `frontend/src/i18n/locales/en.json`
- Optionally update `frontend/src/components/landing/data.ts` if tech stack chips should become value chips
- Avoid layout or CSS changes unless text wrapping breaks the current design
- Do not change backend behavior

## Testing

After implementation:

- Run frontend type/lint checks if available
- Start the frontend or full dev server
- Capture the landing page in desktop and mobile widths
- Verify hero text wraps cleanly and does not overlap CTAs or tech/value chips
- Verify English and Chinese landing pages read naturally

## Open Decisions

- Whether to keep `TECH_STACK` as technical stack labels or rename it conceptually to value signals.
- Whether to update Japanese, Korean, and Russian landing copy now or let them temporarily fall back to existing generic positioning.
- Whether homepage screenshots should be reordered later to put admin governance panels before general chat screenshots.
