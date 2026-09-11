import { useEffect, useRef } from 'react';

// p8 final wave, F6 (DESIGN.md §5 C3/C4/C5/C6 idiom, generalized): replaces four verbatim
// "notify once per background-refresh-failure episode" blocks that had drifted into
// useDashboard/useContentList/useContentEditor/useConnectedApps. Fires `notify(message)` once on
// each false→true transition ("rising edge") of `active` — and never on mount, even when
// `active` is already `true` on the very first render: the "previous value" ref is SEEDED with
// that same first-render value (not a hardcoded `false`), so the first effect run always compares
// `active` against itself and can never look like a transition. A later genuine false→true
// transition (a fresh failure episode) still fires; `active` staying `true` across renders
// (a sustained failure) does not re-fire; going back to `false` and `true` again (recovery, then
// a new failure) fires again.
export function useRisingEdgeNotice(
  active: boolean,
  notify: (message: string) => void,
  message: string,
): void {
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && !wasActive.current) {
      notify(message);
    }
    wasActive.current = active;
  }, [active, notify, message]);
}
