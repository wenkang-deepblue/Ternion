/**
 * Toast context definitions for Ternion Control Panel.
 *
 * Provides the types and context for global toast notifications.
 */
import { createContext, useContext } from 'react';

/**
 * Defines the visual type and icon of the toast message.
 */
export type ToastType = 'success' | 'error' | 'info';

/**
 * The shape of the toast context value provided to consumers.
 */
export interface ToastContextType {
  /**
   * Displays a global toast notification.
   * @param message - The content of the notification to display
   * @param type - The visual severity type (defaults to 'info')
   */
  showToast: (message: string, type?: ToastType) => void;
}

export const ToastContext = createContext<ToastContextType | null>(null);

/**
 * Custom hook to access the global toast notification context.
 * Must be used within a component wrapped by ToastProvider.
 * 
 * @returns The toast context containing the showToast method
 * @throws Error if used outside of a ToastProvider
 */
export function useToast(): ToastContextType {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}

