// phase-8 task-03 (DESIGN.md §A2). Every CMS body starts with `# <title>` (the seed articles
// and the editor convention), while `ArticleScreen` renders the title itself — so the page
// showed the title twice. Pure and tested here rather than special-cased inside the renderer:
// the renderer shouldn't know what a "title" is.
const LEADING_H1 = /^\s*#[ \t]+([^\n]*?)[ \t]*#*[ \t]*(?:\n|$)/;

export function stripLeadingHeading(body: string, title: string): string {
  const match = LEADING_H1.exec(body);
  if (!match) {
    return body;
  }
  const headingText = (match[1] ?? '').trim().toLowerCase();
  if (headingText !== title.trim().toLowerCase()) {
    return body;
  }
  return body.slice(match[0].length).replace(/^\n+/, '');
}
