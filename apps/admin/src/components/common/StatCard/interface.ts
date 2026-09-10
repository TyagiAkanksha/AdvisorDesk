export interface StatCardProps {
  label: string;
  value: number | string;
  /** When set, the whole card is a link (dashboard → filtered content list, DESIGN.md §C3). */
  href?: string;
}
