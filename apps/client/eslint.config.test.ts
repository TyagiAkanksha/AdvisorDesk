import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

// phase-8 task-02: pins the MUI import boundary (docs/FRONTEND-CONVENTIONS.md §4) as a lint
// gate. `lintText` with a virtual `filePath` resolves the flat config exactly as `eslint .`
// would for a real file at that path — no file needs to exist on disk.
const APP_ROOT = new URL('.', import.meta.url).pathname;
const eslint = new ESLint({ cwd: APP_ROOT });
const MUI_IMPORT = "import MuiButton from '@mui/material/Button';\nexport const x = MuiButton;\n";

async function ruleIdsFor(filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(MUI_IMPORT, { filePath });
  return (result?.messages ?? []).map((message) => message.ruleId ?? '');
}

describe('MUI import boundary (FRONTEND-CONVENTIONS §4)', () => {
  it('rejects an @mui import in a screen component', async () => {
    expect(await ruleIdsFor('src/components/content/Fake/Component.tsx')).toContain(
      'no-restricted-imports',
    );
  }, 20000);

  it('rejects an @mui import in a lib module', async () => {
    expect(await ruleIdsFor('src/lib/fake.ts')).toContain('no-restricted-imports');
  }, 20000);

  it('allows @mui imports inside src/components/common', async () => {
    expect(await ruleIdsFor('src/components/common/Fake/Component.tsx')).not.toContain(
      'no-restricted-imports',
    );
  }, 20000);

  it('allows @mui imports in theme.ts and providers.tsx', async () => {
    expect(await ruleIdsFor('src/theme/theme.ts')).not.toContain('no-restricted-imports');
    expect(await ruleIdsFor('src/app/providers.tsx')).not.toContain('no-restricted-imports');
  }, 20000);
});
