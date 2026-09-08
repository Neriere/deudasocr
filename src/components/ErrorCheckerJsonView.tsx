import React, { useState } from "react";
import { AlertCircle, CheckCircle, FileCode, Upload, Play, Terminal } from "lucide-react";

export const ErrorCheckerJsonView: React.FC = () => {
  const [inputText, setInputText] = useState("");
  const [status, setStatus] = useState<"idle" | "valid" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [analysis, setAnalysis] = useState<{
    packetCount?: number;
    opcodesFound?: string[];
    potentialErrors?: string[];
    detectedFighters?: string[];
    sampleParsed?: any;
  } | null>(null);

  const loadUltimoCombate = async () => {
    try {
      const res = await fetch("/api/download/ultimo_combate.json");
      if (res.ok) {
        const text = await res.text();
        setInputText(text);
        validateAndAnalyze(text);
      } else {
        setErrorMessage("No se encontró ultimo_combate.json en el servidor.");
        setStatus("error");
      }
    } catch (e: any) {
      setErrorMessage(e.message);
      setStatus("error");
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setInputText(content);
      validateAndAnalyze(content);
    };
    reader.readAsText(file);
  };

  const validateAndAnalyze = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      setStatus("idle");
      setAnalysis(null);
      setErrorMessage("");
      return;
    }

    try {
      const parsed = JSON.parse(trimmed);
      setStatus("valid");
      setErrorMessage("");

      const packets = Array.isArray(parsed) ? parsed : [parsed];
      const opcodes = new Set<string>();
      const fighters = new Set<string>();
      const potentialErrors: string[] = [];

      packets.forEach((pkt, idx) => {
        const hex = pkt.raw_hex || "";
        if (!hex && !pkt.messages) {
          potentialErrors.push(`Paquete #${idx + 1}: No contiene 'raw_hex' ni 'messages'.`);
        }
        if (hex) {
          try {
            const buf = hex.match(/.{1,2}/g)?.map((byte: string) => parseInt(byte, 16));
            if (!buf) {
              potentialErrors.push(`Paquete #${idx + 1}: Cadena hex inválida.`);
            }
          } catch {
            potentialErrors.push(`Paquete #${idx + 1}: Error al parsear hex.`);
          }
        }

        // Buscar firmas de Ankama en el texto o hex
        const strRep = JSON.stringify(pkt);
        const knownOpcodes = ["jyg", "jsn", "kuf", "idu", "kmv", "jss", "hpm", "kqo", "kqy", "lzp", "jxo"];
        knownOpcodes.forEach((op) => {
          if (strRep.includes(`ankama.com/${op}`) || strRep.includes(`"${op}"`)) {
            opcodes.add(op);
          }
        });

        // Buscar nombres posibles
        const nameMatches = strRep.match(/([A-Z][a-z0-9_-]{2,15})/g);
        if (nameMatches) {
          nameMatches.forEach((nm) => {
            if (!["Type", "Ankama", "Combat", "Object", "True", "False", "None"].includes(nm)) {
              fighters.add(nm);
            }
          });
        }
      });

      if (!opcodes.has("jyg") && !opcodes.has("kuf") && !opcodes.has("idu")) {
        potentialErrors.push("Aviso: No se detectaron opcodes de recompensa de combate ('jyg', 'kuf' o 'idu'). Podría tratarse de un paquete de movimiento o mapa.");
      }

      setAnalysis({
        packetCount: packets.length,
        opcodesFound: Array.from(opcodes),
        potentialErrors,
        detectedFighters: Array.from(fighters).slice(0, 8),
        sampleParsed: packets[0],
      });
    } catch (e: any) {
      setStatus("error");
      setErrorMessage(`Error de sintaxis JSON: ${e.message}`);
      setAnalysis(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/70 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            <FileCode className="w-5 h-5 text-sky-400" />
            Comprobador y Validador de JSON / Paquetes
          </h2>
          <p className="text-sm text-slate-400">
            Valida archivos generados por el sniffer (<code className="text-slate-300">ultimo_combate.json</code>) para diagnosticar errores de decodificación o cambios de Ankama.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadUltimoCombate}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition"
          >
            <Play className="w-3.5 h-3.5" />
            Cargar ultimo_combate.json
          </button>

          <label className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 cursor-pointer transition">
            <Upload className="w-3.5 h-3.5" />
            Subir archivo JSON
            <input type="file" accept=".json" onChange={handleFileUpload} className="hidden" />
          </label>
        </div>
      </div>

      {/* Input Textarea */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Entrada de Texto JSON
          </span>
          {status === "valid" && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
              <CheckCircle className="w-3.5 h-3.5" />
              JSON Válido
            </span>
          )}
          {status === "error" && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-400">
              <AlertCircle className="w-3.5 h-3.5" />
              Error de Formato
            </span>
          )}
        </div>

        <textarea
          value={inputText}
          onChange={(e) => {
            setInputText(e.target.value);
            validateAndAnalyze(e.target.value);
          }}
          placeholder="Pega aquí el contenido de un JSON de combate o haz clic en 'Cargar ultimo_combate.json'..."
          rows={10}
          className="w-full bg-slate-950 font-mono text-xs text-slate-300 p-3 rounded-lg border border-slate-800 focus:outline-none focus:border-sky-500"
        />

        {errorMessage && (
          <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800/60 text-xs text-rose-300 font-mono flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* Analysis Results */}
      {analysis && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60">
            <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Paquetes Totales</h4>
            <p className="text-2xl font-bold text-sky-400">{analysis.packetCount}</p>
            <p className="text-xs text-slate-500 mt-1">Ráfagas capturadas en el archivo</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60">
            <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Mensajes Protobuf Ankama</h4>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {analysis.opcodesFound && analysis.opcodesFound.length > 0 ? (
                analysis.opcodesFound.map((op) => (
                  <span key={op} className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-sky-300 border border-slate-700">
                    type.ankama.com/{op}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">Ningún opcode estándar detectado</span>
              )}
            </div>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60">
            <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Nombres Detectados</h4>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {analysis.detectedFighters && analysis.detectedFighters.length > 0 ? (
                analysis.detectedFighters.map((nm) => (
                  <span key={nm} className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    {nm}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">Sin nombres claros</span>
              )}
            </div>
          </div>

          {analysis.potentialErrors && analysis.potentialErrors.length > 0 && (
            <div className="md:col-span-3 p-4 rounded-xl border border-amber-800/50 bg-amber-950/20 text-xs text-amber-300 space-y-1">
              <h4 className="font-semibold flex items-center gap-1.5 mb-2">
                <AlertCircle className="w-4 h-4" />
                Diagnóstico de estructura:
              </h4>
              {analysis.potentialErrors.map((err, i) => (
                <p key={i}>• {err}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
