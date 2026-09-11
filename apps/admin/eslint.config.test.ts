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

const TESTING_IMPORT =
  "import { navigation } from '@/testing/nextNavigation';\nexport const x = navigation;\n";

async function ruleIdsForText(text: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(text, { filePath });
  return (result?.messages ?? []).map((message) => message.ruleId ?? '');
}

describe('test-seam import boundary (hygiene t09)', () => {
  it('rejects an @/testing import in a screen component', async () => {
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/Component.tsx'),
    ).toContain('no-restricted-imports');
  }, 20000);

  it('rejects an @/testing import in a common primitive, a hook and a lib module', async () => {
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/common/Fake/Component.tsx'),
    ).toContain('no-restricted-imports');
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/useFake.ts'),
    ).toContain('no-restricted-imports');
    expect(await ruleIdsForText(TESTING_IMPORT, 'src/lib/fake.ts')).toContain(
      'no-restricted-imports',
    );
  }, 20000);

  it('allows @/testing imports from test files anywhere and from src/testing itself', async () => {
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/Component.test.tsx'),
    ).not.toContain('no-restricted-imports');
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/common/Fake/Component.test.tsx'),
    ).not.toContain('no-restricted-imports');
    expect(await ruleIdsForText(TESTING_IMPORT, 'src/testing/other.test.tsx')).not.toContain(
      'no-restricted-imports',
    );
    // Colocated test-support folders (e.g. ContentEditorScreen/testing/renderEditor.tsx).
    expect(
      await ruleIdsForText(TESTING_IMPORT, 'src/components/content/Fake/testing/renderFake.tsx'),
    ).not.toContain('no-restricted-imports');
  }, 20000);

  // The composition must not drop the MUI boundary for any file class it re-configures.
  it('keeps the MUI boundary in place for test files outside common', async () => {
    expect(
      await ruleIdsForText(MUI_IMPORT, 'src/components/content/Fake/Component.test.tsx'),
    ).toContain('no-restricted-imports');
  }, 20000);
});
