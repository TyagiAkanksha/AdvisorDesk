// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useChatComposer } from './useChatComposer';

const key = (overrides: Partial<KeyboardEvent<HTMLTextAreaElement>>) =>
  ({
    key: 'Enter',
    shiftKey: false,
    preventDefault: vi.fn(),
    ...overrides,
  }) as unknown as KeyboardEvent<HTMLTextAreaElement>;

describe('useChatComposer', () => {
  it('cannot send an empty or whitespace draft, and sends the trimmed draft then clears it', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: false, onSend }));

    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('   '));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('  Hello  '));
    expect(result.current.canSend).toBe(true);
    act(() => result.current.submit());

    expect(onSend).toHaveBeenCalledWith('Hello');
    expect(result.current.draft).toBe('');
  });

  it('Enter submits and prevents the newline; Shift+Enter is left to the field', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: false, onSend }));
    act(() => result.current.setDraft('Q'));

    const enter = key({});
    act(() => result.current.onKeyDown(enter));
    expect(enter.preventDefault).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('Q');

    act(() => result.current.setDraft('multi'));
    const shiftEnter = key({ shiftKey: true });
    act(() => result.current.onKeyDown(shiftEnter));
    expect(shiftEnter.preventDefault).not.toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('never sends while disabled', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: true, onSend }));
    act(() => result.current.setDraft('Q'));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.submit());
    expect(onSend).not.toHaveBeenCalled();
  });

  // fix round 1 (M-1): the Enter that confirms an IME composition (e.g. a kanji candidate)
  // must not also submit the form — it's a "commit this text" keystroke, not "send the message".
  it('does not send while an IME composition is in progress', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: false, onSend }));
    act(() => result.current.setDraft('Q'));

    const composingEnter = key({
      nativeEvent: {
        isComposing: true,
      } as unknown as KeyboardEvent<HTMLTextAreaElement>['nativeEvent'],
    });
    act(() => result.current.onKeyDown(composingEnter));

    expect(composingEnter.preventDefault).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });
});
