import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PublicAccessStatus } from '../api/client';
import { getTranslations } from '../i18n';
import { PublicAccessNotice } from './PublicAccessNotice';
import { ToastContext } from './toastContext';

function buildPublicAccess(overrides?: Partial<PublicAccessStatus>): PublicAccessStatus {
  return {
    mode: 'local_tunnel',
    deployment_environment: 'local',
    detection_method: 'manual_config',
    detected_public_base_url: '',
    configured_public_base_url: 'https://demo.ngrok.app',
    effective_public_base_url: 'https://demo.ngrok.app',
    effective_source: 'config',
    cursor_override_base_url: 'https://demo.ngrok.app',
    configured: true,
    requires_public_url: true,
    ...overrides,
  };
}

function renderNotice(publicAccess: PublicAccessStatus | null, ready = true) {
  const t = getTranslations('zh');
  const showToast = vi.fn();

  const utils = render(
    <ToastContext.Provider value={{ showToast }}>
      <PublicAccessNotice publicAccess={publicAccess} ready={ready} t={t} />
    </ToastContext.Provider>
  );

  return { t, showToast, ...utils };
}

describe('PublicAccessNotice', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('shows an info toast when public access is already available', async () => {
    const { t, showToast } = renderNotice(buildPublicAccess());

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledWith(t.publicAccessConfiguredToast, 'info');
    });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the guide modal when public access is missing and the user requests help', async () => {
    const user = userEvent.setup();
    const { t, showToast } = renderNotice(
      buildPublicAccess({
        configured_public_base_url: '',
        effective_public_base_url: '',
        effective_source: 'none',
        cursor_override_base_url: '',
        configured: false,
      })
    );

    expect(await screen.findByText(t.publicAccessIntroTitle)).toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: t.publicAccessIntroGuide }));

    expect(await screen.findByText(t.publicAccessGuideTitle)).toBeInTheDocument();
  });

  it('closes the intro modal with the primary action and does not show it again in the same session', async () => {
    const user = userEvent.setup();
    const missingPublicAccess = buildPublicAccess({
      configured_public_base_url: '',
      effective_public_base_url: '',
      effective_source: 'none',
      cursor_override_base_url: '',
      configured: false,
    });

    const { t, unmount } = renderNotice(missingPublicAccess);

    expect(await screen.findByText(t.publicAccessIntroTitle)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.publicAccessIntroOk }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    unmount();
    renderNotice(missingPublicAccess);

    await waitFor(() => {
      expect(screen.queryByText(t.publicAccessIntroTitle)).not.toBeInTheDocument();
    });
  });

  it('closes the modal when Escape is pressed', async () => {
    const user = userEvent.setup();
    const { t } = renderNotice(
      buildPublicAccess({
        configured_public_base_url: '',
        effective_public_base_url: '',
        effective_source: 'none',
        cursor_override_base_url: '',
        configured: false,
      })
    );

    expect(await screen.findByText(t.publicAccessIntroTitle)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.publicAccessIntroOk })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole('button', { name: t.publicAccessIntroGuide })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole('button', { name: t.publicAccessIntroOk })).toHaveFocus();

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
