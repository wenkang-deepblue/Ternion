import type { ModelInfo, ModelsData } from './api/client';

const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  google: 'Google',
  anthropic: 'Anthropic',
  openai: 'OpenAI',
};

const MODEL_SERIES_NAMES: Record<string, string> = {
  google: 'Gemini',
  anthropic: 'Claude',
  openai: 'GPT',
};

export function getProviderDisplayName(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] || provider;
}

export function getModelSeriesName(provider: string): string {
  return MODEL_SERIES_NAMES[provider] || provider;
}

export function getModelDisplayLabel(modelId: string): string {
  return modelId;
}

export function getCatalogModelDisplayLabel(model: Pick<ModelInfo, 'id' | 'name'>): string {
  const catalogName = model.name;
  void catalogName;
  return getModelDisplayLabel(model.id);
}

export function getModelName(
  modelsData: ModelsData | null | undefined,
  provider: string,
  modelId: string
): string {
  const items = modelsData?.models?.[provider] || [];
  const catalogName = items.find((item) => item.id === modelId)?.name;
  void catalogName;
  return getModelDisplayLabel(modelId);
}

export function isModelAvailableInCatalog(
  modelsData: ModelsData | null | undefined,
  provider: string,
  modelId: string
): boolean {
  if (!provider || !modelId) {
    return false;
  }
  return (modelsData?.models?.[provider] || []).some((item) => item.id === modelId);
}
