/**
 * Toast notification provider for Ternion Control Panel.
 *
 * Provides context-based toast notifications with:
 * - Success, error, and info message types
 * - Auto-dismiss with fade animations
 * - Multi-line message support
 */

import { useState, createContext, useContext, useCallback, useRef } from 'react';

interface ToastContextType {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
  exiting: boolean;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextIdRef = useRef(0);

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = nextIdRef.current++;
    setToasts(prev => [...prev, { id, message, type, exiting: false }]);

    // Start fade-out after 4.5 seconds (visible for ~5s total including animations)
    setTimeout(() => {
      setToasts(prev =>
        prev.map(t => (t.id === id ? { ...t, exiting: true } : t))
      );
    }, 4500);

    // Remove from DOM after fade-out animation (0.5s)
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container - positioned at screen center */}
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`
            fixed top-1/2 left-1/2 z-[9999]
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
          {toast.type === 'success' && <span className="text-emerald-400">✅</span>}
          {toast.type === 'error' && <span className="text-red-400">❌</span>}
          {toast.type === 'info' && <span className="text-blue-400">ℹ️</span>}
          <span className="font-medium whitespace-pre-line text-left">{toast.message}</span>
        </div>
      ))}
    </ToastContext.Provider>
  );
}

export default ToastProvider;
