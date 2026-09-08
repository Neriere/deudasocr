import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { AuditorView } from "./components/AuditorView";
import { ErrorCheckerJsonView } from "./components/ErrorCheckerJsonView";
import { ScriptDownloadView } from "./components/ScriptDownloadView";
import { AuditDbState } from "./types";

export default function App() {
  const [activeTab, setActiveTab] = useState<string>("auditor");
  const [auditState, setAuditState] = useState<AuditDbState>({
    players: {},
    settlements: [],
    last_combat: null,
  });

  const fetchAuditState = async () => {
    try {
      const res = await fetch("/api/audit");
      if (res.ok) {
        const data = await res.json();
        setAuditState(data);
      }
    } catch (err) {
      console.error("Error cargando auditoria:", err);
    }
  };

  useEffect(() => {
    fetchAuditState();
    const interval = setInterval(fetchAuditState, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleResetPlayer = async (playerKey: string) => {
    try {
      const res = await fetch("/api/audit/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: playerKey }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.db) setAuditState(data.db);
        else await fetchAuditState();
      }
    } catch (err) {
      console.error("Error reseteando jugador:", err);
    }
  };

  const handleResetAll = async () => {
    try {
      const res = await fetch("/api/audit/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all: true }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.db) setAuditState(data.db);
        else await fetchAuditState();
      }
    } catch (err) {
      console.error("Error reseteando todos los jugadores:", err);
    }
  };

  const handleSimulateCombat = async () => {
    try {
      const res = await fetch("/api/audit/simulate", {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        if (data.db) setAuditState(data.db);
        else await fetchAuditState();
      }
    } catch (err) {
      console.error("Error simulando combate:", err);
    }
  };

  const handleUpdateCharacterName = async (name: string) => {
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ my_character_name: name }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.db) setAuditState(data.db);
        else await fetchAuditState();
      }
    } catch (err) {
      console.error("Error actualizando personaje:", err);
    }
  };

  const pendingPlayersCount = Object.values(auditState.players || {}).filter(
    (p: any) => Object.keys(p.pending_drops || {}).length > 0
  ).length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white">
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        pendingPlayersCount={pendingPlayersCount}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "auditor" && (
          <AuditorView
            auditState={auditState}
            onRefresh={fetchAuditState}
            onResetPlayer={handleResetPlayer}
            onResetAll={handleResetAll}
            onSimulateCombat={handleSimulateCombat}
            onUpdateCharacterName={handleUpdateCharacterName}
          />
        )}

        {activeTab === "diagnostic" && <ErrorCheckerJsonView />}

        {activeTab === "script" && <ScriptDownloadView />}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950 py-3 text-center text-xs text-slate-500">
        <p>Dofus Unity Sniffer & Botín</p>
      </footer>
    </div>
  );
}
