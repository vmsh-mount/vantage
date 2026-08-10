import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { ManualHoldings } from './pages/ManualHoldings';
import { Thresholds } from './pages/Thresholds';
import { Status } from './pages/Status';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="manual-holdings" element={<ManualHoldings />} />
          <Route path="thresholds" element={<Thresholds />} />
          <Route path="status" element={<Status />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
