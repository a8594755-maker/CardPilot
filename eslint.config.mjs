import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import eslintConfigPrettier from 'eslint-config-prettier';

export default tseslint.config(
  // ── Global ignores ──
  {
    ignores: [
      '**/node_modules/',
      '**/dist/',
      '**/build/',
      '**/coverage/',
      'data/',
      'EZ-GTO/',
      'EZ-GTO-data/',
      'checkpoints/',
      'tools/',
      'models/',
      'scripts/',
      'docs/',
      'apps/web/src/**/*Final.ts',
      'apps/web/src/**/*Final.tsx',
      'apps/web/src/**/*.bak',
      '**/*.js',
      '**/*.cjs',
      '**/*.mjs',
    ],
  },

  // ── Base JS recommended rules ──
  eslint.configs.recommended,

  // ── TypeScript recommended (type-aware off for speed) ──
  ...tseslint.configs.recommended,

  // ── Disable formatting rules (let Prettier handle it) ──
  eslintConfigPrettier,

  // ── Project-wide overrides ──
  {
    files: ['**/*.ts', '**/*.tsx'],
    linterOptions: {
      // Downgrade "unused/unknown disable directive" from error to warn
      // (some files reference react-hooks plugin which isn't installed)
      reportUnusedDisableDirectives: 'warn',
    },
    rules: {
      // Allow unused vars prefixed with _ (common pattern in this codebase)
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // Allow explicit any (too many to fix at once)
      '@typescript-eslint/no-explicit-any': 'off',
      // Allow non-null assertions (common in poker code)
      '@typescript-eslint/no-non-null-assertion': 'off',
      // Allow require imports (used in some node scripts)
      '@typescript-eslint/no-require-imports': 'off',
      // Allow empty functions (stubs, callbacks)
      '@typescript-eslint/no-empty-function': 'off',
      // Allow empty object types in interfaces
      '@typescript-eslint/no-empty-object-type': 'off',
      // Allow empty catch blocks
      'no-empty': ['error', { allowEmptyCatch: true }],
      // Allow declarations in case blocks (common pattern)
      'no-case-declarations': 'off',
      // Prefer const
      'prefer-const': 'warn',
      // No console in library packages (warn only)
      'no-console': 'off',
    },
  },

  // ── Test files: relax rules ──
  {
    files: ['**/__tests__/**', '**/*.test.ts', '**/*.test.tsx'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
      'no-useless-escape': 'off',
    },
  },
);
