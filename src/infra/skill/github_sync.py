"""
GitHub repository sync service for skills

Fetches skills from GitHub repositories and prepares them for installation.
"""

import re
from typing import Any, Optional

import aiohttp

from src.kernel.schemas.skill import GitHubPreviewResponse, GitHubSkillPreview


class GitHubSyncService:
    """
    Service for syncing skills from GitHub repositories.

    Supports two repository structures:
    1. Manifest-based: skills.json file listing skills
    2. Auto-discovery: Scan for SKILL.md files in subdirectories
    """

    GITHUB_API_BASE = "https://api.github.com"
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize GitHub sync service.

        Args:
            github_token: Optional GitHub personal access token for higher rate limits
        """
        self.github_token = github_token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"

    def _parse_repo_url(self, repo_url: str) -> tuple[str, str]:
        """
        Parse GitHub repository URL to extract owner and repo name.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/owner/repo)

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            ValueError: If URL is not a valid GitHub repository URL
        """
        # Handle various GitHub URL formats
        patterns = [
            r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$",
            r"github\.com/([^/]+)/([^/]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, repo_url)
            if match:
                owner = match.group(1)
                repo = match.group(2).replace(".git", "")
                return owner, repo

        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    async def _fetch_json(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[dict[str, Any]]:
        """Fetch JSON from URL"""
        try:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception:
            return None

    async def _fetch_text(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch text content from URL"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception:
            return None

    async def _fetch_directory_contents(
        self, session: aiohttp.ClientSession, owner: str, repo: str, path: str = ""
    ) -> list[dict[str, Any]]:
        """Fetch directory contents from GitHub API"""
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        result = await self._fetch_json(session, url)
        if isinstance(result, list):
            return result
        return []

    def _parse_skill_md(self, content: str) -> dict[str, Any]:
        """
        Parse SKILL.md content to extract metadata.

        Extracts:
        - name: From YAML frontmatter (name field) or falls back to first heading
        - description: From YAML frontmatter (description field) or first paragraph
        - content: Full SKILL.md content

        Args:
            content: Raw SKILL.md content

        Returns:
            Dict with name, description, and content
        """
        name = ""
        description = ""

        # Parse YAML frontmatter
        if content.startswith("---"):
            # Handle cases where frontmatter starts with "---" but has no closing "---"
            # or has multiple "---" at the start (empty frontmatter)
            content_for_parse = content[3:].strip()
            if content_for_parse.startswith("---"):
                # Skip the empty first frontmatter
                content_for_parse = content_for_parse[3:].strip()

            # Find the closing ---
            if "---" in content_for_parse:
                parts = content_for_parse.split("---", 1)
                frontmatter = parts[0].strip()
                content_body = parts[1].strip() if len(parts) > 1 else ""
            else:
                # No closing ---, treat all as frontmatter
                frontmatter = content_for_parse
                content_body = ""

            # Simple YAML parsing for common fields
            for line in frontmatter.split("\n"):
                line = line.strip()
                if line.startswith("name:"):
                    name = line[5:].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    # Handle YAML multiline strings (|) and regular values
                    desc_value = line[12:].strip()
                    if desc_value.endswith("|"):
                        # Multiline string - need to get following lines
                        pass  # Will use fallback to get description
                    else:
                        description = desc_value.strip('"').strip("'")

            # If description is still empty but we have multiline, try to extract
            if not description:
                # Try to get description from lines after "description:|"
                for i, line in enumerate(frontmatter.split("\n")):
                    if line.strip().startswith("description: |"):
                        # Get subsequent non-empty lines
                        lines = frontmatter.split("\n")
                        desc_lines = []
                        for j in range(i + 1, len(lines)):
                            next_line = lines[j]
                            if next_line.startswith(" ") or next_line.startswith("\t"):
                                desc_lines.append(next_line.strip())
                            else:
                                break
                        if desc_lines:
                            description = " ".join(desc_lines)
                        break
        else:
            content_body = content

        # Fallback: extract name from first heading
        if not name:
            heading_match = re.search(r"^#\s+(.+)$", content_body, re.MULTILINE)
            if heading_match:
                name = heading_match.group(1).strip()

        # Fallback: extract description from first paragraph
        if not description:
            # Remove headings and get first non-empty paragraph
            lines = content_body.split("\n")
            paragraph_lines = []
            in_paragraph = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    if in_paragraph:
                        break
                    continue
                if stripped:
                    paragraph_lines.append(stripped)
                    in_paragraph = True
                elif in_paragraph:
                    break
            if paragraph_lines:
                description = " ".join(paragraph_lines)[:200]

        return {
            "name": name,
            "description": description,
            "content": content,  # Return full content including frontmatter
        }

    async def fetch_skills_from_repo(
        self, repo_url: str, branch: str = "main"
    ) -> GitHubPreviewResponse:
        """
        Fetch skills from a GitHub repository.

        First tries to read skills.json manifest, then falls back to auto-discovery.

        Args:
            repo_url: GitHub repository URL
            branch: Branch name (default: main)

        Returns:
            GitHubPreviewResponse with repo_url and list of skills found
        """
        owner, repo = self._parse_repo_url(repo_url)
        skills = []

        async with aiohttp.ClientSession() as session:
            # Try to fetch skills.json manifest
            manifest_url = f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/skills.json"
            manifest = await self._fetch_json(session, manifest_url)

            if manifest and "skills" in manifest:
                # Use manifest to fetch skills
                for skill_entry in manifest["skills"]:
                    skill_path = skill_entry.get("path", "")
                    if not skill_path:
                        continue

                    skill_md_url = (
                        f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/{skill_path}/SKILL.md"
                    )
                    content = await self._fetch_text(session, skill_md_url)
                    if content:
                        parsed = self._parse_skill_md(content)
                        # Fetch files for this skill
                        files = await self._fetch_directory_files(
                            session, owner, repo, skill_path, branch
                        )
                        skills.append(
                            GitHubSkillPreview(
                                name=parsed["name"] or skill_path,
                                description=parsed["description"],
                                path=skill_path,
                                files=list(files.keys()),
                            )
                        )
            else:
                # Auto-discover: check root SKILL.md first, then scan directories
                root_skill_url = f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/SKILL.md"
                root_content = await self._fetch_text(session, root_skill_url)
                if root_content:
                    parsed = self._parse_skill_md(root_content)
                    # Fetch all files from root subdirectories
                    root_files = {}
                    root_contents = await self._fetch_directory_contents(session, owner, repo)
                    for item in root_contents:
                        if item.get("type") == "dir":
                            subdir = item.get("name", "")
                            if not subdir.startswith(".") and subdir not in [".git"]:
                                subdir_files = await self._fetch_directory_files(
                                    session, owner, repo, subdir, branch
                                )
                                root_files.update(subdir_files)
                    skills.append(
                        GitHubSkillPreview(
                            name=parsed["name"] or repo,
                            description=parsed["description"],
                            path="",
                            files=list(root_files.keys()),
                        )
                    )

                # Scan subdirectories for SKILL.md
                contents = await self._fetch_directory_contents(session, owner, repo)

                for item in contents:
                    if item.get("type") == "dir":
                        dir_name = item.get("name", "")
                        skill_md_url = (
                            f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/{dir_name}/SKILL.md"
                        )
                        content = await self._fetch_text(session, skill_md_url)
                        if content:
                            parsed = self._parse_skill_md(content)
                            # Fetch files for this skill
                            files = await self._fetch_directory_files(
                                session, owner, repo, dir_name, branch
                            )
                            skills.append(
                                GitHubSkillPreview(
                                    name=parsed["name"] or dir_name,
                                    description=parsed["description"],
                                    path=dir_name,
                                    files=list(files.keys()),
                                )
                            )

        return GitHubPreviewResponse(repo_url=repo_url, skills=skills)

    async def fetch_skill_content(
        self, repo_url: str, skill_path: str, branch: str = "main"
    ) -> Optional[dict[str, Any]]:
        """
        Fetch full content of a specific skill from repository.

        Args:
            repo_url: GitHub repository URL
            skill_path: Path to skill directory (empty for root)
            branch: Branch name (default: main)

        Returns:
            Dict with name, description, content, files, and version, or None if not found
        """
        owner, repo = self._parse_repo_url(repo_url)

        async with aiohttp.ClientSession() as session:
            skill_md_url = f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/{skill_path}/SKILL.md"
            content = await self._fetch_text(session, skill_md_url)

            if content:
                parsed = self._parse_skill_md(content)

                # Fetch all files in the skill directory
                files = {}
                if skill_path:
                    # Fetch all files in the skill subdirectory
                    files = await self._fetch_directory_files(
                        session, owner, repo, skill_path, branch
                    )
                else:
                    # For root skill, fetch SKILL.md and all subdirectories
                    files["SKILL.md"] = content
                    # Fetch root directory contents to find all subdirectories
                    root_contents = await self._fetch_directory_contents(session, owner, repo)
                    for item in root_contents:
                        if item.get("type") == "dir":
                            subdir = item.get("name", "")
                            # Skip hidden directories and common non-content dirs
                            if not subdir.startswith(".") and subdir not in [".git"]:
                                subdir_files = await self._fetch_directory_files(
                                    session, owner, repo, subdir, branch
                                )
                                files.update(subdir_files)

                return {
                    "name": parsed["name"] or skill_path or repo,
                    "description": parsed["description"],
                    "content": content,
                    "files": files,
                    "version": None,  # Could be extracted from tags/commits if needed
                }

        return None

    async def _fetch_directory_files(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> dict[str, str]:
        """Fetch all files from a directory recursively"""
        files: dict[str, str] = {}
        try:
            contents_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
            contents = await self._fetch_json(session, contents_url)
            if isinstance(contents, list):
                for item in contents:
                    if item.get("type") == "file":
                        file_name = item.get("name", "")
                        # Only fetch markdown and text files
                        if file_name.endswith((".md", ".txt", ".py", ".yml", ".yaml", ".json")):
                            file_content = await self._fetch_text(session, item.get("download_url"))
                            if file_content:
                                files[f"{path}/{file_name}"] = file_content
                    elif item.get("type") == "dir":
                        # Recursively fetch subdirectory
                        subdir = item.get("name", "")
                        subdir_files = await self._fetch_directory_files(
                            session, owner, repo, f"{path}/{subdir}", branch
                        )
                        files.update(subdir_files)
        except Exception:
            pass
        return files

    async def fetch_all_skill_contents(
        self, repo_url: str, skill_paths: list[str], branch: str = "main"
    ) -> list[dict[str, Any]]:
        """
        Fetch full contents of multiple skills from repository.

        Args:
            repo_url: GitHub repository URL
            skill_paths: List of skill directory paths
            branch: Branch name (default: main)

        Returns:
            List of dicts with skill data
        """
        results = []
        for path in skill_paths:
            skill_data = await self.fetch_skill_content(repo_url, path, branch)
            if skill_data:
                results.append(skill_data)
        return results
