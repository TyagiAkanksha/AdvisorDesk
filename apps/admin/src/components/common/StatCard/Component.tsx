import { Link } from '../Link';
import { Paper } from '../Paper';
import { Typography } from '../Typography';
import type { StatCardProps } from './interface';

// phase-8 task-05 (DESIGN.md §A3/§C3): the dashboard's status/tag counts. Replaces a 7-line sx
// blob that had been duplicated across the dashboard's stat-card slots (FRONTEND-CONVENTIONS §2:
// "a style used twice becomes a variant or a component"). With `href`, the whole card is one link.
export default function Component({ label, value, href }: StatCardProps) {
  const card = (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        height: '100%',
        ...(href ? { '&:hover': { borderColor: 'primary.main' } } : {}),
      }}
    >
      <Typography variant="body2" color="text.secondary" component="p">
        {label}
      </Typography>
      <Typography variant="h3" component="p" sx={{ mt: 0.5 }}>
        {value}
      </Typography>
    </Paper>
  );

  if (!href) {
    return card;
  }
  return (
    <Link href={href} underline="none" color="inherit" sx={{ display: 'block' }}>
      {card}
    </Link>
  );
}
