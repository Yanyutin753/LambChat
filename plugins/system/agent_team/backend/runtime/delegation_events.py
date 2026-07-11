"""Delegation event parsing and forced-stage descriptions."""

import time
from typing import Any

from plugins.system.agent_team.backend.runtime.prompt import (
    build_team_member_subagent_type,
)
from src.infra.agent.events.types import TOOL_TASK


def _extract_event_text_fragments(value: Any) -> list[str]:
    fragments: list[str] = []
    if isinstance(value, str):
        if value.strip():
            fragments.append(value.strip())
        return fragments
    if isinstance(value, dict):
        for nested in value.values():
            fragments.extend(_extract_event_text_fragments(nested))
        return fragments
    if isinstance(value, (list, tuple)):
        for nested in value:
            fragments.extend(_extract_event_text_fragments(nested))
        return fragments
    content = getattr(value, "content", None)
    if content is not None:
        fragments.extend(_extract_event_text_fragments(content))
    return fragments


def _extract_task_tool_input(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event") != "on_tool_start":
        return None
    if str(event.get("name") or "").casefold() != TOOL_TASK:
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    task_input = data.get("input")
    if isinstance(task_input, dict):
        return task_input
    return None


def _task_input_text(task_input: dict[str, Any]) -> str:
    return "\n".join(_extract_event_text_fragments(task_input)).casefold()


def _task_subagent_type(task_input: dict[str, Any]) -> str:
    return str(
        task_input.get("subagent_type")
        or task_input.get("subagent")
        or task_input.get("agent")
        or task_input.get("target")
        or ""
    ).casefold()


def _task_target_text(subagent_type: str, text: str) -> str:
    target_lines = [
        line
        for line in text.splitlines()
        if any(marker in line for marker in ("target member", "current member", "subagent_type"))
    ]
    return "\n".join((subagent_type, *target_lines))


def _task_targets_prompt_member(subagent_type: str, text: str) -> bool:
    target_text = _task_target_text(subagent_type, text)
    return any(
        marker in target_text
        for marker in (
            "prompt_engineer",
            "prompt-engineer",
            "prompt",
            "提示词 agent",
            "提示词成员",
        )
    )


def _task_targets_storyboard_member(subagent_type: str, text: str) -> bool:
    target_text = _task_target_text(subagent_type, text)
    return any(
        marker in target_text
        for marker in (
            "copywriter",
            "copy-writing",
            "storyboard",
            "分镜 agent",
            "文案 agent",
            "宣传文案",
        )
    )


def _task_targets_manager_member(subagent_type: str, text: str) -> bool:
    target_text = _task_target_text(subagent_type, text)
    return any(
        marker in target_text
        for marker in (
            "manager",
            "workflow",
            "agent-manager",
            "工作流管理",
            "管理 agent",
        )
    )


def _collect_full_asset_package_stages_from_event(event: Any) -> set[str]:
    if not isinstance(event, dict):
        return set()
    task_input = _extract_task_tool_input(event)
    if task_input is None:
        return set()
    text = _task_input_text(task_input)
    subagent_type = _task_subagent_type(task_input)
    stages: set[str] = set()

    is_delivery = any(
        marker in text
        for marker in ("file_artifact", "create_files", "delivery mode: create_files")
    ) and any(
        marker in text
        for marker in ("image_generate", "reveal_project", "下载包", "压缩包", "archive", "zip")
    )
    if is_delivery:
        stages.add("delivery")
        return stages

    if _task_targets_manager_member(subagent_type, text) and any(
        marker in text
        for marker in (
            "需求梳理",
            "requirement clarification",
            "material/attachment constraints",
            "素材包交付清单",
            "可用素材",
            "总时长",
        )
    ):
        stages.add("requirements")
    if _task_targets_storyboard_member(subagent_type, text) and any(
        marker in text
        for marker in (
            "宣传文案",
            "分镜",
            "storyboard",
            "scene 编号",
            "scene number",
            "画面目标",
            "visual goal",
        )
    ):
        stages.add("storyboard")
    prompt_field_count = sum(
        1
        for marker in (
            "image prompt en",
            "negative prompt en",
            "image-to-video prompt en",
            "图片生成提示词",
            "图生视频提示词",
            "负面提示词",
        )
        if marker in text
    )
    if _task_targets_prompt_member(subagent_type, text) and prompt_field_count >= 3:
        stages.add("prompts")
    return stages


def _build_full_asset_package_stage_description(
    *,
    team: Any,
    member: Any,
    user_input: Any,
    stage: str,
    title: str,
    index: int,
    total: int,
    previous_results: list[tuple[str, str]],
) -> str:
    role_name = getattr(member, "role_name", None) or build_team_member_subagent_type(member)
    prior = "\n\n".join(
        f"### Previous result from {name}\n{result.strip()}"
        for name, result in previous_results
        if result.strip()
    )
    prior_section = prior or "No previous stage result yet. Use the original request as input."
    common_header = (
        "Team router forced full asset package pipeline.\n"
        "This is a hard recovery assignment because the router did not prove that the "
        "complete four-stage deliverable contract was satisfied.\n"
        f"Team: {getattr(team, 'name', '')}.\n"
        f"Current task start time: {time.strftime('%Y-%m-%d %H:%M:%S %z')}.\n"
        f"Pipeline stage: {index}/{total} - {title}.\n"
        f"Target member: {role_name}.\n\n"
        "Original user request:\n"
        f"{str(user_input or '').strip()}\n\n"
        "Fixed inputs from prior stages:\n"
        f"{prior_section}\n\n"
    )
    if stage == "requirements":
        return (
            common_header
            + "Task type: MULTI_STAGE\n"
            + "Delivery mode: RETURN_TEXT\n"
            + "Reference policy: USER_PROVIDED_ONLY\n"
            + "Tool policy: NO_TOOLS\n"
            + "Max tool calls: 0\n"
            + "Artifact intent: false\n"
            + "Allowed tools: none\n"
            + "Forbidden actions: read files, write files, generate images, create folders, package, reveal.\n"
            + "Objective: perform only requirement clarification for a scene-level first-frame image and image-to-video package.\n"
            + "Output format: user request summary; available materials/attachment constraints; total duration; Scene count and duration plan; global visual constraints; screen prohibitions; material package checklist; Fixed inputs for the next member.\n"
        )
    if stage == "storyboard":
        return (
            common_header
            + "Task type: MULTI_STAGE\n"
            + "Delivery mode: RETURN_TEXT\n"
            + "Reference policy: USER_PROVIDED_ONLY\n"
            + "Tool policy: NO_TOOLS\n"
            + "Max tool calls: 0\n"
            + "Artifact intent: false\n"
            + "Allowed tools: none\n"
            + "Forbidden actions: read files, create directories, write prompt files, generate images, package, reveal.\n"
            + "Objective: produce 4-6 continuous scenes, preferably no more than 6, each usually 6 or 10 seconds.\n"
            + "Output format for each Scene: Scene number; duration; corresponding copy/content; visual goal; visual description; subject action; setting; emotion; transition suggestion; expression boundary.\n"
        )
    if stage == "prompts":
        return (
            common_header
            + "Task type: MULTI_STAGE\n"
            + "Delivery mode: RETURN_TEXT\n"
            + "Reference policy: USER_PROVIDED_ONLY\n"
            + "Tool policy: NO_TOOLS\n"
            + "Max tool calls: 0\n"
            + "Artifact intent: false\n"
            + "Allowed tools: none\n"
            + "Forbidden actions: use tools, read files, create files, reveal, use placeholders, write 'same as above'.\n"
            + "Objective: write self-contained per-Scene image and image-to-video prompts for independent first-frame images.\n"
            + "Global rules: default 9:16 vertical; each prompt must include unified style, region, era/setting, subject, composition, lighting, realistic texture, and aspect ratio; screen text, subtitles, logos, menus, readable signs are forbidden by default; English negative prompt must contain: No subtitles / no captions / no text.\n"
            + "Output format for each Scene: Scene number; duration; corresponding content; visual description; 图片生成提示词 CN; Image Prompt EN; 负面提示词 CN; Negative Prompt EN; 图生视频提示词 CN; Image-to-Video Prompt EN.\n"
        )
    return (
        common_header
        + "Task type: FILE_ARTIFACT\n"
        + "Delivery mode: CREATE_FILES\n"
        + "Reference policy: USER_PROVIDED_ONLY\n"
        + "Tool policy: ARTIFACT_ALLOWED\n"
        + "Max tool calls: as needed\n"
        + "Artifact intent: true\n"
        + "Allowed tools: image_generate, file write/edit tools, shell/archive tools, reveal_project, and verification tools as available.\n"
        + "Forbidden actions: claim nonexistent images, files, folders, or zip packages; use placeholder images as first-frame images; copy URL text as a PNG; finish without reveal_project when a folder/package was created.\n"
        + "Objective: create the real deliverable package for every Scene.\n"
        + "Required execution: for each Scene, use the English image prompt to generate an independent 9:16 first-frame image; save real image files under scenes/scene_01, scene_02, etc.; write README.md, storyboard.md, style_guide.md, and each Scene's CN/EN image prompts, CN/EN image-to-video prompts, negative prompts, and notes; create a real downloadable archive; verify Scene count, total duration, files, images, and archive.\n"
        + "Image URL handling: if image_generate returns images[].url as an HTTP URL, download it to a PNG file with curl -fL or Python; verify it with file/PIL/Image.open; do not package cache query strings or raw URL text.\n"
        + "Final action: call reveal_project for the delivery directory. If image generation, file writing, zipping, or reveal fails, clearly report the blocker or partial completion and do not mark the package as complete.\n"
    )


def _build_forced_delegation_description(
    *,
    team: Any,
    member: Any,
    user_input: Any,
    reason: str,
    index: int,
    total: int,
    previous_results: list[tuple[str, str]],
) -> str:
    role_name = getattr(member, "role_name", None) or build_team_member_subagent_type(member)
    prior = "\n\n".join(
        f"### Previous result from {name}\n{result.strip()}"
        for name, result in previous_results
        if result.strip()
    )
    prior_section = prior or "No previous member result yet. Start from the original request."
    return (
        "Team router forced delegation recovery.\n"
        f"Reason: {reason}.\n"
        f"Team: {getattr(team, 'name', '')}.\n"
        f"Current member: {role_name} ({index}/{total}).\n\n"
        "Original user request:\n"
        f"{str(user_input or '').strip()}\n\n"
        "Previous member results:\n"
        f"{prior_section}\n\n"
        "Assignment:\n"
        "- Complete the concrete portion of the request that matches your role.\n"
        "- For a complete short-video/material package, produce actual deliverable content, "
        "not just a plan.\n"
        "- If the user did not specify a topic, product, audience, style, or length, choose "
        "reasonable general-purpose defaults and state them briefly; do not stop, block, or "
        "ask for clarification.\n"
        "- Include clear handoff details for the next member when useful.\n"
        "- If you are the final member, include a concise final package summary and any "
        "artifact or image-generation status you can verify.\n"
    )
