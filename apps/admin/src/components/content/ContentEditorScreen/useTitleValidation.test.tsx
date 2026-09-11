// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useTitleValidation } from './useTitleValidation';

// hygiene t07 (closes phase-8 t19 M2): the editor's title-validation state (blurred /
// submit-attempted / message) is a self-contained state machine, extracted out of the 375-line
// `useContentEditor.ts`. RED today: the module does not exist.
describe('useTitleValidation', () => {
  it('stays silent until the field is blurred or a submit is attempted', () => {
    const { result } = renderHook(() => useTitleValidation(''));

    expect(result.current.titleError).toBeNull();
  });

  it('reports the required message after a blur on a blank title', () => {
    const { result } = renderHook(() => useTitleValidation(''));

    act(() => result.current.onTitleBlur());

    expect(result.current.titleError).toBe('Title is required');
  });

  it('reports the required message after a submit attempt without any blur', () => {
    const { result } = renderHook(() => useTitleValidation(''));

    act(() => result.current.markSubmitAttempted());

    expect(result.current.titleError).toBe('Title is required');
  });

  it('clears as soon as a non-blank title arrives and stays clear on re-blur', () => {
    const { result, rerender } = renderHook((title: string) => useTitleValidation(title), {
      initialProps: '',
    });
    act(() => result.current.onTitleBlur());
    expect(result.current.titleError).toBe('Title is required');

    rerender('A title');
    expect(result.current.titleError).toBeNull();

    act(() => result.current.onTitleBlur());
    expect(result.current.titleError).toBeNull();
  });

  it('re-reports when a title that was typed is emptied again', () => {
    const { result, rerender } = renderHook((title: string) => useTitleValidation(title), {
      initialProps: 'A title',
    });
    act(() => result.current.onTitleBlur());
    expect(result.current.titleError).toBeNull();

    rerender('');

    expect(result.current.titleError).toBe('Title is required');
  });
});
