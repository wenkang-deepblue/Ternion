/**
 * Main application component for Ternion Control Panel.
 *
 * Integrates all sub-components and provides:
 * - i18n language support with preferences persistence
 * - Theme switching (light/dark/system)
 * - Configuration status bar
 * - Tab navigation
 */

import { useState, useEffect, useCallback } from 'react';
import api from './api/client';
import type { Config, ServerStatus } from './api/client';
import { ToastProvider } from './components/Toast';
import StatusBar from './components/StatusBar';
import ApiKeyManager from './components/ApiKeyManager';
import RoleModelConfig from './components/RoleModelConfig';
import BudgetSettings from './components/BudgetSettings';
import PortsSettings from './components/PortsSettings';
import UsageDashboard from './components/UsageDashboard';
import ObservabilityPanel from './components/ObservabilityPanel';
import SettingsDropdown from './components/SettingsDropdown';
import type { ThemeMode, LanguageMode } from './components/SettingsDropdown';
import { detectBrowserLanguage, getTranslations } from './i18n';
import type { Language } from './i18n';
import './index.css';
import ternionLogo from './assets/icons/ternion-logo-light.png';
import ternionLogoDark from './assets/icons/ternion-logo-dark.png';

// Tab icons for light/dark mode
import configIconLight from './assets/icons/configuration_light_mode_50dp.svg';
import configIconDark from './assets/icons/configuration_dark_mode_50dp.svg';
import portIconLight from './assets/icons/port_light_mode_50dp.svg';
import portIconDark from './assets/icons/port_dark_mode_50dp.svg';
import usageIconLight from './assets/icons/usage_light_mode_50dp.svg';
import usageIconDark from './assets/icons/usage_dark_mode_50dp.svg';
import logIconLight from './assets/icons/log_light_mode_dp50.svg';
import logIconDark from './assets/icons/log_dark_mode_dp50.svg';

function AppContent() {
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [activeTab, setActiveTab] = useState<'config' | 'ports' | 'usage' | 'logs'>('config');

  // Preference states
  const [themeMode, setThemeMode] = useState<ThemeMode>('system');
  const [languageMode, setLanguageMode] = useState<LanguageMode>('auto');

  // Computed language for i18n
  const effectiveLanguage: Language =
    languageMode === 'auto' ? detectBrowserLanguage() : languageMode;
  const t = getTranslations(effectiveLanguage);

  // Computed dark mode based on theme preference
  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false
  );

  const isDarkMode =
    themeMode === 'dark' || (themeMode === 'system' && systemDark);

  // Listen for system theme changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  // Apply dark mode class
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDarkMode);
  }, [isDarkMode]);

  // Load initial data and preferences
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [configData, statusData] = await Promise.all([
        api.getConfig(),
        api.getStatus(),
      ]);
      setConfig(configData);
      setStatus(statusData);

      // Load preferences from config
      if (configData?.preferences) {
        if (configData.preferences.theme) {
          setThemeMode(configData.preferences.theme as ThemeMode);
        }
        if (configData.preferences.language) {
          setLanguageMode(configData.preferences.language as LanguageMode);
        }
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  };

  const handleConfigUpdate = (newConfig: Config) => {
    setConfig(newConfig);
    api.getStatus().then(setStatus).catch(console.error);
  };

  const handleThemeChange = useCallback(async (theme: ThemeMode) => {
    setThemeMode(theme);
    try {
      await api.updatePreferences({ theme });
    } catch (error) {
      console.error('Failed to save theme preference:', error);
    }
  }, []);

  const handleLanguageChange = useCallback(async (language: LanguageMode) => {
    setLanguageMode(language);
    try {
      await api.updatePreferences({ language });
    } catch (error) {
      console.error('Failed to save language preference:', error);
    }
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src={isDarkMode ? ternionLogoDark : ternionLogo} alt="Ternion" className="h-20" />
              <div>
                <h1 className="text-xl font-bold text-slate-900 dark:text-white">
                  {t.appTitle}
                </h1>
                <p className="text-sm text-slate-500">
                  {t.appSubtitle}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Status Badge */}
              {status && (
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      status.provider_count > 0
                        ? 'bg-emerald-500 animate-pulse'
                        : 'bg-yellow-500'
                    }`}
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    {status.provider_count} {t.llmKeysEnabled}
                  </span>
                </div>
              )}
              {/* Settings Dropdown */}
              <SettingsDropdown
                t={t}
                theme={themeMode}
                language={languageMode}
                isDarkMode={isDarkMode}
                onThemeChange={handleThemeChange}
                onLanguageChange={handleLanguageChange}
              />
            </div>
          </div>
        </div>

        {/* Status Bar */}
        <StatusBar config={config} t={t} />

        {/* Tabs */}
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex gap-1 -mb-px">
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'config'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('config')}
            >
              <img src={isDarkMode ? configIconDark : configIconLight} alt="" className="w-5 h-5" />
              {t.tabConfig}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'ports'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('ports')}
            >
              <img src={isDarkMode ? portIconDark : portIconLight} alt="" className="w-5 h-5" />
              {t.tabPorts}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'usage'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('usage')}
            >
              <img src={isDarkMode ? usageIconDark : usageIconLight} alt="" className="w-5 h-5" />
              {t.tabUsage}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'logs'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('logs')}
            >
              <img src={isDarkMode ? logIconDark : logIconLight} alt="" className="w-5 h-5" />
              {t.tabLogs}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {activeTab === 'config' && (
          <div className="space-y-6">
            <ApiKeyManager config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} />
            <RoleModelConfig config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} />
            <BudgetSettings config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} />
          </div>
        )}
        {activeTab === 'ports' && <PortsSettings t={t} isDarkMode={isDarkMode} />}
        {activeTab === 'usage' && <UsageDashboard t={t} isDarkMode={isDarkMode} onConfigUpdate={handleConfigUpdate} />}
        {activeTab === 'logs' && <ObservabilityPanel t={t} isDarkMode={isDarkMode} />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-700 py-6 mt-12">
        <div className="max-w-5xl mx-auto px-4 text-center text-sm text-slate-500">
          <p>
            Ternion v0.4.8 • {t.appSubtitle} •{' '}
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              {t.footerApiDocs}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;
