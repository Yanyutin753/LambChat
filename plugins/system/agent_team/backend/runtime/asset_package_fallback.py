"""Deterministic full asset-package fallback delivery."""

import io
import json
import uuid
import zipfile
from types import SimpleNamespace
from typing import Any

from plugins.system.agent_team.backend.runtime.asset_delivery import (
    reveal_project_files,
    uploaded_file_path_from_url,
)
from plugins.system.agent_team.backend.runtime.context import TeamAgentContext


def _default_full_asset_scenes() -> list[dict[str, str]]:
    return [
        {
            "id": "scene_01",
            "title": "开场钩子：内容策划痛点",
            "duration": "10s",
            "copy": "开场文案：一条抖音不是先拍再想，而是先让用户第一眼知道为什么要停下。",
            "visual": "现代内容工作室里，策划师面对空白分镜板整理短视频结构，桌面有手机、镜头和咖啡，气氛专注。",
            "image_prompt_en": "9:16 vertical realistic cinematic commercial photo, modern Chinese content studio, a young video strategist planning a Douyin short-video storyboard at a desk, smartphone and camera lens on the table, warm white practical light, subtle blue-purple rim light, shallow depth of field, premium clean composition, no readable text, no logo, no captions.",
            "i2v_prompt_en": "Slow dolly-in from the desk props to the strategist and blank storyboard board, natural hand movement, focused expression, cinematic stable motion, 10 seconds, no subtitles, no captions, no text.",
        },
        {
            "id": "scene_02",
            "title": "核心方案：账号定位与内容矩阵",
            "duration": "10s",
            "copy": "中段文案：账号定位、内容矩阵、首帧吸引、转化路径，决定这条视频能不能被看完。",
            "visual": "创意会议室内，两名运营人员围绕无字卡片和抽象增长图形讨论内容矩阵，画面专业清晰。",
            "image_prompt_en": "9:16 vertical realistic cinematic commercial photo, creative meeting room in a contemporary Chinese city, two short-video operators discussing a content matrix with blank cards and abstract chart shapes, no readable writing, warm neutral colors, clean premium business atmosphere, realistic texture, shallow depth of field, no logo, no subtitles, no captions.",
            "i2v_prompt_en": "Gentle side pan across the blank strategy cards, operators point and nod, abstract chart shapes glow softly, professional and calm movement, 10 seconds, no readable text.",
        },
        {
            "id": "scene_03",
            "title": "执行落地：拍摄剪辑与首帧设计",
            "duration": "10s",
            "copy": "执行文案：拍摄、剪辑、首帧图、标题文案和发布节奏，要在同一个目标下协同。",
            "visual": "拍摄现场与剪辑工作台结合，竖屏手机、相机、灯光和剪辑屏幕构成真实执行场景。",
            "image_prompt_en": "9:16 vertical realistic cinematic commercial photo, short-video production setup, vertical smartphone on a stabilizer, camera and softbox light, editor at a workstation, contemporary Chinese commercial studio, warm key light with blue-purple ambient light, realistic materials, clean composition, no screen text, no logo, no captions.",
            "i2v_prompt_en": "Camera glides from the vertical phone rig to the editor's hands, soft light changes naturally, equipment remains stable, professional filming atmosphere, 10 seconds, no text or logos.",
        },
        {
            "id": "scene_04",
            "title": "成果收束：交付感与行动引导",
            "duration": "10s",
            "copy": "收束文案：把策划变成可执行素材包，让每一段画面都有首帧、文案和图生视频提示词。",
            "visual": "策划师站在抽象增长数据背景前做最终确认，背后是无字图形化面板和暖色高光，呈现专业交付感。",
            "image_prompt_en": "9:16 vertical realistic cinematic commercial photo, confident short-video strategist in a modern studio, abstract growth visualization panels without readable text, warm highlights, subtle blue-purple tech ambience, premium business delivery feeling, shallow depth of field, realistic human proportions, no subtitles, no captions, no logo, no text.",
            "i2v_prompt_en": "Slow push-in toward the strategist, abstract panels pulse softly without readable symbols, the subject turns slightly toward camera with a confident calm expression, cinematic stable motion, 10 seconds, no text.",
        },
    ]


def _read_uploaded_file_url_bytes(url: str) -> bytes:
    local_path = uploaded_file_path_from_url(url)
    if not local_path:
        raise ValueError(f"unsupported generated image URL: {url}")
    with open(local_path, "rb") as file_obj:
        return file_obj.read()


