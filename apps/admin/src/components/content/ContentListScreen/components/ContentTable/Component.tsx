import { Box, IconButton, StatusChip } from '@/components/common';

import type { ContentTableProps } from './interface';

function formatUpdatedAt(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function Component({ items, onDeleteClick }: ContentTableProps) {
  return (
    <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
      <Box component="thead">
        <Box component="tr">
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Title
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Status
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Tags
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Updated
          </Box>
          <Box component="th" sx={{ p: 1 }} />
        </Box>
      </Box>
      <Box component="tbody">
        {items.map((item) => (
          <Box component="tr" key={item.id} sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
            <Box component="td" sx={{ p: 1 }}>
              {item.title}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              <StatusChip status={item.status} />
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {item.tags.map((itemTag) => (
                <Box component="span" key={itemTag} sx={{ mr: 0.5 }}>
                  {itemTag}
                </Box>
              ))}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {formatUpdatedAt(item.updated_at)}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              <IconButton
                name="Delete"
                label={`Delete ${item.title}`}
                onClick={() => onDeleteClick(item)}
              />
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
