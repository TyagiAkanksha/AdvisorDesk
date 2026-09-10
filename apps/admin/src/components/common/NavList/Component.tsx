'use client';

import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Link from 'next/link';

import { Icon } from '../Icon';
import type { NavListProps } from './interface';

// p8 final: same latent defect common/Link (task-04 fix round 1, F1) already documents — `Link`
// (a function) passed as `component` isn't serializable across an RSC boundary into MUI's own
// `'use client'` ListItemButton, so a Server Component call site would 500.
export default function Component({ items, onNavigate }: NavListProps) {
  return (
    <List>
      {items.map((item) => (
        <ListItemButton
          key={item.href}
          component={Link}
          href={item.href}
          selected={item.selected}
          onClick={onNavigate}
          aria-current={item.selected ? 'page' : undefined}
        >
          {item.icon ? (
            <ListItemIcon>
              <Icon name={item.icon} />
            </ListItemIcon>
          ) : null}
          <ListItemText primary={item.label} />
        </ListItemButton>
      ))}
    </List>
  );
}