async def _generate_full_asset_scene_images(
    *,
    scenes: list[dict[str, str]],
    runtime: Any,
    event_processor: Any,
) -> tuple[dict[str, bytes], dict[str, str]]:
    generated: dict[str, bytes] = {}
    failures: dict[str, str] = {}

    try:
        from src.infra.tool.image_generation_tool import (
            ImageOutputFormat,
            ImageQuality,
            ImageSize,
            image_generate,
        )
    except Exception as exc:
        return {}, {scene["id"]: f"image_generate import failed: {exc}" for scene in scenes}

    coroutine = getattr(image_generate, "coroutine", None)
    if not callable(coroutine):
        return {}, {scene["id"]: "image_generate coroutine is unavailable" for scene in scenes}

    for scene in scenes:
        tool_call_id = f"agent_team_fallback_image_generate_{scene['id']}_{uuid.uuid4().hex[:8]}"
        args = {
            "prompt": scene["image_prompt_en"],
            "input_images": None,
            "size": ImageSize.PORTRAIT.value,
            "quality": ImageQuality.AUTO.value,
            "n": 1,
            "output_format": ImageOutputFormat.PNG.value,
        }
        if event_processor is not None:
            await event_processor.process_event(
                {
                    "event": "on_tool_start",
                    "name": "image_generate",
                    "run_id": tool_call_id,
                    "data": {"input": args},
                    "metadata": {},
                }
            )
        try:
            result_text = await coroutine(
                prompt=scene["image_prompt_en"],
                input_images=None,
                size=ImageSize.PORTRAIT,
                quality=ImageQuality.AUTO,
                n=1,
                output_format=ImageOutputFormat.PNG,
                runtime=runtime,
            )
        except Exception as exc:
            result_text = json.dumps({"error": f"image_generate raised: {exc}"}, ensure_ascii=False)

        if event_processor is not None:
            await event_processor.process_event(
                {
                    "event": "on_tool_end",
                    "name": "image_generate",
                    "run_id": tool_call_id,
                    "data": {"output": result_text},
                    "metadata": {},
                }
            )

        try:
            parsed = json.loads(result_text)
        except Exception as exc:
            failures[scene["id"]] = f"image_generate returned non-JSON output: {exc}"
            continue
        if not isinstance(parsed, dict):
            failures[scene["id"]] = "image_generate returned an unexpected result type"
            continue
        if parsed.get("error"):
            failures[scene["id"]] = str(parsed.get("error"))
            continue
        images = parsed.get("images")
        if not isinstance(images, list) or not images:
            failures[scene["id"]] = "image_generate returned no images"
            continue
        image_url = images[0].get("url") if isinstance(images[0], dict) else None
        if not image_url:
            failures[scene["id"]] = "image_generate returned an image without a URL"
            continue
        try:
            image_bytes = _read_uploaded_file_url_bytes(str(image_url))
        except Exception as exc:
            failures[scene["id"]] = f"failed to materialize generated image URL: {exc}"
            continue
        generated[scene["id"]] = image_bytes

    return generated, failures


