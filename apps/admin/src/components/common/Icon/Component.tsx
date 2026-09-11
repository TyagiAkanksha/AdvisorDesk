import ArticleIcon from '@mui/icons-material/Article';
import CloseIcon from '@mui/icons-material/Close';
import DashboardIcon from '@mui/icons-material/Dashboard';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import LinkIcon from '@mui/icons-material/Link';
import MenuIcon from '@mui/icons-material/Menu';
import SearchIcon from '@mui/icons-material/Search';
import SendIcon from '@mui/icons-material/Send';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import StopIcon from '@mui/icons-material/Stop';

import type { IconProps } from './interface';

// Explicit registry, NOT `import * as icons from '@mui/icons-material'` (see interface.ts
// for why). Add a named import above + an entry here when a screen needs an icon that
// isn't listed yet — `IconProps['name']` tracks this object automatically via `keyof typeof`.
// SmartToy/Link/ExpandMore/Send/Stop added phase-8 task-14 (DESIGN.md §C1/§C4/§C7: AppBar
// "Agent" button + agent panel, NavList's external-link items, the tag table's dashboard link,
// the composer's send button, streaming Stop). p8 final, F15: Add/Chat/Logout removed —
// zero call sites reference them (re-verified by grep before deleting).
export const ICONS = {
  Article: ArticleIcon,
  Close: CloseIcon,
  Dashboard: DashboardIcon,
  Delete: DeleteIcon,
  Edit: EditIcon,
  ExpandMore: ExpandMoreIcon,
  Link: LinkIcon,
  Menu: MenuIcon,
  Search: SearchIcon,
  Send: SendIcon,
  SmartToy: SmartToyIcon,
  Stop: StopIcon,
} as const;

export default function Component({ name, label, size = 'medium', color }: IconProps) {
  const Glyph = ICONS[name];

  return (
    <Glyph
      fontSize={size}
      sx={color ? { color } : undefined}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}
