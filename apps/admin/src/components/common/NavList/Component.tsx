import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Link from 'next/link';

import { Icon } from '../Icon';
import type { NavListProps } from './interface';

export default function Component({ items }: NavListProps) {
  return (
    <List>
      {items.map((item) => (
        <ListItemButton key={item.href} component={Link} href={item.href}>
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
