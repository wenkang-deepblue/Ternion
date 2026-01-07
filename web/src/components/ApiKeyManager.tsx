/**
 * API Key Manager component for Ternion Control Panel.
 *
 * Provides UI for:
 * - Adding/removing API keys for each provider
 * - Testing API key validity
 * - Selecting active API key per provider
 */

import { useState, useMemo } from 'react';
import api from '../api/client';
import type { Config } from '../api/client';
import { useToast } from './Toast';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';
import type { Language } from '../i18n';

// API Key section icons
import apiKeyIconLight from '../assets/icons/api_key_light_mode_50dp.svg';
import apiKeyIconDark from '../assets/icons/api_key_dark_mode_50dp.svg';

// Provider logos
import geminiLogo from '../assets/icons/gemini_logo.png';
import claudeLogo from '../assets/icons/claude_logo.png';
import openaiLogo from '../assets/icons/openai_logo.png';
import openaiLogoDark from '../assets/icons/openai_logo_dark_mode.png';

// Visibility toggle icon
import visibilityIconLight from '../assets/icons/visibility_light_mode_50dp.svg';
import visibilityIconDark from '../assets/icons/visibility_dark_mode_50dp.svg';

// Delete icon
import deleteIconLight from '../assets/icons/delete_light_mode_50dp.svg';
import deleteIconDark from '../assets/icons/delete_dark_mode_50dp.svg';

interface ApiKeyManagerProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  t: Translations;
  isDarkMode: boolean;
  language: Language;
}

const PROVIDER_INFO = {
  google: {
    placeholder: 'AIza...',
    link: 'https://aistudio.google.com/',
    logo: geminiLogo,
    logoDark: geminiLogo,
  },
  anthropic: {
    placeholder: 'sk-ant-...',
    link: 'https://console.anthropic.com/',
    logo: claudeLogo,
    logoDark: claudeLogo,
  },
  openai: {
    placeholder: 'sk-...',
    link: 'https://platform.openai.com/',
    logo: openaiLogo,
    logoDark: openaiLogoDark,
  },
};

// Provider names and descriptions from i18n
const getProviderInfo = (provider: string, t: Translations) => {
  const providerData = {
    google: { name: t.providerGoogle, desc: t.providerGoogleDesc },
    anthropic: { name: t.providerAnthropic, desc: t.providerAnthropicDesc },
    openai: { name: t.providerOpenai, desc: t.providerOpenaiDesc },
  };
  return providerData[provider as keyof typeof providerData] || { name: provider, desc: '' };
};

// Measure text width using Canvas API (supports CJK characters)
const measureTextWidth = (text: string, font: string = '0.8rem Inter, sans-serif'): number => {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return text.length * 10;
  ctx.font = font;
  return ctx.measureText(text).width;
};

