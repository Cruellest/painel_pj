// frontend/src/sistemas/cumprimento_beta/index.ts
/**
 * Entry point para o módulo Cumprimento de Sentença Beta
 *
 * Este arquivo é o ponto de entrada para o bundler (esbuild/vite/webpack)
 */

// Export all types
export * from './types';

// Export API
export { api } from './api';

// Export components
export {
  JsonViewer,
  jsonViewerStyles,
  HistoryDrawer,
  historyDrawerStyles,
  ProcessSteps,
  processStepsStyles,
  ProcessSummary,
  processSummaryStyles,
} from './components';

// Export and run app
export { CumprimentoBetaApp } from './app';
