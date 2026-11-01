import js from '@eslint/js'
import astro from 'eslint-plugin-astro'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Deliberately stricter than steam-backlog-enforcer/web, which this was copied
// from: that one extends only `tseslint.configs.recommended` and so runs no
// type-aware rules at all. `strictTypeChecked` needs `projectService`, so the
// tests live inside tsconfig.json's `src` include and are lintable.
export default defineConfig([
  globalIgnores(['dist', 'coverage', '.astro']),
  {
    files: ['**/*.ts'],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  ...astro.configs.recommended,
])
