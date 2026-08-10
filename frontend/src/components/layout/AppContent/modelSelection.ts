export interface ModelSelectionOption {
  id: string;
  value: string;
}

export interface ModelSelection {
  modelId: string;
  modelValue: string;
}

interface ModelSelectionCandidate {
  modelId?: string;
  modelValue?: string;
}

interface ResolveModelSelectionArgs {
  availableModels?: ModelSelectionOption[] | null;
  sessionModelId?: string;
  sessionModelValue?: string;
  userDefaultId?: string;
  userDefaultValue?: string;
  systemDefaultId?: string;
  systemDefaultValue?: string;
}

const EMPTY_SELECTION: ModelSelection = {
  modelId: "",
  modelValue: "",
};

function normalizeCandidate({
  modelId,
  modelValue,
}: ModelSelectionCandidate): ModelSelection {
  return {
    modelId: modelId?.trim() || "",
    modelValue: modelValue?.trim() || "",
  };
}

function firstRawCandidate(
  candidates: ModelSelectionCandidate[],
): ModelSelection {
  return (
    candidates.map(normalizeCandidate).find((item) => {
      return item.modelId || item.modelValue;
    }) ?? EMPTY_SELECTION
  );
}

function resolveCandidate(
  availableModels: ModelSelectionOption[],
  candidate: ModelSelectionCandidate,
): ModelSelection | null {
  const normalized = normalizeCandidate(candidate);

  if (normalized.modelId) {
    const idMatch = availableModels.find(
      (model) => model.id === normalized.modelId,
    );
    if (idMatch) {
      return { modelId: idMatch.id, modelValue: idMatch.value };
    }
  }

  if (!normalized.modelValue) return null;

  const valueMatches = availableModels.filter(
    (model) => model.value === normalized.modelValue,
  );
  if (valueMatches.length !== 1) return null;

  return {
    modelId: valueMatches[0].id,
    modelValue: valueMatches[0].value,
  };
}

export function resolveModelSelection({
  availableModels,
  sessionModelId,
  sessionModelValue,
  userDefaultId,
  userDefaultValue,
  systemDefaultId,
  systemDefaultValue,
}: ResolveModelSelectionArgs): ModelSelection {
  const candidates = [
    { modelId: sessionModelId, modelValue: sessionModelValue },
    { modelId: userDefaultId, modelValue: userDefaultValue },
    { modelId: systemDefaultId, modelValue: systemDefaultValue },
  ];

  if (availableModels == null) {
    return firstRawCandidate(candidates);
  }

  if (availableModels.length === 0) {
    return EMPTY_SELECTION;
  }

  for (const candidate of candidates) {
    const resolved = resolveCandidate(availableModels, candidate);
    if (resolved) return resolved;
  }

  const firstModel = availableModels[0];
  return { modelId: firstModel.id, modelValue: firstModel.value };
}
