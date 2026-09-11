// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useAgentComposer } from './useAgentComposer';

function key(k: string, shift = false) {
  return {
    key: k,
    shiftKey: shift,
    preventDefault: vi.fn(),
  } as unknown as KeyboardEvent<HTMLTextAreaElement>;
}

describe('useAgentComposer', () => {
  it('canSend requires a non-blank draft and not disabled', () => {
    const { result } = renderHook(() => useAgentComposer({ disabled: false, onSend: vi.fn() }));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('  hi '));
    expect(result.current.canSend).toBe(true);
  });

  it('submit trims, sends once and clears; blocked while disabled', () => {
    const onSend = vi.fn();
    const { result, rerender } = renderHook(
      ({ disabled }) => useAgentComposer({ disabled, onSend }),
      { initialProps: { disabled: false } },
    );
    act(() => result.current.setDraft('  Draft it  '));
    act(() => result.current.submit());
    expect(onSend).toHaveBeenCalledWith('Draft it');
    expect(result.current.draft).toBe('');

    rerender({ disabled: true });
    act(() => result.current.setDraft('again'));
    act(() => result.current.submit());
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('Enter submits and prevents the newline; Shift+Enter is left to the field', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useAgentComposer({ disabled: false, onSend }));
    act(() => result.current.setDraft('go'));

    const shiftEnter = key('Enter', true);
    act(() => result.current.onKeyDown(shiftEnter));
    expect(shiftEnter.preventDefault).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();

    const enter = key('Enter');
    act(() => result.current.onKeyDown(enter));
    expect(enter.preventDefault).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('go');
  });
});
