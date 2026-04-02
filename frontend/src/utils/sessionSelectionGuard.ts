let blockedUntil = 0;
let pendingTargetPath: string | null = null;

function isChatPath(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

export function beginSessionSelectionGuard(
  targetPath: string,
  fallbackMs = 3000,
): void {
  pendingTargetPath = targetPath;
  blockedUntil = Date.now() + fallbackMs;
}

export function clearSessionSelectionGuard(): void {
  pendingTargetPath = null;
  blockedUntil = 0;
}

export function shouldBlockSessionSelection(currentPathname: string): boolean {
  if (!pendingTargetPath) {
    return false;
  }

  if (Date.now() >= blockedUntil) {
    clearSessionSelectionGuard();
    return false;
  }

  if (!isChatPath(currentPathname)) {
    clearSessionSelectionGuard();
    return false;
  }

  return true;
}
