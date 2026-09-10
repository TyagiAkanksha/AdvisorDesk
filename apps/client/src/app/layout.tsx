import type { Metadata } from 'next';
import { Inter, Source_Serif_4 } from 'next/font/google';
import type { ReactNode } from 'react';

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

export const metadata: Metadata = {
  title: 'AdvisorDesk',
  description: 'Ask questions about our published research and insights.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${headingFont.variable} ${bodyFont.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
