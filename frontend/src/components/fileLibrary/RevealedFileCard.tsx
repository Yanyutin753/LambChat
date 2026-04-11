import type { RevealedFileItem } from "../../services/api";
import { GridCard } from "./components/GridCard";
import { ListCard } from "./components/ListCard";

interface RevealedFileCardProps {
  file: RevealedFileItem;
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
  viewMode?: "grid" | "list";
}

export function RevealedFileCard({
  file,
  onPreview,
  onGoToSession,
  onToggleFavorite,
  viewMode = "grid",
}: RevealedFileCardProps) {
  if (viewMode === "list") {
    return (
      <ListCard
        file={file}
        onPreview={onPreview}
        onGoToSession={onGoToSession}
        onToggleFavorite={onToggleFavorite}
      />
    );
  }

  return (
    <GridCard
      file={file}
      onPreview={onPreview}
      onGoToSession={onGoToSession}
      onToggleFavorite={onToggleFavorite}
    />
  );
}
