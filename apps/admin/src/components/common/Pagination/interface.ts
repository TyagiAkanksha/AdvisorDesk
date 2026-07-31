/**
 * A page-based pager (docs/FRONTEND-CONVENTIONS.md §4) — wraps MUI `Pagination`, not
 * `TablePagination` (fix round 1, F1: the content table is hand-rolled `Box`-as-semantic-table
 * markup, not MUI's own `Table`/`TableRow`/`TableCell`, and `TablePagination`'s root renders
 * as a `<td>` that would need re-wrapping in a `<tr>` for no benefit here). `page` is
 * 1-indexed, matching `useContentList`'s own paging state and the API's `page` query param.
 */
export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}
