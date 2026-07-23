import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './components/AppShell';

export const App: React.FC = () => {
  return (
    <BrowserRouter basename="/dashboard">
      <AppShell>
        <Routes>
          <Route
            path="/"
            element={
              <div style={{ padding: '1rem' }}>
                <h2>Overview</h2>
                <p>Welcome to OpenMCP Monitor &amp; Debug Console.</p>
              </div>
            }
          />
          <Route
            path="/projects"
            element={
              <div style={{ padding: '1rem' }}>
                <h2>Projects</h2>
                <p>Projects monitoring view.</p>
              </div>
            }
          />
          <Route
            path="/jobs"
            element={
              <div style={{ padding: '1rem' }}>
                <h2>Jobs</h2>
                <p>Jobs &amp; Execution timeline view.</p>
              </div>
            }
          />
          <Route
            path="/targets"
            element={
              <div style={{ padding: '1rem' }}>
                <h2>Targets</h2>
                <p>Backend target capacity &amp; status view.</p>
              </div>
            }
          />
          <Route
            path="/profiles"
            element={
              <div style={{ padding: '1rem' }}>
                <h2>Profiles</h2>
                <p>Profile configuration view.</p>
              </div>
            }
          />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
};
