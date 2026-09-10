import type { Metadata } from 'next';

// phase-8 task-07 (DESIGN.md §A4): one metadata template for the whole app — every page's
// `metadata.title` becomes `<page> · AdvisorDesk` automatically; only the root layout sets
// `description`.
export const SITE_NAME = 'AdvisorDesk';

export const rootMetadata: Metadata = {
  title: { default: SITE_NAME, template: `%s · ${SITE_NAME}` },
  description: 'Ask questions about our published research and insights.',
};
