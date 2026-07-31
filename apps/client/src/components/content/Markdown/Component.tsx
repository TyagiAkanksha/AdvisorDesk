import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Link, Typography } from '@/components/common';

import type { MarkdownProps } from './interface';

// task-04 (phase-3): react-markdown (the default, synchronous `Markdown` export — RSC-safe, no
// hooks) + remark-gfm (tables/strikethrough/autolinks) mapped onto MUI Typography/Link, so
// markdown body content picks up the app's theme instead of unstyled browser defaults. No
// `rehype-raw` plugin is registered, so raw HTML embedded in markdown (e.g. `<script>`) is
// never parsed into real DOM nodes — react-markdown renders it as escaped text instead
// (verified empirically: `<script>alert(1)</script>` comes out as the literal, inert text
// "&lt;script&gt;alert(1)&lt;/script&gt;", never a real `<script>` element).
//
// Lists/tables/emphasis (`ul`/`ol`/`li`/`table`/`thead`/`tbody`/`tr`/`th`/`td`/`strong`/`em`)
// are left as react-markdown's own default semantic HTML — already the correct ARIA
// roles/visible text with no MUI wrapper adding value; only headings/paragraphs/links get the
// theme treatment.
//
// Phase-4 task-05 reuses this component verbatim for assistant answers. The admin
// `MarkdownPreview` (apps/admin/src/components/content/MarkdownPreview/Component.tsx) mirrors
// this same tag→MUI mapping approach in its own copy — the two apps deploy independently, so
// the mapping is duplicated rather than shared, the same way `theme.ts` is.
const components: Components = {
  h1: (props) => <Typography variant="h1" component="h1" {...props} />,
  h2: (props) => <Typography variant="h2" component="h2" {...props} />,
  h3: (props) => <Typography variant="h3" component="h3" {...props} />,
  h4: (props) => <Typography variant="h4" component="h4" {...props} />,
  h5: (props) => <Typography variant="h5" component="h5" {...props} />,
  h6: (props) => <Typography variant="h6" component="h6" {...props} />,
  p: (props) => <Typography variant="body1" component="p" {...props} />,
  a: ({ href, children, ...rest }) => (
    <Link href={href ?? ''} {...rest}>
      {children}
    </Link>
  ),
};

export default function Component({ markdown }: MarkdownProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </ReactMarkdown>
  );
}
