import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Compass } from './pages/Compass';
import { Dashboard } from './pages/Dashboard';
import { ManualHoldings } from './pages/ManualHoldings';
import { Status } from './pages/Status';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="manual-holdings" element={<ManualHoldings />} />
          {/* Thresholds (task 11/17) moved into Compass's Risk Controls
              section — redirect any old bookmark/link rather than 404. */}
          <Route path="thresholds" element={<Navigate to="/compass" replace />} />
          <Route path="compass" element={<Compass />} />
          <Route path="status" element={<Status />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
