import { Inter } from 'next/font/google';
import type { ReactNode } from 'react';

import { rootMetadata } from '@/lib/metadata';

import Providers from './providers';

// phase-8 task-01: next/font downloads these at build time and self-hosts them (no runtime
// request to Google, no CSP change). They reach theme.ts only as the two CSS variables below,
// set on <html> — theme.ts stays Next-free (DESIGN.md §A1). Admin = internal console, so both
// variables use Inter; the client twin of this file uses Source Serif 4 for headings.
const headingFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-heading' });
const bodyFont = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-body' });

export const metadata = rootMetadata;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${headingFont.variable} ${bodyFont.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
