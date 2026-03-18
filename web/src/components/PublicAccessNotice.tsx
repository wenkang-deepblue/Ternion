/**
 * Session-scoped public access reminder for the Control Panel.
 *
 * The notice shows:
 * - an info toast when a usable public URL is already available
 * - an intro modal when public access is missing
 * - a follow-up guide modal with ngrok/Cloud Run guidance
 *
 * Reminder dismissal is stored in sessionStorage to avoid repeating the prompt
 * on every render within the same browser session.
 */

import { useEffect, useRef, useState } from 'react';

import type { PublicAccessStatus } from '../api/client';
import type { Translations } from '../i18n';
import { useToast } from './toastContext';

const REMINDER_STORAGE_KEY = 'ternion-public-access-reminder-dismissed';

interface PublicAccessNoticeProps {
  publicAccess: PublicAccessStatus | null;
  ready: boolean;
  t: Translations;
}

function rememberReminderDismissed(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.sessionStorage.setItem(REMINDER_STORAGE_KEY, '1');
}

function hasReminderBeenDismissed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.sessionStorage.getItem(REMINDER_STORAGE_KEY) === '1';
}

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  ).filter((element) => !element.hasAttribute('disabled'));
}

function PublicAccessModal({
  title,
  body,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
  onRequestClose,
}: {
  title: string;
  body: string;
  primaryLabel: string;
  secondaryLabel?: string;
  onPrimary: () => void;
  onSecondary?: () => void;
  onRequestClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const primaryButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusedElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    previousFocusedElementRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    primaryButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onRequestClose();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const focusableElements = getFocusableElements(dialog);
      if (focusableElements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;

      if (event.shiftKey) {
        if (activeElement === firstElement || !dialog.contains(activeElement)) {
          event.preventDefault();
          lastElement.focus();
        }
        return;
      }

      if (activeElement === lastElement || !dialog.contains(activeElement)) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (previousFocusedElementRef.current?.isConnected) {
        previousFocusedElementRef.current.focus();
      }
    };
  }, [onRequestClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-6 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="public-access-modal-title"
        aria-describedby="public-access-modal-body"
        tabIndex={-1}
        className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-800"
      >
        <h2
          id="public-access-modal-title"
          className="text-lg font-semibold text-slate-900 dark:text-white"
        >
          {title}
        </h2>
        <p
          id="public-access-modal-body"
          className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-600 dark:text-slate-300"
        >
          {body}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          {secondaryLabel && onSecondary && (
            <button type="button" className="btn btn-secondary" onClick={onSecondary}>
              {secondaryLabel}
            </button>
          )}
          <button
            ref={primaryButtonRef}
            type="button"
            className="btn btn-primary"
            onClick={onPrimary}
          >
            {primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PublicAccessNotice({ publicAccess, ready, t }: PublicAccessNoticeProps) {
  const { showToast } = useToast();
  const [introOpen, setIntroOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const hasHandledInitialReminder = useRef(false);

  useEffect(() => {
    if (!ready || !publicAccess || hasHandledInitialReminder.current || hasReminderBeenDismissed()) {
      return;
    }

    hasHandledInitialReminder.current = true;

    if (publicAccess.effective_public_base_url) {
      showToast(t.publicAccessConfiguredToast, 'info');
      rememberReminderDismissed();
      return;
    }

    const timerId = window.setTimeout(() => {
      setIntroOpen(true);
    }, 0);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [publicAccess, ready, showToast, t.publicAccessConfiguredToast]);

  const closeAll = () => {
    setIntroOpen(false);
    setGuideOpen(false);
    rememberReminderDismissed();
  };

  const openGuide = () => {
    setIntroOpen(false);
    setGuideOpen(true);
  };

  if (!introOpen && !guideOpen) {
    return null;
  }

  if (guideOpen) {
    return (
      <PublicAccessModal
        title={t.publicAccessGuideTitle}
        body={t.publicAccessGuideBody}
        primaryLabel={t.publicAccessGuideClose}
        onPrimary={closeAll}
        onRequestClose={closeAll}
      />
    );
  }

  return (
    <PublicAccessModal
      title={t.publicAccessIntroTitle}
      body={t.publicAccessIntroBody}
      primaryLabel={t.publicAccessIntroOk}
      secondaryLabel={t.publicAccessIntroGuide}
      onPrimary={closeAll}
      onSecondary={openGuide}
      onRequestClose={closeAll}
    />
  );
}

export default PublicAccessNotice;
