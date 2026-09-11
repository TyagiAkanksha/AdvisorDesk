// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useRisingEdgeNotice } from '.';

describe('useRisingEdgeNotice', () => {
  it('does not fire on mount, even when `active` starts true', () => {
    const notify = vi.fn();

    renderHook(() => useRisingEdgeNotice(true, notify, 'boom'));

    expect(notify).not.toHaveBeenCalled();
  });

  it('does not fire on mount when `active` starts false', () => {
    const notify = vi.fn();

    renderHook(() => useRisingEdgeNotice(false, notify, 'boom'));

    expect(notify).not.toHaveBeenCalled();
  });

  it('fires once on a false -> true transition (a failure episode)', () => {
    const notify = vi.fn();
    const { rerender } = renderHook(({ active }) => useRisingEdgeNotice(active, notify, 'boom'), {
      initialProps: { active: false },
    });

    rerender({ active: true });

    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('boom');
  });

  it('does not re-fire while `active` stays true across renders (a sustained failure)', () => {
    const notify = vi.fn();
    const { rerender } = renderHook(({ active }) => useRisingEdgeNotice(active, notify, 'boom'), {
      initialProps: { active: false },
    });

    rerender({ active: true });
    rerender({ active: true });
    rerender({ active: true });

    expect(notify).toHaveBeenCalledTimes(1);
  });

  it('fires again after recovery (true -> false -> true is a second episode)', () => {
    const notify = vi.fn();
    const { rerender } = renderHook(({ active }) => useRisingEdgeNotice(active, notify, 'boom'), {
      initialProps: { active: false },
    });

    rerender({ active: true });
    rerender({ active: false });
    rerender({ active: true });

    expect(notify).toHaveBeenCalledTimes(2);
  });
});