def _build_fallback_asset_files(
    project_dir: str,
    user_input: Any,
    *,
    generated_images: dict[str, bytes],
    image_failures: dict[str, str],
) -> dict[str, bytes]:
    scenes = _default_full_asset_scenes()
    files: dict[str, bytes] = {}
    request_text = str(user_input or "").strip()
    image_status = (
        "complete"
        if len(generated_images) == len(scenes)
        else f"partial ({len(generated_images)}/{len(scenes)} first-frame images generated)"
    )

    readme = [
        "# Douyin Full Planning Asset Package",
        "",
        f"Original request: {request_text}",
        "",
        "Default topic: generic modern Douyin content planning package.",
        "Format: 9:16 vertical short video.",
        "Total duration: 40 seconds.",
        "Scene count: 4 scenes, 10 seconds each.",
        f"Image generation status: {image_status}.",
        "",
        "Included deliverables:",
        "- storyboard and publishing copy",
        "- independent first-frame PNG for each Scene only when image_generate succeeded",
        "- CN/EN image prompts",
        "- CN/EN image-to-video prompts",
        "- CN/EN negative prompts",
        "- notes for each Scene",
        "- zip archive containing the same package files",
        "",
        "Important: if image_generate failed for a Scene, this package marks that Scene as partial and does not include a placeholder first_frame.png.",
    ]
    files[f"{project_dir}/README.md"] = "\n".join(readme).encode("utf-8")

    storyboard_lines = ["# Storyboard", ""]
    for scene in scenes:
        storyboard_lines.extend(
            [
                f"## {scene['id']} - {scene['title']}",
                f"Duration: {scene['duration']}",
                f"Copy: {scene['copy']}",
                f"Visual: {scene['visual']}",
                "Transition: clean cinematic cut into the next production step.",
                "",
            ]
        )
    files[f"{project_dir}/storyboard.md"] = "\n".join(storyboard_lines).encode("utf-8")

    style_guide = """# Style Guide

- Aspect ratio: 9:16 vertical.
- Visual style: realistic cinematic commercial photography.
- Setting: contemporary Chinese urban content studio and production workspace.
- Lighting: warm white key light with subtle blue-purple technology ambience.
- Texture: realistic people, equipment, desks, glass, screens, and studio materials.
- Forbidden: subtitles, captions, readable text, logos, watermarks, QR codes, phone numbers, platform marks, exaggerated claims.
- Required negative prompt EN: No subtitles, no captions, no text, no logo, no watermark, no readable signs.
"""
    files[f"{project_dir}/style_guide.md"] = style_guide.encode("utf-8")

    negative_cn = "不要字幕，不要标题文字，不要可读文字，不要 Logo，不要水印，不要二维码，不要联系方式，不要平台标识，不要畸形手部，不要低清晰度。"
    negative_en = "No subtitles, no captions, no text, no logo, no watermark, no readable signs, no QR code, no phone number, no platform mark, no deformed hands, no low resolution."

    for index, scene in enumerate(scenes, start=1):
        scene_dir = f"{project_dir}/scenes/{scene['id']}"
        if scene["id"] in generated_images:
            files[f"{scene_dir}/first_frame.png"] = generated_images[scene["id"]]
        else:
            files[f"{scene_dir}/first_frame_status.md"] = (
                "# First Frame Status\n\n"
                "No `first_frame.png` is included for this Scene because real image generation did not complete.\n\n"
                f"Failure reason: {image_failures.get(scene['id'], 'image_generate did not return a usable image')}.\n\n"
                "This is intentionally marked as partial completion; no placeholder image is used as a first-frame image.\n"
            ).encode("utf-8")
        files[f"{scene_dir}/image_prompt_cn.txt"] = (
            f"9:16 竖屏，真实电影感商业摄影，当代中国城市内容工作室，{scene['visual']}，"
            "暖白主光，蓝紫色轻科技氛围光，浅景深，构图干净高级，真实材质，无字幕，无文字，无 Logo。"
        ).encode("utf-8")
        files[f"{scene_dir}/image_prompt_en.txt"] = scene["image_prompt_en"].encode("utf-8")
        files[f"{scene_dir}/negative_prompt_cn.txt"] = negative_cn.encode("utf-8")
        files[f"{scene_dir}/negative_prompt_en.txt"] = negative_en.encode("utf-8")
        files[f"{scene_dir}/i2v_prompt_cn.txt"] = (
            f"{scene['duration']} 图生视频：{scene['visual']}。镜头运动稳定、缓慢、专业，人物动作自然，"
            "光线无闪烁，禁止字幕、文字、Logo、水印和可读标识。"
        ).encode("utf-8")
        files[f"{scene_dir}/i2v_prompt_en.txt"] = scene["i2v_prompt_en"].encode("utf-8")
        files[f"{scene_dir}/notes.md"] = (
            f"# {scene['id']} Notes\n\n"
            f"- Title: {scene['title']}\n"
            f"- Duration: {scene['duration']}\n"
            f"- Copy: {scene['copy']}\n"
            f"- Visual objective: {scene['visual']}\n"
            + (
                "- First-frame image: first_frame.png\n"
                if scene["id"] in generated_images
                else "- First-frame image: not generated; see first_frame_status.md\n"
            )
        ).encode("utf-8")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        prefix = f"{project_dir.rstrip('/')}/"
        for path, content in files.items():
            archive.writestr(path.replace(prefix, ""), content)
    files[f"{project_dir}/douyin_full_planning_asset_package.zip"] = zip_buffer.getvalue()
    return files


