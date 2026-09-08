import React, { useState, useEffect } from "react";
import { AuditedPlayer, SettlementRecord, AuditDbState } from "../types";
import { RefreshCcw, Package, History, CheckCircle2, User, Save } from "lucide-react";

interface AuditorViewProps {
  auditState: AuditDbState;
  onRefresh: () => void;
  onResetPlayer: (playerKey: string) => Promise<void>;
  onResetAll: () => Promise<void>;
  onSimulateCombat: () => Promise<void>;
  onUpdateCharacterName: (name: string) => Promise<void>;
}

export const AuditorView: React.FC<AuditorViewProps> = ({
  auditState,
  onRefresh,
  onResetPlayer,
  onResetAll,
  onUpdateCharacterName,
}) => {
  const [resettingKey, setResettingKey] = useState<string | null>(null);
  const [charInput, setCharInput] = useState<string>("");
  const [isSavingName, setIsSavingName] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const configuredName = auditState.config?.my_character_name || "";

  useEffect(() => {
    if (configuredName) {
      setCharInput(configuredName);
    }
  }, [configuredName]);

  const handleSaveCharName = async (nameToSave?: string) => {
    const target = (nameToSave !== undefined ? nameToSave : charInput).trim();
    try {
      setIsSavingName(true);
      await onUpdateCharacterName(target);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } finally {
      setIsSavingName(false);
    }
  };

  const playersList: AuditedPlayer[] = Object.values(auditState.players || {});
  const settlements: SettlementRecord[] = auditState.settlements || [];

  const handleReset = async (key: string) => {
    try {
      setResettingKey(key);
      await onResetPlayer(key);
    } finally {
      setResettingKey(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Bar: Controls & Character configuration */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl border border-slate-800 bg-slate-900/80">
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="font-semibold text-slate-300">Mi Personaje:</span>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={charInput}
              onChange={(e) => setCharInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSaveCharName()}
              placeholder="Nombre en Dofus..."
              className="px-2.5 py-1.5 text-xs rounded-lg bg-slate-950 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 w-36 sm:w-44"
            />
            <button
              onClick={() => handleSaveCharName()}
              disabled={isSavingName}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition disabled:opacity-50"
            >
              {saveSuccess ? (
                <>
                  <CheckCircle2 className="w-3 h-3 text-emerald-300" />
                  <span>Listo</span>
                </>
              ) : (
                <>
                  <Save className="w-3 h-3" />
                  <span>{isSavingName ? "..." : "Guardar"}</span>
                </>
              )}
            </button>
          </div>
          {configuredName && (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/60">
              Activo: {configuredName}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 justify-end">
          {playersList.length > 0 && (
            <button
              onClick={onResetAll}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800/50 transition"
            >
              Reiniciar Todo a 0
            </button>
          )}

          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
          >
            <RefreshCcw className="w-3 h-3" />
            <span>Actualizar</span>
          </button>
        </div>
      </div>

      {/* Players Cards Grid */}
      {playersList.length === 0 ? (
        <div className="p-12 text-center rounded-xl border border-dashed border-slate-800 bg-slate-900/30">
          <Package className="w-10 h-10 text-slate-600 mx-auto mb-2.5" />
          <h3 className="text-sm font-medium text-slate-300">Sin combates registrados aún</h3>
          <p className="text-xs text-slate-500 mt-1">
            Esperando actividad de combate en Dofus...
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {playersList.map((player) => {
            const pendingDrops = Object.values(player.pending_drops || {});
            const totalUnits = pendingDrops.reduce((acc, d) => acc + d.quantity, 0);
            const isMe = player.is_me;

            return (
              <div
                key={player.key}
                className={`flex flex-col rounded-xl border transition-all ${
                  isMe
                    ? "border-sky-700/60 bg-slate-900/90 shadow-lg shadow-sky-950/20"
                    : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
                }`}
              >
                {/* Player Header */}
                <div className="p-3.5 border-b border-slate-800/80 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-100">{player.name}</span>
                    {isMe ? (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/50">
                        Tú
                      </span>
                    ) : (
                      <button
                        onClick={() => handleSaveCharName(player.name)}
                        title="Marcar como mi personaje"
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition"
                      >
                        Marcar como yo
                      </button>
                    )}
                  </div>

                  <div className="text-right">
                    <span className="text-xs font-bold text-sky-400">{totalUnits} uds</span>
                  </div>
                </div>

                {/* Items List with DofusDB icons, names and quantity */}
                <div className="p-3 flex-1">
                  {pendingDrops.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-500 flex flex-col items-center gap-1">
                      <CheckCircle2 className="w-5 h-5 text-emerald-500/50" />
                      <span>Al día (0 recursos pendientes)</span>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {pendingDrops.map((drop) => {
                        const iconSrc = drop.iconUrl || `https://api.dofusdb.fr/img/items/${drop.itemId}.png`;
                        return (
                          <div
                            key={drop.itemId}
                            className="flex items-center gap-2.5 p-1.5 px-2 rounded-lg bg-slate-950/60 border border-slate-800/60 hover:border-slate-700 transition"
                          >
                            <img
                              src={iconSrc}
                              alt={drop.name}
                              className="w-8 h-8 rounded object-contain bg-slate-900 border border-slate-800 p-0.5 shrink-0"
                              onError={(e) => {
                                (e.target as HTMLImageElement).src = `https://api.dofusdb.fr/img/items/${drop.itemId}.png`;
                              }}
                            />
                            <div className="flex-1 min-w-0">
                              <span className="text-xs font-medium text-slate-200 truncate block">
                                {drop.name}
                              </span>
                            </div>
                            <span className="text-xs font-bold text-sky-400 bg-sky-950/60 border border-sky-800/40 px-2 py-0.5 rounded shrink-0">
                              x{drop.quantity}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Reset Action */}
                <div className="p-3 pt-0 mt-auto">
                  <button
                    onClick={() => handleReset(player.key)}
                    disabled={pendingDrops.length === 0 || resettingKey === player.key}
                    className="w-full py-2 px-3 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-30 disabled:hover:bg-rose-600 disabled:cursor-not-allowed"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>{resettingKey === player.key ? "Liquidando..." : "Entregado - Reiniciar a 0"}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Settlements History */}
      {settlements.length > 0 && (
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2.5">
            <History className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
              Historial de Entregas
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="text-slate-400 border-b border-slate-800 pb-2">
                <tr>
                  <th className="py-2 px-3 font-semibold">Fecha</th>
                  <th className="py-2 px-3 font-semibold">Jugador</th>
                  <th className="py-2 px-3 font-semibold text-right">Total</th>
                  <th className="py-2 px-3 font-semibold">Detalle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {settlements.slice(0, 15).map((s, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/20">
                    <td className="py-2 px-3 text-slate-400 font-mono text-[11px]">{s.date}</td>
                    <td className="py-2 px-3 font-semibold text-slate-200">{s.playerName}</td>
                    <td className="py-2 px-3 text-right font-bold text-emerald-400">{s.totalUnits} uds</td>
                    <td className="py-2 px-3 text-slate-300 max-w-md truncate">{s.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
