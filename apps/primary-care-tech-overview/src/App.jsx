import React from "react";
import FunnelBoard from "./components/FunnelBoard.jsx";

// Reworked into a single vertical "Funnel Movement" board.
// The previous multi-section layout (ArrProgressHeader / LiveCohortTable /
// MofuPanels / TofuSources / PracticeDrilldown) is kept on disk but no longer
// rendered — cheap insurance if a future view wants those panels back.
export default function App() {
  return <FunnelBoard />;
}
