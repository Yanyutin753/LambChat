/** Local fixtures using production controls; no upload, delete, or API writes. */
import { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Download, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { Button } from "../src/components/common/ui/Button";
import { IconButton } from "../src/components/common/ui/IconButton";
import { AttachmentCard } from "../src/components/common/AttachmentCard";
import { ResourceCardMenu } from "../src/components/common/ResourceCardMenu";
import type { MessageAttachment } from "../src/types";
import "../src/fonts.css";
import "../src/styles/tailwind.css";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/animations.css";
void import("../src/fonts-cjk");
const params = new URLSearchParams(location.search);
const theme = params.get("theme");
applyThemeToDocument(isTheme(theme) ? theme : "light");
await i18n.changeLanguage(params.get("lang") || "zh");
const files: MessageAttachment[] = [
  {
    id: "report",
    key: "",
    name: "季度研究报告.pdf",
    mimeType: "application/pdf",
    type: "document",
    size: 248576,
  },
  {
    id: "notes",
    key: "",
    name: "产品访谈记录与下一季度改进计划.txt",
    mimeType: "text/plain",
    type: "document",
    size: 4096,
  },
];

export function ControlsPreview() {
  const [attachments, setAttachments] = useState(files);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [status, setStatus] = useState(
    "点击附件可预览；此页操作仅影响本地演示。",
  );
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <main className="mx-auto max-w-4xl space-y-8 p-5 sm:p-10 text-theme-text">
      <header className="space-y-3">
        <p className="text-12 text-theme-text-secondary">LambChat · 组件预览</p>
        <h1 className="text-24 font-semibold">按钮、菜单与附件</h1>
        <div className="flex flex-wrap gap-3 text-13">
          <a href="?theme=light">浅色</a>
          <a href="?theme=dark">深色</a>
          <a href="?theme=sepia">暖色</a>
          <a href="/chat/preview-report">进入聊天</a>
          <a href="/skills">查看资源菜单</a>
        </div>
      </header>
      <section className="space-y-4">
        <h2 className="text-16 font-medium">共享按钮</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            leftIcon={<Plus size={16} />}
            onClick={() => setStatus("已触发创建操作（演示）")}
          >
            {i18n.t("common.create")}
          </Button>
          <Button onClick={() => setStatus("已触发保存操作（演示）")}>
            {i18n.t("common.save")}
          </Button>
          <Button variant="ghost">{i18n.t("common.cancel")}</Button>
          <Button variant="danger">{i18n.t("common.delete")}</Button>
          <Button disabled>{i18n.t("common.save")}</Button>
          <Button loading>{i18n.t("common.save")}</Button>
          <IconButton
            aria-label={i18n.t("documents.download")}
            icon={<Download size={16} />}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </div>
      </section>
      <section className="space-y-4">
        <h2 className="text-16 font-medium">共享菜单</h2>
        <button
          ref={trigger}
          type="button"
          className="ui-button ui-button--secondary ui-button--md"
          aria-haspopup="menu"
          aria-expanded={!!menu}
          aria-controls={menu ? "controls-menu" : undefined}
          onClick={() => {
            const rect = trigger.current!.getBoundingClientRect();
            setMenu({ x: rect.left, y: rect.bottom + 6 });
          }}
        >
          <MoreHorizontal size={16} />
          {i18n.t("nav.more")}
        </button>
        {menu && (
          <ResourceCardMenu
            id="controls-menu"
            title={i18n.t("nav.more")}
            position={menu}
            onClose={(restore) => {
              setMenu(null);
              if (restore) trigger.current?.focus();
            }}
            actions={[
              {
                label: i18n.t("common.edit"),
                icon: <Pencil />,
                onClick: () => setStatus("已选择编辑（演示）"),
              },
              {
                label: i18n.t("documents.download"),
                icon: <Download />,
                onClick: () => setStatus("已选择下载（演示）"),
              },
              {
                label: i18n.t("common.save"),
                disabled: true,
                onClick: () => {},
              },
              {
                label: i18n.t("common.delete"),
                icon: <Trash2 />,
                danger: true,
                separatorBefore: true,
                onClick: () => setStatus("已选择删除（演示）"),
              },
            ]}
          />
        )}
      </section>
      <section className="space-y-4">
        <h2 className="text-16 font-medium">消息附件</h2>
        <div className="flex flex-wrap gap-3">
          {files.map((attachment) => (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              onClick={() => setStatus(attachment.name)}
            />
          ))}
        </div>
      </section>
      <section className="space-y-4">
        <h2 className="text-16 font-medium">输入框附件与上传状态</h2>
        <div className="flex flex-wrap gap-3">
          {attachments.map((attachment) => (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              size="compact"
              variant="editable"
              onClick={() => setStatus(attachment.name)}
              onRemove={() =>
                setAttachments((items) =>
                  items.filter((item) => item.id !== attachment.id),
                )
              }
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          <AttachmentCard
            attachment={{
              ...files[0],
              uploadStage: "processing",
              uploadProcessingProgress: 46,
            }}
            size="compact"
            variant="editable"
            isUploading
            onCancel={() => setStatus("已取消上传（演示）")}
          />
          <AttachmentCard
            attachment={{ ...files[1], uploadError: "Fixture upload failed" }}
            size="compact"
            variant="editable"
            onClick={() => setStatus(files[1].name)}
            onRetry={() => setStatus("已重试上传（演示）")}
            onRemove={() => setStatus("已移除失败附件（演示）")}
          />
        </div>
      </section>
      <p role="status" className="text-13 text-theme-text-secondary">
        {status}
      </p>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<ControlsPreview />);
