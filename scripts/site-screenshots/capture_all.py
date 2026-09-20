#!/usr/bin/env python3
"""LambChat 全站多端一键截图。

一条命令完成:API 登录 → 抓一个真实会话 ID(给 /chat/:sessionId 灌数据)
→ 从 frontend/src/App.tsx 路由表提取全部页面 → 多浏览器并行截图
(每页等到 网络空闲+字体就绪+DOM 稳定 才按快门)→ 生成 out/index.html 目录页。

用法:
    python3 capture_all.py --base https://test.lambchat.com \
        --username stg_verify_0828 --password 'xxx' \
        [--themes light,dark] [--devices desktop,tablet,mobile] [--jobs 8] [--no-seed]

依赖(一次性,二选一):
    uv tool install shot-scraper && shot-scraper install   # 推荐,本脚本自动复用其 playwright+Chromium
    # 或:uv tool install playwright && playwright install chromium

产物:out/<theme>/<device>/<页面>.png + out/index.html
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

DEVICES = {
    "desktop": (1440, 900),
    "tablet": (834, 1128),
    "mobile": (390, 844),
}
PUBLIC_FULL_PAGE = {
    "/",
    "/interface",
    "/features",
    "/architecture",
    "/dashboard",
    "/responsive",
    "/github",
    "/download",
    "/auth/login",
    "/auth/register",
    "/auth/reset-request",
    "/auth/reset-password",
    "/auth/verify-email",
    "/auth/pending",
}
EXCLUDED = ("/auth/callback", "/dev/")
THEME_KEY = "lambchat-theme"

# 页面级等待参数(毫秒)
NETWORK_IDLE_TIMEOUT = 8000  # networkidle 最多等这么久(SSE/长连接页封顶后继续)
DOM_STABLE_MS = 900  # DOM 尺寸连续稳定时长,达到即认为渲染完
DOM_STABLE_CAP = 10000  # 稳定等待封顶


def ensure_playwright():
    """当前解释器没有 playwright 时,复用 shot-scraper 工具环境。"""
    try:
        import playwright.sync_api  # noqa: F401

        return
    except ImportError:
        pass
    venv_py = Path.home() / ".local/share/uv/tools/shot-scraper/bin/python"
    if venv_py.exists():
        os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit("缺少 playwright:先 uv tool install shot-scraper && shot-scraper install")


def http_json(url: str, token: str | None = None, data: dict | None = None, timeout: int = 20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers=headers,
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def login(base: str, username: str, password: str) -> dict:
    data = http_json(f"{base}/api/auth/login", data={"username": username, "password": password})
    if "access_token" not in data:
        sys.exit("登录失败: " + json.dumps(data, ensure_ascii=False)[:300])
    return data


def fetch_session_id(base: str, token: str) -> str | None:
    try:
        data = http_json(f"{base}/api/sessions?limit=1", token=token)
        sessions = data.get("sessions") or []
        return sessions[0].get("id") if sessions else None
    except Exception as e:  # noqa: BLE001
        print(f"  ! 抓会话 ID 失败,/chat/<id> 将跳过: {e}")
        return None


def extract_routes(app_tsx: Path) -> list[str]:
    text = app_tsx.read_text(encoding="utf-8")
    routes = re.findall(r'<Route\s+path="([^"]+)"', text)
    seen, out = set(), []
    for r in routes:
        if r in seen or r == "*":
            continue
        seen.add(r)
        out.append(r)
    return out


def route_urls(routes: list[str], session_id: str | None) -> list[tuple[str, bool]]:
    result, skipped = [], []
    for r in routes:
        if any(r.startswith(p) for p in EXCLUDED):
            continue
        if ":sessionId?" in r:
            result.append(("/chat", False))
            if session_id:
                result.append((f"/chat/{session_id}", False))
            else:
                skipped.append(r + "(无会话数据)")
            continue
        if ":" in r:
            base_path = r.split("/:")[0]
            params = re.findall(r":\w+\??", r)
            if all(p.endswith("?") for p in params) and base_path != r:
                result.append((base_path, base_path in PUBLIC_FULL_PAGE))
                skipped.append(r + "(详情页需真实 ID)")
            else:
                skipped.append(r)
            continue
        result.append((r, r in PUBLIC_FULL_PAGE))
    for s in skipped:
        print(f"  - 跳过 {s}")
    return result


def write_auth(path: Path, base: str, tokens: dict | None, theme: str):
    entries = [
        {"name": THEME_KEY, "value": theme},
        # 中和"按时段自动切主题":显式禁用,防止账号配置把注入主题翻掉
        {
            "name": "lambchat-theme-schedule",
            "value": '{"enabled":false,"start":"00:00","end":"00:00","nightTheme":"dark"}',
        },
    ]
    if tokens:
        entries = [
            {"name": "access_token", "value": tokens["access_token"]},
            {"name": "refresh_token", "value": tokens["refresh_token"]},
        ] + entries
    state = {"cookies": [], "origins": [{"origin": base, "localStorage": entries}]}
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def slug(path: str) -> str:
    return (path.strip("/") or "home").replace("/", "-")


@dataclass
class Shot:
    theme: str
    device: str
    route: str
    url: str
    out: Path
    width: int
    height: int
    full_page: bool
    public: bool  # 公开页用匿名上下文截,否则登录态会被重定向到 /chat


SETTLE_JS = (
    """
