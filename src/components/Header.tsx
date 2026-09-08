import React from "react";
import { UserCheck, FileCode, Terminal, Download } from "lucide-react";
import { DOFUS_AUDITOR_PYTHON, ITEMS_DATABASE_JSON } from "../data/scripts";

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  pendingPlayersCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  pendingPlayersCount,
}) => {
  const tabs = [
    {
      id: "auditor",
      label: "Botín",
      icon: UserCheck,
      badge: pendingPlayersCount,
    },
    {
      id: "diagnostic",
      label: "Diagnóstico",
      icon: FileCode,
    },
    {
      id: "script",
      label: "Script Sniffer",
      icon: Terminal,
    },
  ];

  const downloadFile = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <header className="border-b border-slate-800 bg-slate-950 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between py-2.5 gap-3 border-b border-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold">
              <UserCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-100 text-sm tracking-tight">
                  Dofus Unity Sniffer
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/60">
                  TCP 5555
                </span>
              </div>
            </div>
          </div>

          {/* Quick download buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadFile("dofus_auditor.py", DOFUS_AUDITOR_PYTHON, "text/x-python")}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition shadow-sm"
              title="Descargar script en archivo .py"
            >
              <Download className="w-3.5 h-3.5" />
              dofus_auditor.py
            </button>

            <button
              onClick={() => downloadFile("items_database.json", ITEMS_DATABASE_JSON, "application/json")}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              title="Descargar base de datos de objetos en caché"
            >
              <Download className="w-3.5 h-3.5" />
              items_database.json
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <nav className="flex space-x-1 overflow-x-auto py-2 scrollbar-none">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`tab-btn-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap cursor-pointer ${
                  isActive
                    ? "bg-slate-800 text-sky-400 font-semibold border border-slate-700"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-sky-400" : "text-slate-400"}`} />
                <span>{tab.label}</span>
                {tab.badge !== undefined && tab.badge > 0 && (
                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                      isActive ? "bg-sky-900 text-sky-200" : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
