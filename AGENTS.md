# LambChat Development Guide

Use this file as the development guide for the LambChat repository. Always prioritize the user's current request; when the request does not provide special instructions, follow the project conventions below.

## Project Overview

LambChat is a full-stack AI Agent platform:

- Backend: Python 3.12+, FastAPI, LangGraph/deepagents, MongoDB, Redis, arq.
- Frontend: React 19, TypeScript, Vite, TailwindCSS, PWA.
- Clients: Capacitor mobile apps and Tauri desktop app.
- Documentation: VitePress, located in `docs/`.

Common directories:

- `src/`: Backend application code, including agent runtime, API, infra, kernel, skills, and related modules.
- `frontend/`: Web frontend plus mobile and desktop client code.
- `tests/`: Python tests.
- `deploy/`: Docker, Kubernetes, and other deployment resources.
- `docs/`: Project documentation site.

## Common Commands

Install dependencies:

```bash
make install-all
```

Start the local development environment:

```bash
make dev-all
```

Start the backend or frontend separately:

```bash
make dev
make frontend-dev
```

Build:

```bash
make build-all
make frontend-build
```

Quality checks:

```bash
make lint
make typecheck
make test
make check-all
```

Frontend-specific commands:

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

## Development Conventions

- Before editing, read the relevant existing modules and preserve the current architecture, naming, and code style.
- Use `uv` for the Python backend environment; do not mix in `pip install` for project dependencies.
- Use `pnpm` for the frontend; do not commit `node_modules/` or build artifacts.
- Python code should follow the Ruff, Mypy, and Pytest configuration in `pyproject.toml`.
- TypeScript/React code should follow `frontend/package.json` and the existing ESLint/Vite configuration.
- For user-facing copy, respect the existing internationalization structure. Do not update only one locale when that would leave the UI with missing text.
- For sensitive paths such as auth, RBAC, model keys, MCP secrets, file access, and sandbox execution, prefer conservative changes and add verification.
- Do not refactor unrelated code casually; keep the change scope close to the current task.
- Do not overwrite existing user changes. If the worktree has uncommitted changes, only touch files relevant to the current task.

## Verification Guidance

Choose the smallest effective verification based on the change scope:

- Backend logic: run the relevant `pytest` tests, and run `make test` when needed.
- Backend formatting/static checks: run `make lint` and `make typecheck`.
- Frontend components or types: run `cd frontend && pnpm run lint`, and run `cd frontend && pnpm run build` when needed.
- Cross-stack or shared behavior: prefer `make check-all` or the matching backend/frontend check combination.
- Documentation changes: confirm Markdown links, commands, and paths remain accurate.

If verification cannot be completed because services, dependencies, or environment variables are missing, state that clearly in the response.

## Local Development URLs

`make dev-all` starts:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3001`
