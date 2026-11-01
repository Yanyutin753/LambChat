import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { agentApi } from "../../services/api/agent";
import type { AgentInfo } from "../../types";

/**
 * assistant 身份展示用的 agent 目录。站内默认走 /api/agents；
 * 公开分享页没有该接口，由 SharedPage 用 agent_meta 合成条目后
 * 通过 Provider 注入（注入后不再发请求）。
 */
const AgentDisplayCatalogContext = createContext<readonly AgentInfo[] | null>(
  null,
);

export function AgentDisplayCatalogProvider({
  agents,
  children,
}: {
  agents: readonly AgentInfo[];
  children: ReactNode;
}) {
  return (
    <AgentDisplayCatalogContext.Provider value={agents}>
      {children}
    </AgentDisplayCatalogContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAgentDisplayCatalog(): readonly AgentInfo[] {
  const provided = useContext(AgentDisplayCatalogContext);
  const [fetched, setFetched] = useState<readonly AgentInfo[]>([]);
  useEffect(() => {
    if (provided) return;
    let active = true;
    agentApi
      .list()
      .then((data) => {
        if (active) setFetched(data.agents || []);
      })
      .catch(() => {
        /* 未登录或接口失败时保留内置翻译兜底 */
      });
    return () => {
      active = false;
    };
  }, [provided]);
  return provided ?? fetched;
}
