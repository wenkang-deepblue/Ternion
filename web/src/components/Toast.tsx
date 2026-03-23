/**
 * Toast notification provider for Ternion Control Panel.
 *
 * Provides context-based toast notifications with:
 * - Success, error, and info message types
 * - Auto-dismiss with fade animations
 * - Multi-line message support
 */

import { useState, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';

// Toast icons
import checkIcon from '../assets/icons/check.svg';
import errorIcon from '../assets/icons/error.svg';
import infoIcon from '../assets/icons/information.svg';
import { ToastContext } from './toastContext';
import type { ToastType } from './toastContext';

/**
 * Internal state representation of a single toast notification.
 */
interface Toast {
  /** Unique identifier for the toast. */
  id: number;
  /** The message text to display. */
  message: string;
  /** The visual type of the toast. */
  type: ToastType;
  /** True if the toast is currently animating out before removal. */
  exiting: boolean;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextIdRef = useRef(0);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextIdRef.current++;
    setToasts(prev => [...prev, { id, message, type, exiting: false }]);

    // Start fade-out after 2 seconds.
    setTimeout(() => {
      setToasts(prev =>
        prev.map(t => (t.id === id ? { ...t, exiting: true } : t))
      );
    }, 2000);

    // Remove from DOM after fade-out animation (~0.5s).
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 2500);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container - positioned at screen center */}
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`
            fixed top-1/2 left-1/2 z-9999
            px-5 py-2.5 rounded-[10px]
            bg-[rgba(50,50,50,0.9)] text-white text-center
            shadow-lg backdrop-blur-sm
            min-w-[200px]
            flex items-center justify-center gap-2
            ${toast.exiting ? 'animate-fade-out' : 'animate-fade-in'}
          `}
          style={{
            transform: 'translate(-50%, -50%)',
          }}
        >
          {toast.type === 'success' && <img src={checkIcon} alt="" className="w-5 h-5" />}
          {toast.type === 'error' && <img src={errorIcon} alt="" className="w-5 h-5" />}
          {toast.type === 'info' && <img src={infoIcon} alt="" className="w-5 h-5" />}
          <span className="font-medium whitespace-pre-line text-center">{toast.message}</span>
        </div>
      ))}
    </ToastContext.Provider>
  );
}

export default ToastProvider;
