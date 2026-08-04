/**
 * SharedEntry - 公开分享页统一入口
 *
 * 拉取一次分享内容，按 share_scope 分发到会话页或项目页，
 * 并把已拉取的数据作为 initialData 注入，避免子组件重复请求。
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { shareApi } from "../../services/api/share";
import type { SharedContent } from "../../types";
import { SharedPage } from "./SharedPage";
import { SharedProjectPage } from "./SharedProjectPage";

export function SharedEntry() {
  const { shareId } = useParams<{ shareId: string }>();
  const [data, setData] = useState<SharedContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!shareId) {
        setFailed(true);
        setLoading(false);
        return;
      }
      try {
        const res = await shareApi.getSharedContent(shareId);
        if (!cancelled) setData(res);
      } catch {
        // 交给 SharedPage 渲染其完整的 401/404 错误态
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [shareId]);

  if (loading) {
    return (
      <div className="min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-theme-text-secondary" />
      </div>
    );
  }

  if (failed || !data) {
    return <SharedPage />;
  }

  if ("sessions" in data) {
    return <SharedProjectPage initialManifest={data} />;
  }
  return <SharedPage initialData={data} />;
}
