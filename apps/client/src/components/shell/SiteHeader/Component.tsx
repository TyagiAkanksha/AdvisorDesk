import { AppBar, Box, Link, Toolbar, Typography } from '@/components/common';
import { SITE_NAME } from '@/lib/metadata';

import { SiteNav } from '../SiteNav';

// phase-8 task-08 (DESIGN.md §B1): a conventional content-site header — white, bottom border,
// no shadow; wordmark left, two links right. Server Component; `SiteNav` is the client leaf.
export default function Component() {
  return (
    <AppBar
      position="static"
      color="inherit"
      elevation={0}
      sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}
    >
      <Toolbar sx={{ maxWidth: 'lg', width: '100%', mx: 'auto', justifyContent: 'space-between' }}>
        <Typography
          variant="h5"
          component="span"
          sx={{ fontFamily: 'var(--font-heading), Georgia, serif' }}
        >
          <Link href="/" underline="none" color="inherit" aria-label={`${SITE_NAME} home`}>
            {SITE_NAME}
          </Link>
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <SiteNav />
        </Box>
      </Toolbar>
    </AppBar>
  );
}
