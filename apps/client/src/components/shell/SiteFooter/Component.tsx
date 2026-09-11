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
      {/* p8 final (M-3): matches Container's responsive gutters (16px on phones, 24px at sm+)
          instead of a flat 24px that felt tight against the viewport edge on small screens. */}
      <Box sx={{ maxWidth: 'lg', mx: 'auto', px: { xs: 2, sm: 3 } }}>
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