export function ApiKeyManager({ config, onConfigUpdate, t, isDarkMode, language }: ApiKeyManagerProps) {
  const { showToast } = useToast();
  const [newKeys, setNewKeys] = useState<Record<string, { name: string; key: string }>>({
    google: { name: '', key: '' },
    anthropic: { name: '', key: '' },
    openai: { name: '', key: '' },
  });
  const [testing, setTesting] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  // Calculate key name input width based on placeholder text
  const keyNameInputWidth = useMemo(() => {
    const textWidth = measureTextWidth(t.apiKeyPlaceholder);
    return `${Math.max(textWidth + 35, 150)}px`;
  }, [t.apiKeyPlaceholder]);

  const handleNameChange = (provider: string, value: string) => {
    setNewKeys(prev => ({
      ...prev,
      [provider]: { ...prev[provider], name: value },
    }));
  };

  const handleKeyChange = (provider: string, value: string) => {
    setNewKeys(prev => ({
      ...prev,
      [provider]: { ...prev[provider], key: value },
    }));
  };

  const handleTestAndSave = async (provider: string) => {
    const { name, key } = newKeys[provider];
    if (!key) return;

    setTesting(provider);
    try {
      const testResult = await api.testProvider(provider, key);

      if (!testResult.success) {
        // Use global getErrorMessage helper
        let errorMessage = getErrorMessage(t, testResult.code, language);
        
        // If translation is missing (returns code) or it is a connection error, append detail
        if (errorMessage === testResult.code || testResult.code === 'CONNECTION_ERROR') {
           // Clean up common error prefixes from backend message
           const rawMessage = testResult.message || '';
           const cleanMessage = rawMessage.replace(/^(400|500)\s+/, '');
           
           // Fallback: Check message content for auth errors if code check failed
           if (cleanMessage.toLowerCase().includes('not valid') || 
               cleanMessage.toLowerCase().includes('invalid') ||
               cleanMessage.toLowerCase().includes('incorrect')) {
              errorMessage = t.code_AUTH_ERROR;
           } else if (testResult.code === 'CONNECTION_ERROR') {
             errorMessage = `${t.code_CONNECTION_ERROR}: ${cleanMessage}`;
           } else {
             // Fallback to cleaned message if no translation found
             errorMessage = cleanMessage || t.code_UNKNOWN_ERROR;
           }
        }
        
        showToast(errorMessage, 'error');
        setTesting(null);
        return;
      }

      setSaving(true);
      const result = await api.addApiKey(provider, name || t.unnamed, key);
      onConfigUpdate(result.config);

      setNewKeys(prev => ({
        ...prev,
        [provider]: { name: '', key: '' },
      }));

      // Success message with localized provider name
      const { name: providerName } = getProviderInfo(provider, t);
      showToast(`${providerName} ${t.code_SUCCESS}`, 'success');

    } catch (error) {
      console.error('Test API Error:', error);
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setTesting(null);
      setSaving(false);
    }
  };

  const handleSelectKey = async (provider: string, keyId: string) => {
    try {
      const result = await api.selectApiKey(provider, keyId);
      onConfigUpdate(result.config);
      showToast(`${t.apiKeySelected}: ${result.key_name || t.unnamed}`, 'info');
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    }
  };

  const handleDeleteKey = async (provider: string, keyId: string) => {
    if (!confirm(t.confirmDeleteApiKey)) return;

    try {
      const result = await api.deleteApiKey(provider, keyId);
      onConfigUpdate(result.config);
      showToast(t.apiKeyDeleted, 'info');
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <img src={isDarkMode ? apiKeyIconDark : apiKeyIconLight} alt="" className="w-6 h-6" />
          {t.apiKeyTitle}
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {t.apiKeyDescription}
          <span className="text-slate-400 dark:text-slate-500">{t.apiKeyStorageNote}</span>
        </p>
      </div>
      <div className="card-body space-y-6">
        {Object.entries(PROVIDER_INFO).map(([provider, info]) => {
          const status = config?.providers[provider];
          const keys = status?.keys || [];
          const selectedKeyId = status?.selected_key_id;
          const { name: providerName, desc: providerDesc } = getProviderInfo(provider, t);

          return (
            <div
              key={provider}
              className="p-4 rounded-lg border border-slate-200 dark:border-slate-700"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <img src={isDarkMode ? info.logoDark : info.logo} alt={providerName} className="w-6 h-6" />
                    <h3 className="font-medium">{providerName}</h3>
                    {status?.enabled && (
                      <span className="badge badge-success">{t.enabled}</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-500 mt-1">
                    {providerDesc} •{' '}
                    <a
                      href={info.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:underline"
                    >
                      {t.apiKeyGetKey}
                    </a>
                  </p>
                </div>
              </div>

              {/* Existing Keys */}
              {keys.length > 0 && (
                <div className="mb-4 space-y-2">
                  {keys.map((keyInfo) => (
                    <div
                      key={keyInfo.id}
                      className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50"
                    >
                      <input
                        type="radio"
                        name={`${provider}-key`}
                        checked={selectedKeyId === keyInfo.id}
                        onChange={() => handleSelectKey(provider, keyInfo.id)}
                        className="w-4 h-4 text-blue-600 cursor-pointer"
                      />
                      <div className="flex-1 min-w-0">
                        <span className="font-medium text-sm">
                          {keyInfo.name || t.unnamed}
                        </span>
                        <code className="ml-2 px-2 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">
                          {keyInfo.key_preview}
                        </code>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteKey(provider, keyInfo.id)}
                        className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 active:scale-85 cursor-pointer"
                        title={t.delete}
                      >
                        <img src={isDarkMode ? deleteIconDark : deleteIconLight} alt="Delete" className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add New Key */}
              <div className="flex flex-col gap-1">
                <div className="flex gap-2" style={{ marginLeft: '2px' }}>
                  <span className="text-xs text-slate-500 dark:text-slate-400" style={{ width: keyNameInputWidth, minWidth: '150px' }}>{t.apiKeyNameLabel}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400 flex-1">{t.apiKeyLabel}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="input-rainbow-glow" style={{ width: keyNameInputWidth, minWidth: '150px', flexShrink: 0 }}>
                    <input
                      type="text"
                      style={{ width: '100%' }}
                      className="input"
                      placeholder={t.apiKeyPlaceholder}
                      value={newKeys[provider]?.name || ''}
                      onChange={(e) => handleNameChange(provider, e.target.value)}
                    />
                  </div>
                  <div className="relative flex-1 input-rainbow-glow">
                    <input
                      type={showKeys[provider] ? 'text' : 'password'}
                      style={{ width: '100%', paddingRight: '2.5rem' }}
                      className="input"
                      placeholder={info.placeholder}
                      value={newKeys[provider]?.key || ''}
                      onChange={(e) => handleKeyChange(provider, e.target.value)}
                    />
                    <button
                      type="button"
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                      onMouseDown={() => setShowKeys(prev => ({ ...prev, [provider]: true }))}
                      onMouseUp={() => setShowKeys(prev => ({ ...prev, [provider]: false }))}
                      onMouseLeave={() => setShowKeys(prev => ({ ...prev, [provider]: false }))}
                      onTouchStart={() => setShowKeys(prev => ({ ...prev, [provider]: true }))}
                      onTouchEnd={() => setShowKeys(prev => ({ ...prev, [provider]: false }))}
                    >
                      <img src={isDarkMode ? visibilityIconDark : visibilityIconLight} alt="Toggle visibility" className="w-5 h-5" />
                    </button>
                  </div>
                  <button
                    style={{ minWidth: '100px', height: '46px', flexShrink: 0 }}
                    className="btn btn-primary text-xs whitespace-nowrap"
                    onClick={() => handleTestAndSave(provider)}
                    disabled={!newKeys[provider]?.key || testing === provider || saving}
                  >
                    {testing === provider ? t.apiKeyTesting : t.apiKeyTestAndSave}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ApiKeyManager;
