import { Box } from '../Box';
import { Icon } from '../Icon';
import type { EmptyStateProps } from './interface';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region. `role="status"` (polite live region) wraps only the icon + text; the
// optional `action` is a sibling after it — controls must not live inside a live region
// (hygiene t03, t23 M5).
// mcp-oauth task-09: `title`/`description` render as two separate paragraphs (not concatenated)
// so each is independently queryable by exact text; `message` (the original, single-line form)
// is unaffected for every pre-existing call site.
export default function Component({
  message,
  title,
  description,
  icon = 'Article',
  action,
}: EmptyStateProps) {
  return (
    <Box sx={{ textAlign: 'center', color: 'text.secondary', py: 6 }}>
      <Box role="status">
        <Icon name={icon} size="large" />
        {title ? (
          <Box component="p" sx={{ mt: 1, fontWeight: 'medium' }}>
            {title}
          </Box>
        ) : null}
        {description ? (
          <Box component="p" sx={{ mt: 0.5 }}>
            {description}
          </Box>
        ) : null}
        {message ? (
          <Box component="p" sx={{ mt: 1 }}>
            {message}
          </Box>
        ) : null}
      </Box>
      {action ? <Box sx={{ mt: 2 }}>{action}</Box> : null}
    </Box>
  );
}
