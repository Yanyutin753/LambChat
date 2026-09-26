// 工作区文件树：本地沙箱目录的懒加载/刷新状态机（桌面双栏的文件面板数据源）。
//
// 数据源是 /api/sandbox/fs/list（服务端把 fs_ls 中继到会话绑定的 daemon），
// 因此树根随 sessionId 变化整体重置；目录按需装载（展开才 list），refresh
// 保留 expanded 集合只重拉已见过目录——run 结束后的自动刷新靠这个语义
// 保住用户的展开现场。同路径并发装载去重（in-flight 表），防止快速点击
// 目录时发出重复请求。
import { useCallback, useEffect, useRef, useState } from "react";
import { sandboxFsApi, type SandboxFsEntry } from "../services/api/sandboxFs";

export interface WorkspaceTreeNode {
  /** 工作区内相对路径（posix；根目录条目为 "."）。 */
  path: string;
  name: string;
  isDir: boolean;
  children?: WorkspaceTreeNode[];
  loading?: boolean;
}

export type WorkspaceTreeState = "idle" | "loading" | "ready" | "error";

/** 目录在前、同名不区分大小写的字母序（VS Code/Finder 的直觉排序）。 */
function compareEntries(a: SandboxFsEntry, b: SandboxFsEntry): number {
  if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
  return a.path.localeCompare(b.path, undefined, { sensitivity: "base" });
}

function toNode(entry: SandboxFsEntry): WorkspaceTreeNode {
  const name = entry.path.split("/").pop() || entry.path;
  return { path: entry.path, name, isDir: entry.is_dir };
}

/** 把一层 entries 挂到 path 对应的目录节点上（path "." = 根）。 */
function attachLevel(
  nodes: WorkspaceTreeNode[],
  path: string,
  entries: SandboxFsEntry[],
): WorkspaceTreeNode[] {
  if (path === "." || path === "") {
    return entries.slice().sort(compareEntries).map(toNode);
  }
  const walk = (list: WorkspaceTreeNode[]): WorkspaceTreeNode[] =>
    list.map((node) => {
      if (!node.isDir) return node;
      if (node.path === path) {
        return { ...node, children: entries.slice().sort(compareEntries).map(toNode), loading: false };
      }
      if (path.startsWith(`${node.path}/`) && node.children) {
        return { ...node, children: walk(node.children) };
      }
      return node;
    });
  return walk(nodes);
}

/** 标记/清除 path 目录的 loading 位（展开转圈用）。 */
function markLoading(
  nodes: WorkspaceTreeNode[],
  path: string,
  loading: boolean,
): WorkspaceTreeNode[] {
  const walk = (list: WorkspaceTreeNode[]): WorkspaceTreeNode[] =>
    list.map((node) => {
      if (!node.isDir) return node;
      if (node.path === path) return { ...node, loading };
      if (path.startsWith(`${node.path}/`) && node.children) {
        return { ...node, children: walk(node.children) };
      }
      return node;
    });
  return walk(nodes);
}

/** 收集需要重拉的目录路径（根 + 所有已装载子目录）。 */
function collectLoadedDirs(nodes: WorkspaceTreeNode[], acc: string[] = ["."]): string[] {
  for (const node of nodes) {
    if (node.isDir && node.children) {
      acc.push(node.path);
      collectLoadedDirs(node.children, acc);
    }
  }
  return acc;
}

/** 按路径找节点（path "." = 根层不存在，返回 null）。 */
function findNode(nodes: WorkspaceTreeNode[], path: string): WorkspaceTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) return node;
    if (path.startsWith(`${node.path}/`) && node.children) {
      const hit = findNode(node.children, path);
      if (hit) return hit;
    }
  }
  return null;
}

export function useWorkspaceTree(sessionId: string | null) {
  const [root, setRoot] = useState<WorkspaceTreeNode[]>([]);
  const [state, setState] = useState<WorkspaceTreeState>("idle");
  const [error, setError] = useState<string | null>(null);
  /** 展开集合（state 驱动渲染）；children 装载后常驻内存，折叠只收 UI。 */
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const inFlightRef = useRef<Set<string>>(new Set());
  /** 会话代际：sessionId 切换后旧异步结果不再落 state。 */
  const generationRef = useRef(0);

  const loadDir = useCallback(
    async (path: string, { replace }: { replace: boolean }) => {
      if (!sessionId) return;
      const key = `${sessionId}\u0000${path}`;
      if (inFlightRef.current.has(key)) return;
      inFlightRef.current.add(key);
      const generation = generationRef.current;
      if (!replace) setRoot((prev) => markLoading(prev, path, true));
      try {
        const result = await sandboxFsApi.list(sessionId, path === "." ? "" : path);
        if (generation !== generationRef.current) return;
        if (result.error) {
          if (path === ".") {
            setError(result.error);
            setState("error");
          }
          return;
        }
        setError(null);
        setRoot((prev) => attachLevel(prev, path, result.entries ?? []));
        if (path === ".") setState("ready");
      } catch (err) {
        if (generation !== generationRef.current) return;
        if (path === ".") {
          setError(err instanceof Error ? err.message : String(err));
          setState("error");
        }
      } finally {
        inFlightRef.current.delete(key);
        if (!replace) setRoot((prev) => markLoading(prev, path, false));
      }
    },
    [sessionId],
  );

  // 会话切换：整体重置（代际 +1 让在途结果作废），根目录装载。
  useEffect(() => {
    generationRef.current += 1;
    inFlightRef.current.clear();
    setExpanded(new Set());
    setRoot([]);
    setError(null);
    if (!sessionId) {
      setState("idle");
      return;
    }
    setState("loading");
    void loadDir(".", { replace: true });
  }, [sessionId, loadDir]);

  const toggleDir = useCallback(
    (path: string) => {
      if (expanded.has(path)) {
        // 折叠只收 UI：children 留在内存，重展开零请求
        setExpanded((prev) => {
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
        return;
      }
      setExpanded((prev) => new Set(prev).add(path));
      const node = findNode(root, path);
      if (!node?.children) void loadDir(path, { replace: false });
    },
    [expanded, root, loadDir],
  );

  const refresh = useCallback(() => {
    if (!sessionId || state === "loading") return;
    // 重拉根 + 已装载目录：attachLevel 原地替换，展开现场保留。
    const dirs = collectLoadedDirs(root);
    void loadDir(".", { replace: true });
    for (const dir of dirs) {
      if (dir !== ".") void loadDir(dir, { replace: true });
    }
  }, [sessionId, state, root, loadDir]);

  return { root, state, error, toggleDir, refresh, expandedPaths: expanded };
}
