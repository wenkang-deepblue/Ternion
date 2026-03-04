/**
 * ExecutionModeSelector component for Ternion Control Panel.
 *
 * Provides two card-based options for selecting execution mode:
 * - CURSOR_HANDOFF: Ternion RCA + Cursor code implementation (recommended)
 * - TERNION_FULL: Ternion RCA + Ternion code implementation
 * 
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import type { Config } from '../api/client';
import api from '../api/client';
import type { Translations } from '../i18n';

// Section icon
import reasoningIconLight from '../assets/icons/reasoning_light_mode_50dp.svg';
import reasoningIconDark from '../assets/icons/reasoning_dark_mode_50dp.svg';

/**
 * Props for the ExecutionModeSelector component.
 */
interface ExecutionModeSelectorProps {
  /** The current global configuration object, containing the saved execution mode. */
  config: Config | null;
  /** Callback fired when the configuration is successfully updated on the server. */
  onConfigUpdate: (config: Config) => void;
  /** Optional callback to log messages (e.g., user selections) to the UI or parent component. */
  onLogMessage?: (message: string) => void;
  /** Translation function/object for localized strings. */
  t: Translations;
  /** Whether the application is currently in dark mode. */
  isDarkMode: boolean;
}

type ExecutionMode = 'cursor_handoff' | 'ternion_full' | '';

/**
 * Props for the individual ModeCard child component.
 */
interface ModeCardProps {
  /** The title of the execution mode card. */
  title: string;
  /** An optional subtitle or badge text (e.g., 'Recommended'). */
  subtitle?: string;
  /** A list of advantages for this mode. */
  pros: string[];
  /** A list of disadvantages for this mode. */
  cons: string[];
  /** Localized label for the 'pros' section. */
  prosLabel: string;
  /** Localized label for the 'cons' section. */
  consLabel: string;
  /** True if this card represents the currently clicked/pending selection. */
  isSelected: boolean;
  /** True if this card represents the mode saved in backend configuration. */
  isSaved: boolean;
  /** True if the user has selected a mode but hasn't saved it to the backend yet. */
  isPendingSave: boolean;
  /** Callback fired when the card is clicked. */
  onClick: () => void;
  /** Whether the application is currently in dark mode. */
  isDarkMode: boolean;
}

