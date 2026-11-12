import { lazy, Suspense } from 'react';
import { App } from './App';
import { useRoute } from './app/router';

// The internal app is a separate chunk, so the landing page bundle is unchanged.
const AppShell = lazy(() => import('./app/AppShell'));

/** `#/app/...` renders the internal app; every other URL renders the landing page. */
export function Root() {
  const { app } = useRoute();
  if (!app) return <App />;
  return (
    <Suspense fallback={<div className="app-loading" aria-busy="true" />}>
      <AppShell />
    </Suspense>
  );
}
