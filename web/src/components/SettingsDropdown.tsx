/**
 * Settings Dropdown component for Ternion Control Panel.
 *
 * Provides theme and language configuration via dropdown menu.
 * Features:
 * - Theme switcher (light/dark/system)
 * - Language selector (auto/en/zh)
 * - Persists preferences to backend
 */

import { useState, useRef, useEffect } from 'react';
import type { Translations } from '../i18n';
import api from '../api/client';

// Settings icons for light/dark mode with normal/hover states
import settingsLightNormal from '../assets/icons/settings_light_mode_50dp.svg';
import settingsLightHover from '../assets/icons/settings_light_mode_hover_50dp.svg';
import settingsDarkNormal from '../assets/icons/settings_dark_mode_normal_50dp.svg';
import settingsDarkHover from '../assets/icons/settings_dark_mode_hover_50dp.svg';

// Theme icons for light/dark mode
import lightIconLight from '../assets/icons/light_light_mode_50dp.svg';
import lightIconDark from '../assets/icons/light_dark_mode_50dp.svg';
import darkIconLight from '../assets/icons/dark_light_mode_50dp.svg';
import darkIconDark from '../assets/icons/dark_dark_mode_50dp.svg';
import computerIconLight from '../assets/icons/computer_light_mode_50dp.svg';
import computerIconDark from '../assets/icons/computer_dark_mode_50dp.svg';

export type ThemeMode = 'light' | 'dark' | 'system';
export type LanguageMode = 'auto' | 'en' | 'zh' | 'es' | 'fr' | 'de' | 'ja' | 'ko';

/**
 * Props for the SettingsDropdown component.
 */
interface SettingsDropdownProps {
  /** Translation function/object for localized strings. */
  t: Translations;
  /** The currently selected theme mode. */
  theme: ThemeMode;
  /** The currently selected language mode. */
  language: LanguageMode;
  /** Whether the application is currently in dark mode. */
  isDarkMode: boolean;
  /** Callback fired when the user selects a new theme. */
  onThemeChange: (theme: ThemeMode) => void;
  /** Callback fired when the user selects a new language. */
  onLanguageChange: (language: LanguageMode) => void;
}

