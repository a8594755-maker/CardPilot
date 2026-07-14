import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: 'var(--cp-bg-base, #151210)',
          color: 'var(--cp-text-primary, #f2ead9)',
          fontFamily: 'system-ui, sans-serif',
          padding: '2rem',
          textAlign: 'center',
        }}
      >
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>Something went wrong</h1>
        <p
          style={{
            color: 'var(--cp-text-secondary, #a6988a)',
            marginBottom: '1.5rem',
            maxWidth: '24rem',
          }}
        >
          An unexpected error occurred. Please try reloading the page.
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            padding: '0.625rem 1.5rem',
            backgroundColor: 'var(--cp-accent, #e3c27e)',
            color: '#fff',
            border: 'none',
            borderRadius: '0.5rem',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
          }}
        >
          Reload
        </button>
      </div>
    );
  }
}
