import { memo, useMemo, useState, useCallback, useEffect, useRef } from "react";
import { Bot, ChevronDown, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AgentInfo } from "../../types";

interface AgentItemProps {
  agent: AgentInfo;
  isSelected: boolean;
  onSelect: () => void;
}

/**
 * AgentItem - 单个助手列表项
 * 使用 memo 避免无关项重渲染
 */
const AgentItem = memo(function AgentItem({
  agent,
  isSelected,
  onSelect,
}: AgentItemProps) {
  const { t } = useTranslation();
  return (
    <button
      onClick={onSelect}
      className="w-full px-3 py-4 text-left hover:bg-gray-100/80 dark:hover:bg-stone-700/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600">
          <Bot size={18} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-700 dark:text-stone-200">
            {t(agent.name)}
          </div>
          <div className="text-xs text-gray-400 dark:text-stone-500 truncate">
            {t(agent.description)}
          </div>
        </div>
        {isSelected && (
          <Check
            size={18}
            className="flex-shrink-0 text-violet-600 dark:text-violet-400"
          />
        )}
      </div>
    </button>
  );
});

interface AgentSelectorProps {
  agents: AgentInfo[];
  currentAgent: string;
  agentsLoading: boolean;
  onSelectAgent: (agentId: string) => void;
}

/**
 * AgentSelector - 助手选择器组件
 *
 * 性能优化：
 * 1. memo: props 不变时不重渲染
 * 2. useMemo: 缓存当前助手查找结果
 * 3. useCallback: 稳定的回调函数引用
 * 4. 细粒度 memo: AgentItem 独立 memo，切换时只重渲染受影响的项
 */
const AgentSelector = memo(function AgentSelector({
  agents,
  currentAgent,
  agentsLoading,
  onSelectAgent,
}: AgentSelectorProps) {
  const { t } = useTranslation();
  const [showSelector, setShowSelector] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 缓存当前助手对象 - 避免每次渲染都 find
  const currentAgentInfo = useMemo(
    () => agents.find((a) => a.id === currentAgent),
    [agents, currentAgent],
  );

  // 处理选择助手
  const handleSelectAgent = useCallback(
    (agentId: string) => {
      onSelectAgent(agentId);
      setShowSelector(false);
    },
    [onSelectAgent],
  );

  // 切换下拉显示
  const toggleSelector = useCallback(() => {
    setShowSelector((prev) => !prev);
  }, []);

  // 点击外部关闭下拉
  useEffect(() => {
    if (!showSelector) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowSelector(false);
      }
    };

    // 使用 mousedown 而非 click，响应更快
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showSelector]);

  if (agents.length === 0) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(e) => e.stopPropagation()}
    >
      {/* 触发按钮 */}
      <button
        onClick={toggleSelector}
        className="flex items-center gap-1.5 hover:opacity-70 transition-opacity"
      >
        <span className="text-base font-semibold text-gray-700 dark:text-stone-200">
          {t(currentAgentInfo?.name || currentAgent)}
        </span>
        <ChevronDown
          size={18}
          className={`text-gray-400 dark:text-stone-500 transition-transform duration-200 ${
            showSelector ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* 下拉列表 */}
      {showSelector && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
          {agentsLoading ? (
            <div className="px-3 py-2 text-sm text-gray-400 dark:text-stone-500">
              Loading...
            </div>
          ) : (
            agents.map((agent) => (
              <AgentItem
                key={agent.id}
                agent={agent}
                isSelected={agent.id === currentAgent}
                onSelect={() => handleSelectAgent(agent.id)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
});

export { AgentSelector, AgentItem };
