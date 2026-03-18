import { AppProviders } from './providers/AppProviders';
import { AppContent } from './AppContent';

export function App() {
  return (
    <AppProviders>
      <AppContent />
    </AppProviders>
  );
}

export default App;
