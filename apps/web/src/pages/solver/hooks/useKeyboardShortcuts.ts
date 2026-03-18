import { useEffect } from 'react';
import { useDisplaySettings } from '../stores/display-settings';
import { useStrategyBrowser } from '../stores/strategy-browser';

export function useKeyboardShortcuts() {
  const { setMatrixMode, toggleNormalize, toggleLock } = useDisplaySettings();
  const { goBack, goToRoot, selectedAction, setSelectedAction, nodeActions } = useStrategyBrowser();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      const isTypingTarget =
        activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';
      if (isTypingTarget) return;

      if (e.key === 'F1') {
        e.preventDefault();
        setMatrixMode('strategy');
      }
      if (e.key === 'F2') {
        e.preventDefault();
        setMatrixMode('equity');
      }
      if (e.key === 'F3') {
        e.preventDefault();
        setMatrixMode('ev');
      }
      if (e.key === 'F8') {
        e.preventDefault();
        toggleNormalize();
      }
      if (e.key === 'F9') {
        e.preventDefault();
        toggleLock();
      }

      // Escape: clear action filter, go back
      if (e.key === 'Escape') {
        if (selectedAction) {
          setSelectedAction(null);
        } else {
          goBack();
        }
      }

      // Home: go to root
      if (e.key === 'Home') {
        e.preventDefault();
        goToRoot();
      }

      // Backspace: go back one step
      if (e.key === 'Backspace') {
        e.preventDefault();
        goBack();
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [
    setMatrixMode,
    toggleNormalize,
    toggleLock,
    goBack,
    goToRoot,
    selectedAction,
    setSelectedAction,
    nodeActions,
  ]);
}
