import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Link, Typography } from '@/components/common';

import type { MarkdownPreviewProps } from './interface';

// phase-3 task-04: swaps the task-06 `<pre>` placeholder for the same react-markdown +
// remark-gfm renderer as the client app's shared Markdown component, so what a content manager
// sees here previews what `ArticleScreen` will actually render — same tag→MUI mapping approach
// (headings/paragraphs → Typography, links → Link; lists/tables/emphasis left as
// react-markdown's own semantic HTML), NOT literal shared code, since apps/admin and
// apps/client deploy independently (docs/plans/phase-3-publish-client-content/
// task-04-client-content-ui.md: "share the MAPPING approach, not literal code"). Twin copy:
// apps/client/src/components/content/Markdown/Component.tsx.
//
// `{markdown: string}` in / visible text out is the frozen contract from task-06 — unchanged by
// this swap (MarkdownPreview/Component.test.tsx is pinned against the TEXT it renders, not this
// file's internals).
//
// task-04 fix round 1 (F2): react-markdown@10 hardcodes `passNode: true` in its own
// `toJsxRuntime` call (node_modules/react-markdown/lib/index.js — NOT opt-in, despite what
// `lib/index.d.ts` alone suggests), so every custom renderer below receives an extra `node`
// prop (the hast AST node: `tagName`/`children`/`position` offsets). Left in `{...props}`, that
// object lands on the DOM as a literal `node="[object Object]"` attribute. Every mapping
// destructures `node` out before spreading the rest. Twin copy: apps/client/src/components/
// content/Markdown/Component.tsx — keep both in sync (see that file's twin-header Component.test.tsx).
const components: Components = {
  h1: ({ node, ...props }) => <Typography variant="h1" component="h1" {...props} />,
  h2: ({ node, ...props }) => <Typography variant="h2" component="h2" {...props} />,
  h3: ({ node, ...props }) => <Typography variant="h3" component="h3" {...props} />,
  h4: ({ node, ...props }) => <Typography variant="h4" component="h4" {...props} />,
  h5: ({ node, ...props }) => <Typography variant="h5" component="h5" {...props} />,
  h6: ({ node, ...props }) => <Typography variant="h6" component="h6" {...props} />,
  p: ({ node, ...props }) => <Typography variant="body1" component="p" {...props} />,
  a: ({ node, href, children, ...rest }) => (
    <Link href={href ?? ''} {...rest}>
      {children}
    </Link>
  ),
};

export default function Component({ markdown }: MarkdownPreviewProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </ReactMarkdown>
  );
}
