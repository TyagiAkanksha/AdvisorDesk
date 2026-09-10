export interface TagFilterProps {
  tags: string[]; // from uniqueTags(all items)
  selectedTag: string | null; // null = "All"
}
