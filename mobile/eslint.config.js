// ESLint 9 flat config. `eslint-config-expo` brings the React Native, React
// Hooks and import rules that match this Expo SDK.
const expoConfig = require('eslint-config-expo/flat');
const prettierConfig = require('eslint-config-prettier');

module.exports = [
  ...expoConfig,
  prettierConfig,
  {
    ignores: ['node_modules/**', '.expo/**', 'dist/**', 'android/**', 'ios/**'],
  },
];
