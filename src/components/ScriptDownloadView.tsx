import React, { useState } from "react";
import { Download, Copy, Check, Terminal, FileCode, Database, ExternalLink } from "lucide-react";
import { DOFUS_AUDITOR_PYTHON, ITEMS_DATABASE_JSON } from "../data/scripts";

export const ScriptDownloadView: React.FC = () => {
  const [copiedScript, setCopiedScript] = useState(false);

  const handleCopyScript = () => {
    navigator.clipboard.writeText(DOFUS_AUDITOR_PYTHON);
    setCopiedScript(true);
    setTimeout(() => setCopiedScript(false), 2000);
  };

  const handleDownloadFile = (filename: string, content: string, mime: string) => {
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
    <div className="space-y-6">
      {/* Download Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Card 1: dofus_auditor.py */}
        <div className="p-5 rounded-xl border border-sky-800/60 bg-sky-950/20 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <FileCode className="w-5 h-5 text-sky-400" />
              <h3 className="font-semibold text-slate-100 text-base">dofus_auditor.py</h3>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-sky-900/60 text-sky-300 border border-sky-700/50">
                Script Principal
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Sniffer pasivo para Dofus Unity (puerto TCP 5555) con servidor web integrado (puerto 5000), base de datos de auditoría acumulativa por jugador y consola limpia sin paquetes repetitivos.
            </p>
          </div>

          <div className="flex items-center gap-2.5 pt-2">
            <button
              onClick={() => handleDownloadFile("dofus_auditor.py", DOFUS_AUDITOR_PYTHON, "text/x-python")}
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition shadow-sm"
            >
              <Download className="w-4 h-4" />
              Descargar dofus_auditor.py
            </button>
            <button
              onClick={handleCopyScript}
              className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              title="Copiar código al portapapeles"
            >
              {copiedScript ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Card 2: items_database.json */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-5 h-5 text-emerald-400" />
              <h3 className="font-semibold text-slate-100 text-base">items_database.json</h3>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60">
                Caché de Objetos
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Base de datos local con nombres en español de recursos de DofusDB. Permite que el script identifique los ítems al instante sin retrasos por peticiones web.
            </p>
          </div>

          <div className="flex items-center gap-2.5 pt-2">
            <button
              onClick={() => handleDownloadFile("items_database.json", ITEMS_DATABASE_JSON, "application/json")}
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 transition"
            >
              <Download className="w-4 h-4" />
              Descargar items_database.json
            </button>
          </div>
        </div>
      </div>

      {/* Setup Guide */}
      <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-4">
        <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-sky-400" />
          Instrucciones para ejecutar el script localmente
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/80 space-y-1.5">
            <span className="text-sky-400 font-semibold">Paso 1</span>
            <p className="text-slate-300 font-medium">Instalar dependencias</p>
            <code className="block p-2 rounded bg-slate-900 text-slate-300 font-mono text-[11px] select-all border border-slate-800">
              pip install scapy requests
            </code>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/80 space-y-1.5">
            <span className="text-sky-400 font-semibold">Paso 2</span>
            <p className="text-slate-300 font-medium">Ejecutar con tu personaje</p>
            <code className="block p-2 rounded bg-slate-900 text-slate-300 font-mono text-[11px] select-all border border-slate-800">
              python dofus_auditor.py -n "TuNombre"
            </code>
            <p className="text-[10px] text-slate-500">O sin flag y configurarlo en la web local.</p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/80 space-y-1.5">
            <span className="text-sky-400 font-semibold">Paso 3</span>
            <p className="text-slate-300 font-medium">Abrir la interfaz local</p>
            <code className="block p-2 rounded bg-slate-900 text-sky-400 font-mono text-[11px] border border-slate-800">
              http://localhost:5000
            </code>
            <p className="text-[10px] text-slate-500">Se abrirá automáticamente en tu navegador.</p>
          </div>
        </div>
      </div>

      {/* Code Preview */}
      <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950">
        <div className="px-4 py-2.5 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">dofus_auditor.py (código completo)</span>
          <button
            onClick={handleCopyScript}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition"
          >
            {copiedScript ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedScript ? "Copiado" : "Copiar código"}</span>
          </button>
        </div>
        <div className="max-h-96 overflow-y-auto p-4 text-xs font-mono text-slate-300">
          <pre>{DOFUS_AUDITOR_PYTHON.slice(0, 4000)}... (resto del script incluido en la descarga)</pre>
        </div>
      </div>
    </div>
  );
};
