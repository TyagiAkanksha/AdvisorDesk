import { Box, Typography } from '@/components/common';
import { DISCLAIMER } from '@/lib/copy';
import { SITE_NAME } from '@/lib/metadata';

// phase-8 task-08 (DESIGN.md §B1, PRD §8): the disclaimer lives in the footer on every page.
export default function Component() {
  return (
    <Box
      component="footer"
      sx={{ borderTop: 1, borderColor: 'divider', mt: 6, py: 3, bgcolor: 'background.paper' }}
    >
      <Box sx={{ maxWidth: 'lg', mx: 'auto', px: 3 }}>
        <Typography variant="body2" color="text.secondary" component="p">
          {DISCLAIMER}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.5 }}>
          {SITE_NAME}
        </Typography>
      </Box>
    </Box>
  );
}
