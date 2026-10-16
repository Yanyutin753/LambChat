"""Reject overwriting an already published dev update."""

import json
import os
import subprocess


def check_release_mutability(tag: str, repo: str) -> None:
    if "-dev." not in tag:
        return
    response = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if response.returncode:
        if "(HTTP 404)" in response.stderr:
            return
        raise RuntimeError("Cannot verify release mutability; refusing publication")
    release = json.loads(response.stdout)
    if any(asset.get("name") == "dev-latest.json" for asset in release["assets"]):
        raise RuntimeError("Dev release is already published; use a new dev.N tag")


def check_release_source(tag: str, repo: str, expected_sha: str) -> None:
    response = subprocess.run(
        ["gh", "api", f"repos/{repo}/commits/{tag}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if response.returncode or json.loads(response.stdout).get("sha") != expected_sha:
        raise RuntimeError("Release tag source does not match the build commit")


if __name__ == "__main__":
    check_release_source(
        os.environ["RELEASE_TAG"], os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    )
    check_release_mutability(os.environ["RELEASE_TAG"], os.environ["GITHUB_REPOSITORY"])
