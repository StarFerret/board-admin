import { Navigate, Route, Routes } from "react-router-dom";
import ControlLayout from "./pages/ControlLayout.jsx";
import UsagePage from "./pages/UsagePage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import PeoplePage from "./pages/PeoplePage.jsx";
import AppsPage from "./pages/AppsPage.jsx";
import ModelsPage from "./pages/ModelsPage.jsx";
import MachinePage from "./pages/MachinePage.jsx";
import UpdatesPage from "./pages/UpdatesPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ControlLayout />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="apps" element={<AppsPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="users" element={<PeoplePage />} />
        <Route path="machine" element={<MachinePage />} />
        <Route path="updates" element={<UpdatesPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
