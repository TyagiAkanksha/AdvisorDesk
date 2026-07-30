import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import Providers from './providers';

export const metadata: Metadata = {
  title: 'AdvisorDesk',
  description: 'Ask questions about our published research and insights.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
