import { Box } from '../Box';
import { Stack } from '../Stack';
import { Typography } from '../Typography';
import type { PageHeaderProps } from './interface';

// phase-8 task-05 (DESIGN.md §A3): one heading block for every admin screen — the page's <h1>
// (styled at the h2 size: an admin console title, not an article title), an optional one-line
// description, an optional meta line, and the screen's primary actions on the right.
export default function Component({ title, description, actions, meta }: PageHeaderProps) {
  return (
    <Stack
      component="header"
      direction={{ xs: 'column', sm: 'row' }}
      spacing={2}
      sx={{
        alignItems: { xs: 'flex-start', sm: 'center' },
        justifyContent: 'space-between',
        mb: 3,
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h2" component="h1">
          {title}
        </Typography>
        {description ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {description}
          </Typography>
        ) : null}
        {meta ? <Box sx={{ mt: 1 }}>{meta}</Box> : null}
      </Box>
      {actions ? (
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          {actions}
        </Stack>
      ) : null}
    </Stack>
  );
}