async () => {
  try { await document.fonts.ready; } catch (e) {}
  await new Promise(resolve => {
    const deadline = Date.now() + """
    + str(DOM_STABLE_CAP)
    + """;
    // 签名包含 <html> 的 class:主题翻转(dark↔light 类名等长)不会改变 outerHTML 长度
    const sig = () => document.documentElement.outerHTML.length + '|' + document.documentElement.className;
    let last = sig(), stable = 0;
    const iv = setInterval(() => {
      const cur = sig();
      if (cur === last) stable += 200;
      else { stable = 0; last = cur; }
      if (stable >= """
    + str(DOM_STABLE_MS)
    + """ || Date.now() > deadline) {
        clearInterval(iv); resolve(true);
      }
    }, 200);
  });
  return true;
}
"""
)

# 复刻 frontend/src/utils/themeDom.ts 的 applyThemeToDocument:
# 启动后账号资料/定时主题的异步翻转可能盖掉注入的 localStorage,快门前强制归位
FORCE_THEME_JS = """
(theme) => {
  localStorage.setItem('lambchat-theme', theme);
  const cls = {light: '', dark: 'dark', sepia: 'theme-sepia'}[theme];
  const color = {light: '#f5f5f4', dark: '#151210', sepia: '#f3edde'}[theme];
  const scheme = theme === 'dark' ? 'dark' : 'light';
  const root = document.documentElement;
  root.classList.remove('dark', 'theme-sepia');
  if (cls) root.classList.add(cls);
  root.style.setProperty('background-color', color);
  root.style.setProperty('color-scheme', scheme);
  if (document.body) {
    document.body.style.setProperty('background-color', color);
    document.body.style.setProperty('color-scheme', scheme);
  }
  document.querySelectorAll('meta[name="theme-color"]')
    .forEach(m => m.setAttribute('content', color));
  return root.className;
}
"""

READ_THEME_JS = """() => {
  const cl = document.documentElement.classList;
  return cl.contains('dark') ? 'dark' : cl.contains('theme-sepia') ? 'sepia' : 'light';
}"""

# 探测页面真实内容高度:内部容器滚动的页面(如落地页)body 只有视口高,
# 整页截图前需把视口拉到内容高度,否则只截到首屏
TALL_PROBE_JS = """() => {
  let max = document.documentElement.scrollHeight;
  for (const el of document.querySelectorAll('*')) {
    if (el.scrollHeight > max && el.scrollHeight - el.clientHeight > 50) {
      max = el.scrollHeight;
    }
  }
  return max;
}"""

SCROLL_PASS_JS = """
async () => {
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 400));
  window.scrollTo(0, 0);
  return true;
}
"""


def worker(
    name: str,
    shots: list[Shot],
    auths: dict[tuple[str, bool], Path],
    counter: dict,
    lock: threading.Lock,
    total: int,
    failures: list[str],
):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        cur_key, ctx = None, None
        try:
            for s in shots:
                key = (s.theme, s.public)
                if key != cur_key:
                    if ctx:
                        ctx.close()
                    ctx = browser.new_context(
                        storage_state=str(auths[key]),
                        viewport={"width": s.width, "height": s.height},
                        reduced_motion="reduce",
                    )
                    cur_key = key
                page = ctx.new_page()
                try:
                    page.goto(s.url, wait_until="load", timeout=30000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
                    except Exception:  # noqa: BLE001  长连接页封顶后继续
                        pass
                    if s.full_page:
                        page.evaluate(SCROLL_PASS_JS)
                    page.evaluate(SETTLE_JS)
                    # 强制目标主题并校验,防止启动后的异步翻转盖掉注入值
                    page.evaluate(FORCE_THEME_JS, s.theme)
                    page.wait_for_timeout(400)
                    got = page.evaluate(READ_THEME_JS)
                    if got != s.theme:
                        page.evaluate(FORCE_THEME_JS, s.theme)
                        page.wait_for_timeout(600)
                        got = page.evaluate(READ_THEME_JS)
                    if got != s.theme:
                        with lock:
                            failures.append(f"{s.out} : 主题校验仍为 {got}(期望 {s.theme})")
                    if s.full_page:
                        content_h = page.evaluate(TALL_PROBE_JS)
                        if content_h > s.height + 100:
                            page.set_viewport_size(
                                {"width": s.width, "height": min(content_h, 12000)}
                            )
                            page.wait_for_timeout(500)
                            page.evaluate(SCROLL_PASS_JS)
                    s.out.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(s.out), full_page=s.full_page)
                except Exception as e:  # noqa: BLE001
                    with lock:
                        failures.append(f"{s.out} : {type(e).__name__} {str(e)[:120]}")
                finally:
                    page.close()
                with lock:
                    counter["done"] += 1
                    print(f"  [{counter['done']}/{total}] {s.out}", flush=True)
            if ctx:
                ctx.close()
        finally:
            browser.close()


def make_gallery(out_dir: Path, themes: list[str], devices: list[str]):
    parts = [
        "<!doctype html><meta charset='utf-8'><title>LambChat 全站截图</title>",
        "<style>body{font-family:system-ui;margin:24px;background:#0f1115;color:#e5e7eb}",
        "h1{font-size:20px}h2{font-size:17px;margin:30px 0 4px}h3{font-size:14px;color:#9ca3af;margin:14px 0 6px}",
        "div.shot{display:inline-block;margin:6px;vertical-align:top}",
        "img{max-width:320px;border:1px solid #333;border-radius:6px;display:block}",
        "span{font-size:12px;color:#9ca3af}</style>",
        "<h1>LambChat 全站截图</h1>",
    ]
    for theme in themes:
        theme_dir = out_dir / theme
        if not theme_dir.is_dir():
            continue
        parts.append(f"<h2>主题:{theme}</h2>")
        for dev in devices:
            dev_dir = theme_dir / dev
            if not dev_dir.is_dir():
                continue
            parts.append(f"<h3>{dev}</h3>")
            for f in sorted(dev_dir.glob("*.png")):
                parts.append(
                    f"<div class='shot'><img loading='lazy' src='{theme}/{dev}/{f.name}'>"
                    f"<span>{f.stem}</span></div>"
                )
    (out_dir / "index.html").write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", required=True, help="站点根地址,如 https://test.lambchat.com")
    ap.add_argument("--username", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--themes", default="light,dark", help="逗号分隔,可选 light,dark,sepia")
    ap.add_argument("--devices", default="desktop,tablet,mobile", help="逗号分隔")
    ap.add_argument(
        "--jobs", type=int, default=16, help="并行浏览器数(默认 16,每路约占 300-400MB 内存)"
    )
    ap.add_argument("--app-tsx", default=str(REPO_ROOT / "frontend/src/App.tsx"), help="路由表文件")
    ap.add_argument("--no-seed", action="store_true", help="不抓真实会话,跳过 /chat/<id>")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    bad = [d for d in devices if d not in DEVICES] + [
        t for t in themes if t not in ("light", "dark", "sepia")
    ]
    if bad:
        sys.exit(f"不认识的 themes/devices 值: {bad}")
    if args.jobs < 1:
        sys.exit("--jobs 必须 >= 1")

    ensure_playwright()
    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)

    print(f"[1/4] 登录 {base} …")
    tokens = login(base, args.username, args.password)

    print("[2/4] 提取路由 …")
    routes = extract_routes(Path(args.app_tsx))
    session_id = None if args.no_seed else fetch_session_id(base, tokens["access_token"])
    urls = route_urls(routes, session_id)

    auths = {}
    for theme in themes:
        auths[(theme, False)] = HERE / f"auth-{theme}.json"
        write_auth(auths[(theme, False)], base, tokens, theme)
        auths[(theme, True)] = HERE / f"anon-{theme}.json"
        write_auth(auths[(theme, True)], base, None, theme)

    shots: list[Shot] = []
    for theme in themes:
        for dev in devices:
            w, h = DEVICES[dev]
            for route, full in urls:
                public = route in PUBLIC_FULL_PAGE
                shots.append(
                    Shot(
                        theme,
                        dev,
                        route,
                        base + route,
                        out_dir / theme / dev / f"{slug(route)}.png",
                        w,
                        h,
                        full,
                        public,
                    )
                )
    total = len(shots)
    print(
        f"[3/4] 截图:{len(urls)} 页 × {len(devices)} 端 × {len(themes)} 主题 = {total} 张,{args.jobs} 路并行 …"
    )

    started = time.time()
    counter, lock, failures = {"done": 0}, threading.Lock(), []
    shards = [shots[i :: args.jobs] for i in range(args.jobs)]
    threads = [
        threading.Thread(
            target=worker, args=(f"w{i}", shard, auths, counter, lock, total, failures), daemon=True
        )
        for i, shard in enumerate(shards)
        if shard
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("[4/4] 生成目录页 …")
    make_gallery(out_dir, themes, devices)
    count = sum(1 for _ in out_dir.glob("*/*/*.png"))
    minutes = (time.time() - started) / 60
    print(f"\n完成:{count}/{total} 张,耗时 {minutes:.1f} 分钟")
    print(f"目录页:{out_dir / 'index.html'}")
    if failures:
        print(f"\n失败 {len(failures)} 张:")
        for f in failures:
            print("  ✗", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