async def _create_and_reveal_full_asset_package_fallback(
    *,
    team: Any,
    user_input: Any,
    backend: Any,
    context: TeamAgentContext,
    presenter: Any,
    event_processor: Any,
    configurable: dict[str, Any],
) -> str:
    if backend is None:
        return "完整素材包兜底交付失败：backend_not_available，无法写入文件系统。"

    session_id = str(configurable.get("session_id") or uuid.uuid4().hex)
    project_name = "douyin_full_planning_asset_package"
    project_dir = f"/home/user/sessions/{session_id}/{project_name}"
    runtime = SimpleNamespace(
        config={
            "configurable": {
                **configurable,
                "backend": backend,
                "context": context,
                "presenter": presenter,
                "session_id": session_id,
                "trace_id": getattr(presenter, "trace_id", None),
                "delivery_source": "agent_team_full_asset_fallback",
            }
        }
    )
    scenes = _default_full_asset_scenes()
    generated_images, image_failures = await _generate_full_asset_scene_images(
        scenes=scenes,
        runtime=runtime,
        event_processor=event_processor,
    )
    files = _build_fallback_asset_files(
        project_dir,
        user_input,
        generated_images=generated_images,
        image_failures=image_failures,
    )

    upload = getattr(backend, "aupload_files", None)
    if not callable(upload):
        return "完整素材包兜底交付失败：backend_aupload_files_not_available，无法写入素材文件。"

    await upload(list(files.items()))

    from src.infra.tool.reveal_project_tool import reveal_project

    image_status = (
        "complete"
        if len(generated_images) == len(scenes)
        else f"partial: {len(generated_images)}/{len(scenes)} first-frame images generated"
    )
    reveal_args = {
        "project_path": project_dir,
        "name": project_name,
        "description": (
            "完整抖音策划素材包：分镜、文案、每段首帧图、"
            "中英文图片提示词、图生视频提示词、负面提示词与 zip 包。"
            f"图片生成状态：{image_status}。"
        ),
        "template": None,
    }
    tool_call_id = f"agent_team_fallback_reveal_project_{uuid.uuid4().hex[:8]}"
    if event_processor is not None:
        await event_processor.process_event(
            {
                "event": "on_tool_start",
                "name": "reveal_project",
                "run_id": tool_call_id,
                "data": {"input": reveal_args},
                "metadata": {},
            }
        )

    coroutine = getattr(reveal_project, "coroutine", None)
    if callable(coroutine):
        reveal_result = await coroutine(**reveal_args, runtime=runtime)
    else:
        reveal_result = await reveal_project.ainvoke(reveal_args)

    if event_processor is not None:
        await event_processor.process_event(
            {
                "event": "on_tool_end",
                "name": "reveal_project",
                "run_id": tool_call_id,
                "data": {"output": reveal_result},
                "metadata": {},
            }
        )

    revealed_files, reveal_error = reveal_project_files(reveal_result)
    file_count = len(revealed_files)
    if reveal_error:
        return (
            "完整抖音策划素材包已部分完成，但项目目录交付失败。\n\n"
            f"- reveal_project 失败：{reveal_error}\n"
            f"- 已写入素材文件：{len(files)} 个\n"
            f"- 首帧图：{len(generated_images)}/{len(scenes)} 成功\n"
            "- 未声称下载包已交付；未使用占位图冒充首帧图。"
        )
    completion_label = "完整交付" if len(generated_images) == len(scenes) else "部分交付"
    failed_scene_count = len(image_failures)
    failure_note = (
        "- 失败 Scene 已写入 first_frame_status.md，未使用占位图冒充首帧图。\n"
        if image_failures
        else ""
    )
    return (
        f"完整抖音策划素材包已{completion_label}。\n\n"
        "- 交付目录已通过 reveal_project 展示。\n"
        f"- Project directory: {project_dir}\n"
        f"- Scene：{len(scenes)} 段\n"
        f"- 文件数：{file_count or len(files)}\n"
        f"- 首帧图：{len(generated_images)}/{len(scenes)} 成功\n"
        f"- 图片生成失败：{failed_scene_count} 段\n"
        f"{failure_note}"
        "- 已包含：策划文档、分镜文案、中英文图片提示词、图生视频提示词、负面提示词、zip 包。"
    )
