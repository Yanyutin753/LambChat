"""Prepare and remove only this native run's synthetic production fixtures."""

import json
import os
import sys
from pathlib import Path


def save_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)


def main():
    root = Path(__file__).resolve().parent
    os.environ["DISTTEST_IMAGE_RESULTS"] = str(root / "fixture-results.jsonl")
    sys.path.insert(0, "/root/disttest")
    # Import the fixture shipped for this run, not an older server copy.
    sys.path.insert(0, str(root))
    import image_loading as images

    state = root / "cleanup.json"
    metadata = root / "metadata.json"
    images.common.remember_session = lambda _: None
    if sys.argv[1] == "prepare":
        try:
            result = images.prepare_fixture("真机验收｜桌面发布回归｜")
            save_private(metadata, result)
        finally:
            save_private(state, images.CLEANUP)
        print("PASS synthetic image fixture and private-access checks")
        return
    if sys.argv[1] != "cleanup":
        raise ValueError("Unknown native fixture operation")
    if not state.exists():
        return
    data = json.loads(state.read_text())
    if data and not data.get("token"):
        data["token"] = images.pod_python(
            'from src.infra.auth.jwt import create_access_token\nimport json\nprint(json.dumps({"token":create_access_token('
            + repr(images.common.UID)
            + ")}))"
        )["token"]
    images.CLEANUP.update(data)
    if data:
        status, _, raw = images.request(
            "GET", images.common.NP + "/api/sessions/" + data["session"], data["token"]
        )
        if status != 404:
            assert status == 200
            session = json.loads(raw)
            assert session["user_id"] == images.common.UID
            assert session["name"].startswith("真机验收｜桌面发布回归｜")
            images.cleanup_images()
            result = images.api("DELETE", "/api/sessions/" + data["session"], data["token"])
            assert result["status"] == "deleted"
        assert (
            images.request(
                "GET", images.common.NP + "/api/sessions/" + data["session"], data["token"]
            )[0]
            == 404
        )
    metadata.unlink(missing_ok=True)
    state.unlink()
    print("PASS own fixture/session/credential cleanup")


if __name__ == "__main__":
    main()
