import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier'

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.d.ts']
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  prettier,
  {
    files: ['**/*.{ts,tsx,vue}'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        ecmaVersion: 'latest',
        sourceType: 'module'
      }
    },
    rules: {
      // Baseline: report existing debt as warnings, do not block P0.
      // TypeScript and Vue's compiler already resolve identifiers; the ESLint
      // core no-undef rule cannot see auto-imported Vue APIs and is therefore noise.
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'no-console': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // P0 baseline: surface existing debt as warnings. Tighten these to errors
      // after the P1 cleanup pass so the gate can go green without hiding debt.
      'no-empty': 'warn',
      'no-useless-escape': 'warn',
      'no-irregular-whitespace': 'warn',
      'prefer-const': 'warn',
      'no-var': 'warn',
      'no-useless-catch': 'warn',
      'no-misleading-character-class': 'warn',
      '@typescript-eslint/no-unused-expressions': 'warn',
      'vue/require-valid-default-prop': 'warn',
      'vue/valid-define-emits': 'warn',
      'vue/no-mutating-props': 'warn',
      'vue/no-dupe-keys': 'warn',
      'vue/no-unused-vars': 'warn',
      'vue/no-deprecated-filter': 'warn',
      'vue/no-side-effects-in-computed-properties': 'warn',
      'vue/no-deprecated-v-on-native-modifier': 'warn',
      'vue/no-reserved-component-names': 'warn',
      'no-control-regex': 'warn',
      'no-unused-labels': 'warn',
      'no-prototype-builtins': 'warn',
      'no-self-assign': 'warn',
      'no-unsafe-optional-chaining': 'warn',
      '@typescript-eslint/no-empty-object-type': 'warn',
      '@typescript-eslint/no-unsafe-function-type': 'warn',
      '@typescript-eslint/no-this-alias': 'warn',
      'vue/multi-word-component-names': 'off',
      'vue/require-default-prop': 'off',
      'vue/no-v-html': 'off',
      'vue/attributes-order': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      // 大文件拆分的护栏：先以 warning 暴露存量，后续每个模块拆完再把阈值收紧。
      'max-lines': ['warn', { max: 1000, skipBlankLines: true, skipComments: true }]
    }
  }
]
