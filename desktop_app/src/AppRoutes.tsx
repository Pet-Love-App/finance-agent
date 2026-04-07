import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "./App";
import { CompareWindow } from "./routes/CompareWindow";
import { PetChatWindow } from "./routes/PetChatWindow";
import { PetWindow } from "./routes/PetWindow";
import { ThemeProvider } from "./theme";

export function AppRoutes() {
  return (
    <ThemeProvider>
      <HashRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/compare" element={<CompareWindow />} />
          <Route path="/pet" element={<PetWindow />} />
          <Route path="/pet-chat" element={<PetChatWindow />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </ThemeProvider>
  );
}