function ModeCard({
  title,
  subtitle,
  pros,
  cons,
  prosLabel,
  consLabel,
  isSelected,
  isSaved,
  isPendingSave,
  onClick,
  isDarkMode,
}: ModeCardProps) {
  // Determine card styling based on state
  const getCardClassNames = () => {
    const outerBaseClasses = `
      relative z-0 isolate rounded-xl transition-all duration-300 cursor-pointer card-rainbow-glow h-full
    `;

    const innerBaseClasses = `
      relative z-10 p-5 rounded-xl border-2 transition-all duration-300 h-full
      ${isDarkMode ? 'bg-slate-800 text-white' : 'bg-white text-slate-900'}
    `;

    if (isSelected) {
      // Selected (pending): animated rainbow glow + slight scale
      const scaleClass = isPendingSave ? 'scale-[1.02]' : 'scale-[1.02]';
      return {
        outer: `${outerBaseClasses} active ${scaleClass}`,
        inner: `${innerBaseClasses} border-transparent`,
      };
    }

    if (isSaved) {
      // Saved: static rainbow border ring (no glow)
      return {
        outer: `${outerBaseClasses} saved`,
        inner: `${innerBaseClasses} rainbow-border-static`,
      };
    }

    // Default state - blue border on hover
    return {
      outer: `${outerBaseClasses}`,
      inner: `${innerBaseClasses} ${isDarkMode ? 'border-slate-600' : 'border-slate-200'} hover:border-[#4083f2]`,
    };
  };

  const { outer, inner } = getCardClassNames();

  return (
    <div className={outer} onClick={onClick}>
      {/* Recommended badge for cursor_handoff */}
      {subtitle && (
        <div className="absolute -top-2 left-4 z-20 px-2 py-0.5 bg-emerald-500 text-white text-xs font-medium rounded">
          {subtitle}
        </div>
      )}

      <div className={inner}>
        {/* Title */}
        <h3 className="text-lg font-semibold mb-3 mt-1">{title}</h3>

        {/* Pros */}
        <div className="mb-3">
          <div className="text-sm font-medium text-emerald-600 dark:text-emerald-400 mb-1">
            {prosLabel}
          </div>
          <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-1">
            {pros.map((pro, i) => (
              <li key={i} className="flex items-start gap-1">
                <span className="text-emerald-500">•</span>
                <span>{pro}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Cons */}
        <div>
          <div className="text-sm font-medium text-amber-600 dark:text-amber-400 mb-1">
            {consLabel}
          </div>
          <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-1">
            {cons.map((con, i) => (
              <li key={i} className="flex items-start gap-1">
                <span className="text-amber-500">•</span>
                <span>{con}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function ExecutionModeSelector({
  config,
  onConfigUpdate,
  onLogMessage,
  t,
  isDarkMode,
}: ExecutionModeSelectorProps) {
  // Saved mode from config
  const savedMode: ExecutionMode = (config?.execution_mode as ExecutionMode) || '';

  // Current selection (may differ from saved)
  const [selectedMode, setSelectedMode] = useState<ExecutionMode>('');
  const [isSaving, setIsSaving] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Determine if a mode is pending save
  const isPendingSave = selectedMode !== '' && selectedMode !== savedMode;

  const getModeDisplayName = useCallback((mode: ExecutionMode): string => {
    return mode === 'cursor_handoff' 
      ? t.execModeCursorTitle
      : t.execModeTernionTitle;
  }, [t.execModeCursorTitle, t.execModeTernionTitle]);

  const handleCardClick = useCallback(async (mode: ExecutionMode) => {
    if (!mode) return;

    // Clicking saved card:
    // - If pending another selection: treat as cancel (matches "click elsewhere including saved card")
    // - Otherwise: do nothing
    if (mode === savedMode) {
      if (isPendingSave) {
        setSelectedMode('');
      }
      return;
    }

    setSelectedMode(mode);
    const modeName = getModeDisplayName(mode);
    onLogMessage?.(`[${modeName}] selected, not saved`);

    // Log to backend (for Logs tab) without persisting
    try {
      await api.logExecutionModeSelection(mode);
    } catch {
      // ignore logging errors
    }
  }, [savedMode, isPendingSave, onLogMessage, getModeDisplayName]);

  const handleSave = useCallback(async () => {
    if (!selectedMode || selectedMode === savedMode) return;

    setIsSaving(true);
    try {
      const updatedConfig = await api.updateConfig({
        execution_mode: selectedMode,
      });
      onConfigUpdate(updatedConfig);
      const modeName = getModeDisplayName(selectedMode);
      onLogMessage?.(`[${modeName}] saved`);
      setSelectedMode(''); // Reset selection after save
    } catch (error) {
      console.error('Failed to save execution mode:', error);
    } finally {
      setIsSaving(false);
    }
  }, [selectedMode, savedMode, onConfigUpdate, onLogMessage, getModeDisplayName]);

  // Click outside -> cancel pending selection (do not change saved state)
  useEffect(() => {
    if (!isPendingSave) return;

    const onDocMouseDown = (e: MouseEvent) => {
      const el = containerRef.current;
      if (!el) return;
      if (el.contains(e.target as Node)) return;
      setSelectedMode('');
    };

    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, [isPendingSave]);

  // Build pros/cons arrays from translations
  const cursorPros = [t.execModeCursorPro1, t.execModeCursorPro2, t.execModeCursorPro3];
  const cursorCons = [t.execModeCursorCon1, t.execModeCursorCon2];
  const ternionPros = [t.execModeTernionPro1, t.execModeTernionPro2, t.execModeTernionPro3];
  const ternionCons = [t.execModeTernionCon1, t.execModeTernionCon2];

  return (
    <div
      className="card"
      ref={containerRef}
    >
      {/* Section Header */}
      <div className="card-header flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <img src={isDarkMode ? reasoningIconDark : reasoningIconLight} alt="" className="w-6 h-6" />
            {t.execModeTitle}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t.execModeDescription}
          </p>
        </div>
        {isPendingSave && (
          <button
            style={{ minWidth: '100px', height: '45px', flexShrink: 0 }}
            className={`btn text-xs whitespace-nowrap ${!isSaving ? 'btn-primary' : 'btn-disabled'}`}
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? t.execModeSaving : t.execModeSave}
          </button>
        )}
      </div>

      {/* Card Body */}
      <div className="card-body">
        {/* Mode Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {/* Cursor Handoff Card (Recommended) */}
          <ModeCard
            title={t.execModeCursorTitle}
            subtitle={t.execModeRecommended}
            pros={cursorPros}
            cons={cursorCons}
            prosLabel={t.execModePros}
            consLabel={t.execModeCons}
            isSelected={selectedMode === 'cursor_handoff'}
            isSaved={savedMode === 'cursor_handoff'}
            isPendingSave={selectedMode === 'cursor_handoff' && savedMode !== 'cursor_handoff'}
            onClick={() => handleCardClick('cursor_handoff')}
            isDarkMode={isDarkMode}
          />

          {/* Ternion Full Card */}
          <ModeCard
            title={t.execModeTernionTitle}
            pros={ternionPros}
            cons={ternionCons}
            prosLabel={t.execModePros}
            consLabel={t.execModeCons}
            isSelected={selectedMode === 'ternion_full'}
            isSaved={savedMode === 'ternion_full'}
            isPendingSave={selectedMode === 'ternion_full' && savedMode !== 'ternion_full'}
            onClick={() => handleCardClick('ternion_full')}
            isDarkMode={isDarkMode}
          />
        </div>
      </div>
    </div>
  );
}

export default ExecutionModeSelector;
