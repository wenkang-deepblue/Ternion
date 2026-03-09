import type { ModelsData } from './api/client';

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
export function getModelName(
  modelsData: ModelsData | null | undefined,
  provider: string,
  modelId: string
): string {
  const items = modelsData?.models?.[provider] || [];
  return items.find((item) => item.id === modelId)?.name || modelId;
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
