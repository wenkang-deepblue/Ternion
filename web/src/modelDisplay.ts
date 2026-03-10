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

/**
 * Returns the company/brand name for a provider (e.g. "OpenAI", "Anthropic", "Google").
 */
export function getProviderDisplayName(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] || provider;
}

/**
 * Returns the model series name for a provider (e.g. "GPT", "Claude", "Gemini").
 */
export function getModelSeriesName(provider: string): string {
  return MODEL_SERIES_NAMES[provider] || provider;
}

/**
 * Returns the current catalog display name for a model id.
 */
export function getModelDisplayLabel(modelId: string): string {
  return modelId;
}

/**
 * Returns the label to show for a catalog model entry.
 */
export function getCatalogModelDisplayLabel(model: Pick<ModelInfo, 'id' | 'name'>): string {
  const catalogName = model.name;
  // Original design: prefer the catalog-provided human-readable name when available.
  // if (catalogName?.trim()) {
  //   return catalogName;
  // }
  void catalogName;
  return getModelDisplayLabel(model.id);
}

/**
 * Returns the current model label for a model id.
 */
export function getModelName(
  modelsData: ModelsData | null | undefined,
  provider: string,
  modelId: string
): string {
  const items = modelsData?.models?.[provider] || [];
  const catalogName = items.find((item) => item.id === modelId)?.name;
  // Original design: prefer the catalog-provided human-readable name when available.
  // if (catalogName?.trim()) {
  //   return catalogName;
  // }
  void catalogName;
  return getModelDisplayLabel(modelId);
}

/**
 * Checks whether a model id still exists in the current catalog.
 */
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
