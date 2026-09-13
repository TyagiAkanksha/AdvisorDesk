import ArticleIcon from '@mui/icons-material/Article';
import SearchIcon from '@mui/icons-material/Search';
import SendIcon from '@mui/icons-material/Send';
import StopIcon from '@mui/icons-material/Stop';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';

import type { IconProps } from './interface';

// Explicit registry, NOT `import * as icons from '@mui/icons-material'` (see interface.ts
// for why). Add a named import above + an entry here when a screen needs an icon that
// isn't listed yet — `IconProps['name']` tracks this object automatically via `keyof typeof`.
// `Send`/`Stop` added phase-8 task-12: the chat composer's submit/abort icon button.
// `ThumbUpAltOutlined`/`ThumbDownAltOutlined` added phase-9 task-17: the 👍/👎 feedback control.
//
// p8 t24: pruned `Add`, `Chat`, `Close`, `Dashboard`, `Delete`, `Edit`, `Info`, `Logout`, `Menu`
// — none of them was referenced anywhere in this app (verified with a repo-wide grep before
// deleting); the admin registry, which does use several of these names, is untouched.
export const ICONS = {
  Article: ArticleIcon,
  Search: SearchIcon,
  Send: SendIcon,
  Stop: StopIcon,
  ThumbDownAltOutlined: ThumbDownAltOutlinedIcon,
  ThumbUpAltOutlined: ThumbUpAltOutlinedIcon,
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
