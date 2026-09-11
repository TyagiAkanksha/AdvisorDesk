import { Inter, Source_Serif_4 } from 'next/font/google';
import type { ReactNode } from 'react';

import { Box } from '@/components/common';
import { SiteFooter } from '@/components/shell/SiteFooter';
import { SiteHeader } from '@/components/shell/SiteHeader';
import { rootMetadata } from '@/lib/metadata';

import Providers from './providers';

// phase-8 task-01: next/font downloads these at build time and self-hosts them (no runtime
// request to Google, no CSP change). They reach theme.ts only as the two CSS variables below,
// set on <html> — theme.ts stays Next-free (DESIGN.md §A1). Client = editorial content site,
// so headings are serif; the admin twin of this file uses Inter for both variables.
const headingFont = Source_Serif_4({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-heading',
});
const bodyFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-body' });

export const metadata = rootMetadata;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${headingFont.variable} ${bodyFont.variable}`}>
      <body>
        <Providers>
          <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
            <SiteHeader />
            {children}
            <SiteFooter />
          </Box>
        </Providers>
      </body>
    </html>
  );
}
