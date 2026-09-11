import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// hygiene t01 (p8 t24 M4): a source-level pin — the screen derives "is there a conversation"
// exactly once (`hasConversation`) instead of repeating `messages.length` checks inline. Lives in
// its own node-environment file, and resolves the path via `fileURLToPath` rather than
// `new URL('./x', import.meta.url)` — Vite rewrites that literal pattern into an asset URL
// (not a file: URL), which is why the same idiom threw inside the jsdom test file.
const SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Component.tsx'), 'utf8');

describe('ChatScreen source', () => {
  it('derives the conversation state once (no inline messages.length checks)', () => {
    expect(SOURCE).toContain('const hasConversation = messages.length > 0;');
    expect(SOURCE).not.toMatch(/messages\.length === 0/);
    expect(SOURCE).not.toMatch(/showNewConversation=\{messages\.length > 0\}/);
  });
});
