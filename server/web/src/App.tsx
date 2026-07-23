import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { queryClient } from './lib/queryClient';
import { AppShell } from './components/AppShell';
import { Overview } from './views/Overview';
import { Projects } from './views/Projects';
import { Jobs } from './views/Jobs';
import { Targets } from './views/Targets';
import { Profiles } from './views/Profiles';

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/targets" element={<Targets />} />
            <Route path="/profiles" element={<Profiles />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </HashRouter>
    </QueryClientProvider>
  );
};
