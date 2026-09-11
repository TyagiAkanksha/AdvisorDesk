'use client';

import { Box, Chip, Link } from '@/components/common';
import { ALL_TAGS_LABEL } from '@/lib/copy';

import type { TagFilterProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2): tag chips as links — filtering is a URL, not client state, so
// the page stays an RSC and a filtered list is shareable. Client leaf for the same reason as
// ArticleCard (next/link passed as `component`).
export default function Component({ tags, selectedTag }: TagFilterProps) {
  const options = [
    { label: ALL_TAGS_LABEL, tag: null },
    ...tags.map((tag) => ({ label: tag, tag })),
  ];

  return (
    <Box
      component="nav"
      aria-label="Filter by tag"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 3 }}
    >
      {options.map((option) => {
        const selected = option.tag === selectedTag;
        return (
          <Chip<typeof Link>
            key={option.label}
            component={Link}
            href={option.tag === null ? '/' : `/?tag=${encodeURIComponent(option.tag)}`}
            clickable
            label={option.label}
            color={selected ? 'primary' : 'default'}
            variant={selected ? 'filled' : 'outlined'}
            aria-current={selected ? 'page' : undefined}
          />
        );
      })}
    </Box>
  );
}
