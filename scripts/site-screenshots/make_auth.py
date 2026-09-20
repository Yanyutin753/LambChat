#!/usr/bin/env python3
"""LambChat 登录态生成器。

调用 LambChat 登录 API,把 access_token / refresh_token 写成 Playwright
storage_state 格式的 auth.json,供 `shot-scraper multi --auth auth.json` 使用,
让截图脚本可以拍到登录后的页面。

用法:
    python3 make_auth.py https://test.lambchat.com 用户名 密码

仅用标准库。token 有效期由服务端 expires_in 决定(通常 24h),过期重跑即可。
"""

import json
import sys
import urllib.request


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(f"用法: {sys.argv[0]} <base_url> <username> <password>")
    base, username, password = sys.argv[1:4]
    base = base.rstrip("/")

    req = urllib.request.Request(
        base + "/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    if "access_token" not in data:
        sys.exit("登录失败: " + json.dumps(data, ensure_ascii=False)[:300])

    state = {
        "cookies": [],
        "origins": [
            {
                "origin": base,
                "localStorage": [
                    {"name": "access_token", "value": data["access_token"]},
                    {"name": "refresh_token", "value": data["refresh_token"]},
                ],
            }
        ],
    }
    with open("auth.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    print(f"auth.json 已生成({base})")


if __name__ == "__main__":
    main()
