import { useEffect } from "react";
import { api } from "./lib/api";
import { useStore } from "./lib/store";
import { Studio } from "./scene/Studio";
import { loadEff, loadOp } from "./ui/actions";
import { Inspector } from "./ui/Inspector";
import { DriveHud, StatusBar, TourCaption } from "./ui/Overlays";
import { Sidebar } from "./ui/Sidebar";
import { TopBar } from "./ui/TopBar";

export function App() {
  useEffect(() => {
    const s = useStore.getState().set;
    Promise.all([api.presets(), api.geometry(), api.parts(), api.fluxList()])
      .then(([presets, geometry, parts, fl]) => { s({ presets, geometry, parts: parts.parts, fluxList: fl.states, status: "준비" }); void loadEff(); void loadOp(); })
      .catch((e) => s({ status: `서버에 연결하지 못했습니다: ${e}` }));
  }, []);
  return (
    <div className="app">
      <TopBar />
      <Sidebar />
      <main className="stage"><Studio /><TourCaption /><DriveHud /></main>
      <Inspector />
      <StatusBar />
    </div>
  );
}
