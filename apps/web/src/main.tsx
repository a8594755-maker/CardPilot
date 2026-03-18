import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { LegalStandalonePage, getLegalRoute } from './legal-pages';
import './styles.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
    },
  },
});

const legalRoute = typeof window !== 'undefined' ? getLegalRoute(window.location.pathname) : null;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        {legalRoute ? (
          <LegalStandalonePage route={legalRoute} />
        ) : (
          <BrowserRouter
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            <App />
          </BrowserRouter>
        )}
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
