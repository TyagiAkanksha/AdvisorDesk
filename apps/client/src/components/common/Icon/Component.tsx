import AddIcon from '@mui/icons-material/Add';
import ArticleIcon from '@mui/icons-material/Article';
import ChatIcon from '@mui/icons-material/Chat';
import CloseIcon from '@mui/icons-material/Close';
import DashboardIcon from '@mui/icons-material/Dashboard';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import LogoutIcon from '@mui/icons-material/Logout';
import MenuIcon from '@mui/icons-material/Menu';
import SearchIcon from '@mui/icons-material/Search';
import SendIcon from '@mui/icons-material/Send';
import StopIcon from '@mui/icons-material/Stop';

import type { IconProps } from './interface';

// Explicit registry, NOT `import * as icons from '@mui/icons-material'` (see interface.ts
// for why). Add a named import above + an entry here when a screen needs an icon that
// isn't listed yet — `IconProps['name']` tracks this object automatically via `keyof typeof`.
// `Info` added task-05 review round 1 (I-1) for the refusal bubble's visual marker; phase-8
// task-12 fix round 1 (M-7) moved that marker onto `common/Alert`'s own built-in severity icon —
// kept here for the client registry, currently unreferenced.
// `Send`/`Stop` added phase-8 task-12: the chat composer's submit/abort icon button.
export const ICONS = {
  Add: AddIcon,
  Article: ArticleIcon,
  Chat: ChatIcon,
  Close: CloseIcon,
  Dashboard: DashboardIcon,
  Delete: DeleteIcon,
  Edit: EditIcon,
  Info: InfoOutlinedIcon,
  Logout: LogoutIcon,
  Menu: MenuIcon,
  Search: SearchIcon,
  Send: SendIcon,
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