export function SettingsDropdown({
  t,
  theme,
  language,
  isDarkMode,
  onThemeChange,
  onLanguageChange,
}: SettingsDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Get the appropriate settings icon based on dark mode and hover state
  const getSettingsIcon = () => {
    if (isDarkMode) {
      return isHovered ? settingsDarkHover : settingsDarkNormal;
    }
    return isHovered ? settingsLightHover : settingsLightNormal;
  };

  // Close dropdown on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Calculate glider position based on theme
  const getGliderPosition = () => {
    switch (theme) {
      case 'light': return 'translate-x-[0%]';
      case 'dark': return 'translate-x-[100%]';
      case 'system': return 'translate-x-[200%]';
      default: return 'translate-x-[200%]';
    }
  };

  // Get theme icon based on current dark mode
  const getThemeIcon = (themeValue: ThemeMode) => {
    switch (themeValue) {
      case 'light':
        return isDarkMode ? lightIconDark : lightIconLight;
      case 'dark':
        return isDarkMode ? darkIconDark : darkIconLight;
      case 'system':
        return isDarkMode ? computerIconDark : computerIconLight;
    }
  };

  const themeOptions: { value: ThemeMode; label: string }[] = [
    { value: 'light', label: t.settingsThemeLight },
    { value: 'dark', label: t.settingsThemeDark },
    { value: 'system', label: t.settingsThemeSystem },
  ];

  const languageOptions: { value: LanguageMode; label: string }[] = [
    { value: 'auto', label: t.settingsLanguageAuto },
    { value: 'en', label: 'English' },
    { value: 'zh', label: '中文' },
    { value: 'es', label: 'Español' },
    { value: 'fr', label: 'Français' },
    { value: 'de', label: 'Deutsch' },
    { value: 'ja', label: '日本語' },
    { value: 'ko', label: '한국어' },
  ];

  const [isLangMenuOpen, setIsLangMenuOpen] = useState(false);
  const langMenuRef = useRef<HTMLDivElement>(null);

  // Close language menu on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (langMenuRef.current && !langMenuRef.current.contains(event.target as Node)) {
        setIsLangMenuOpen(false);
      }
    };
    if (isLangMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isLangMenuOpen]);

  const currentLanguageLabel = languageOptions.find(opt => opt.value === language)?.label || language;

  return (
    <div ref={dropdownRef} className="relative">
      {/* Settings Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-all duration-200 active:scale-85 hover:scale-110"
        title={t.settingsTitle}
      >
        <img
          src={getSettingsIcon()}
          alt={t.settingsTitle}
          className="w-6 h-6 transition-opacity"
        />
      </button>

      {/* Dropdown Menu */}
      <div
        className={`absolute right-0 top-full mt-2 w-68 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 p-4 z-50 origin-top-right transition-transform duration-300 ease-in-out will-change-transform ${isOpen
            ? 'scale-100 translate-y-0 translate-x-0'
            : 'scale-0 -translate-y-2 translate-x-2 pointer-events-none'
          }`}
      >
        {/* Theme Section */}
        <div className="mb-5">
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wide">
            {t.settingsTheme}
          </div>
          {/* Sliding Segmented Control */}
          <div className="relative flex p-1 bg-slate-100 dark:bg-slate-700 rounded-lg isolate">
            {/* Glider */}
            <div
              className={`absolute top-1 bottom-1 w-[calc((100%-0.5rem)/3)] bg-white dark:bg-slate-600 shadow rounded-md transition-transform duration-300 ease-in-out ${getGliderPosition()}`}
              style={{ left: '4px', zIndex: 0 }}
            />
            {/* Buttons */}
            {themeOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => onThemeChange(option.value)}
                className={`relative z-10 flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md text-sm transition-colors duration-200 ${theme === option.value
                    ? 'text-blue-600 dark:text-blue-400 font-medium'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                title={option.label}
              >
                <img src={getThemeIcon(option.value)} alt={option.label} className="w-5 h-5" />
              </button>
            ))}
          </div>
        </div>

        {/* Language Section (Custom Dropdown) */}
        <div className="relative" ref={langMenuRef}>
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wide">
            Language
          </div>

          <button
            onClick={() => setIsLangMenuOpen(!isLangMenuOpen)}
            className="w-full flex items-center justify-between px-3 py-2 bg-slate-100 dark:bg-slate-700 rounded-lg text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          >
            <span>{currentLanguageLabel}</span>
            <span className={`transform transition-transform duration-200 ${isLangMenuOpen ? 'rotate-180' : ''}`}>
              ▼
            </span>
          </button>

          {/* Animated Options List */}
          <div
            className={`absolute top-full left-0 w-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg overflow-hidden z-20 origin-top transition-all duration-200 ease-out ${isLangMenuOpen
                ? 'opacity-100 scale-y-100'
                : 'opacity-0 scale-y-0 pointer-events-none'
              }`}
          >
            {languageOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  onLanguageChange(option.value);
                  setIsLangMenuOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 ${language === option.value
                    ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 font-medium'
                    : 'text-slate-700 dark:text-slate-200'
                  }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Config File Note */}
        <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700">
          <p className="text-xs text-slate-400 dark:text-slate-500 leading-relaxed">
            {t.settingsConfigLabel}:{' '}
            <button
              onClick={() => api.revealFile('~/.ternion/config.json').catch(console.error)}
              className="text-blue-500 dark:text-blue-400 hover:text-blue-600 dark:hover:text-blue-300 underline underline-offset-2 cursor-pointer transition-colors"
              title={t.logsOpenFile}
            >
              ~/.ternion/config.json
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default SettingsDropdown;
