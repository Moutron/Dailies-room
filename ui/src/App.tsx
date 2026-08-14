import { Navigate, Route, Routes } from "react-router-dom";
import { Attribution } from "./components/Attribution";
import { AskPage } from "./pages/AskPage";
import { ClipDetailPage } from "./pages/ClipDetailPage";
import { CoveragePage } from "./pages/CoveragePage";
import { IngestPage } from "./pages/IngestPage";
import { ReelsPage } from "./pages/ReelsPage";
import { ShotListPage } from "./pages/ShotListPage";

export default function App() {
  return (
    <div className="app">
      <div className="app__routes">
        <Routes>
          <Route path="/" element={<Navigate to="/ask" replace />} />
          <Route path="/ask" element={<AskPage />} />
          <Route path="/coverage" element={<CoveragePage />} />
          <Route path="/reels" element={<ReelsPage />} />
          <Route path="/shot-list" element={<ShotListPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/clip/:clipId" element={<ClipDetailPage />} />
          <Route path="*" element={<Navigate to="/ask" replace />} />
        </Routes>
      </div>
      <Attribution />
    </div>
  );
}
