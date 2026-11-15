import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import BoardPage from "./pages/BoardPage.jsx";
import WorkspacePage from "./pages/WorkspacePage.jsx";
import AgentPage from "./pages/AgentPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import NameGate from "./NameGate.jsx";
import { VisitorContext } from "./visitorContext.js";

const STORAGE_KEY = "starferret_name";

export default function App() {
  const [visitorName, setVisitorName] = useState(() => localStorage.getItem(STORAGE_KEY) || "");

  if (!visitorName.trim()) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <NameGate
          onDone={(name) => {
            localStorage.setItem(STORAGE_KEY, name);
            setVisitorName(name);
          }}
        />
      </div>
    );
  }

  return (
    <VisitorContext.Provider value={visitorName}>
      <Routes>
        <Route path="/" element={<BoardPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/w/:id" element={<WorkspacePage />} />
        <Route path="/a/:id" element={<AgentPage />} />
        <Route path="*" element={<BoardPage />} />
      </Routes>
    </VisitorContext.Provider>
  );
}
