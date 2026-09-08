import express from "express";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";

const app = express();
const PORT = 3000;

app.use(express.json({ limit: "50mb" }));

// In-memory cache for Dofus items
const itemCache = new Map<number, { id: number; name: string; iconUrl?: string; level?: number }>();

// Seed item cache from local items_database.json
const itemsDbPath = path.join(process.cwd(), "items_database.json");
if (fs.existsSync(itemsDbPath)) {
  try {
    const rawDb = JSON.parse(fs.readFileSync(itemsDbPath, "utf-8"));
    Object.entries(rawDb).forEach(([idStr, item]: [string, any]) => {
      const id = Number(idStr);
      if (item && item.name) {
        itemCache.set(id, {
          id,
          name: item.name,
          iconUrl: item.iconUrl || `https://api.dofusdb.fr/img/items/${item.iconId || id}.png`,
          level: item.level || 1,
        });
      }
    });
  } catch (e) {
    console.error("Error cargando items_database.json:", e);
  }
}

export interface CombatFighter {
  name: string;
  isCurrentPlayer?: boolean;
  xp: number;
  kamas: number;
  drops: Array<{
    itemId: number;
    name: string;
    quantity: number;
    iconUrl?: string;
  }>;
}

export interface CombatRecord {
  id: string;
  timestamp: string;
  timeStr: string;
  durationSec?: number;
  fighters: CombatFighter[];
  packetCount: number;
  rawMessages: string[];
}

export interface PacketRecord {
  id: string;
  time: string;
  bytes: number;
  messages: Record<string, any>;
  raw_hex?: string;
  source: string;
}

// In-memory stores (initialized empty by default)
const combatStore: CombatRecord[] = [];
const packetStore: PacketRecord[] = [];

// Helper: resolve item info from DofusDB or Cache
async function resolveItem(itemId: number): Promise<{ id: number; name: string; iconUrl?: string; level?: number }> {
  if (itemCache.has(itemId)) {
    return itemCache.get(itemId)!;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    const resp = await fetch(`https://api.dofusdb.fr/items/${itemId}?lang=es`, {
      signal: controller.signal,
      headers: { "User-Agent": "DofusUnityCombatSniffer/1.0" },
    });
    clearTimeout(timeout);

    if (resp.ok) {
      const data = await resp.json();
      const n = data?.name;
      const name =
        (typeof n === "object" ? n.es || n.fr || n.en : typeof n === "string" ? n : "") || `Objeto #${itemId}`;
      const imgId = data?.img || data?.iconId || itemId;
      const result = {
        id: itemId,
        name: name.trim(),
        iconUrl: `https://api.dofusdb.fr/img/items/${imgId}.png`,
        level: data?.level || 1,
      };
      itemCache.set(itemId, result);
      return result;
    }
  } catch (err) {
    // ignore, fall back below
  }

  const fallback = {
    id: itemId,
    name: `Objeto #${itemId}`,
    iconUrl: `https://api.dofusdb.fr/img/items/${itemId}.png`,
    level: 1,
  };
  itemCache.set(itemId, fallback);
  return fallback;
}

// ================= API ROUTES =================
app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// Download dofus_auditor.py directly
app.get("/api/download/dofus_auditor.py", (_req, res) => {
  const filePath = path.join(process.cwd(), "dofus_auditor.py");
  if (fs.existsSync(filePath)) {
    res.download(filePath, "dofus_auditor.py");
  } else {
    res.status(404).send("File not found");
  }
});

// Download items_database.json directly
app.get("/api/download/items_database.json", (_req, res) => {
  const filePath = path.join(process.cwd(), "items_database.json");
  if (fs.existsSync(filePath)) {
    res.download(filePath, "items_database.json");
  } else {
    res.status(404).send("File not found");
  }
});

// Download ultimo_combate.json directly
app.get("/api/download/ultimo_combate.json", (_req, res) => {
  const filePath = path.join(process.cwd(), "ultimo_combate.json");
  if (fs.existsSync(filePath)) {
    res.download(filePath, "ultimo_combate.json");
  } else {
    res.status(404).send("File not found");
  }
});

// Get Current Audit State
app.get("/api/audit", (_req, res) => {
  const auditFile = path.join(process.cwd(), "auditoria_botin.json");
  if (fs.existsSync(auditFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(auditFile, "utf-8"));
      if (!data.config) data.config = { my_character_name: "" };
      if (!data.players) data.players = {};
      if (!data.settlements) data.settlements = [];
      return res.json(data);
    } catch (e) {}
  }
  res.json({ config: { my_character_name: "" }, players: {}, settlements: [], last_combat: null });
});

// Update Configuration (e.g. My Character Name)
app.post("/api/config", (req, res) => {
  const { my_character_name } = req.body || {};
  const cleanName = String(my_character_name || "").trim();
  const auditFile = path.join(process.cwd(), "auditoria_botin.json");
  let db: any = { config: { my_character_name: cleanName }, players: {}, settlements: [], last_combat: null };
  if (fs.existsSync(auditFile)) {
    try {
      db = JSON.parse(fs.readFileSync(auditFile, "utf-8"));
    } catch (e) {}
  }
  if (!db.config) db.config = {};
  db.config.my_character_name = cleanName;

  // Update is_me flag across registered players
  if (db.players) {
    Object.values(db.players).forEach((p: any) => {
      if (cleanName) {
        p.is_me = (p.name || "").trim().toLowerCase() === cleanName.toLowerCase();
      }
    });
  }

  try {
    fs.writeFileSync(auditFile, JSON.stringify(db, null, 2), "utf-8");
  } catch (e) {}
  res.json({ success: true, config: db.config, db });
});

// Reset Player Loot in Audit State
app.post("/api/audit/reset", (req, res) => {
  const { key, all } = req.body || {};
  const auditFile = path.join(process.cwd(), "auditoria_botin.json");
  let db: any = { players: {}, settlements: [], last_combat: null };
  if (fs.existsSync(auditFile)) {
    try {
      db = JSON.parse(fs.readFileSync(auditFile, "utf-8"));
    } catch (e) {}
  }
  if (!db.players) db.players = {};
  if (!db.settlements) db.settlements = [];

  const nowFull = new Date().toLocaleString("es-ES");
  if (all) {
    Object.values(db.players || {}).forEach((p: any) => {
      const drops = Object.values(p.pending_drops || {}) as any[];
      if (drops.length > 0) {
        const summary = drops.map(d => `${d.name} x${d.quantity}`).join(", ");
        const totalUnits = drops.reduce((sum, d) => sum + d.quantity, 0);
        db.settlements.unshift({
          date: nowFull,
          playerName: p.name,
          totalUnits,
          summary,
        });
        p.pending_drops = {};
      }
    });
  } else if (key && db.players && db.players[key]) {
    const p = db.players[key];
    const drops = Object.values(p.pending_drops || {}) as any[];
    if (drops.length > 0) {
      const summary = drops.map(d => `${d.name} x${d.quantity}`).join(", ");
      const totalUnits = drops.reduce((sum, d) => sum + d.quantity, 0);
      db.settlements.unshift({
        date: nowFull,
        playerName: p.name,
        totalUnits,
        summary,
      });
      p.pending_drops = {};
    }
  }
  try {
    fs.writeFileSync(auditFile, JSON.stringify(db, null, 2), "utf-8");
  } catch (e) {}
  res.json({ success: true, db });
});

// Simulate Combat Drops
app.post("/api/audit/simulate", (_req, res) => {
  const auditFile = path.join(process.cwd(), "auditoria_botin.json");
  let db: any = { players: {}, settlements: [], last_combat: null };
  if (fs.existsSync(auditFile)) {
    try {
      db = JSON.parse(fs.readFileSync(auditFile, "utf-8"));
    } catch (e) {}
  }
  if (!db.players) db.players = {};
  if (!db.settlements) db.settlements = [];

  const nowFull = new Date().toLocaleString("es-ES");
  const nowTime = new Date().toLocaleTimeString("es-ES");

  const myName = (db.config?.my_character_name || "Noinoi").trim();

  // Deadman-soldier
  if (!db.players["Deadman-soldier"]) {
    db.players["Deadman-soldier"] = {
      key: "Deadman-soldier",
      char_id: 250894876967,
      name: "Deadman-soldier",
      is_me: "Deadman-soldier".toLowerCase() === myName.toLowerCase(),
      combats_count: 0,
      last_seen: nowFull,
      pending_drops: {},
    };
  }
  const dP = db.players["Deadman-soldier"];
  dP.is_me = "Deadman-soldier".toLowerCase() === myName.toLowerCase();
  dP.combats_count += 1;
  dP.last_seen = nowFull;
  if (!dP.pending_drops["17123"]) {
    dP.pending_drops["17123"] = { itemId: 17123, name: "Carne picada", quantity: 0, level: 1, iconUrl: "https://api.dofusdb.fr/img/items/175008.png" };
  }
  dP.pending_drops["17123"].quantity += 4;
  if (!dP.pending_drops["6900"]) {
    dP.pending_drops["6900"] = { itemId: 6900, name: "Pluma de pío rojo", quantity: 0, level: 1, iconUrl: "https://api.dofusdb.fr/img/items/6900.png" };
  }
  dP.pending_drops["6900"].quantity += 2;

  // Noinoi
  if (!db.players["Noinoi"]) {
    db.players["Noinoi"] = {
      key: "Noinoi",
      char_id: 248675369255,
      name: "Noinoi",
      is_me: "Noinoi".toLowerCase() === myName.toLowerCase(),
      combats_count: 0,
      last_seen: nowFull,
      pending_drops: {},
    };
  }
  const nP = db.players["Noinoi"];
  nP.is_me = "Noinoi".toLowerCase() === myName.toLowerCase();
  nP.combats_count += 1;
  nP.last_seen = nowFull;
  if (!nP.pending_drops["17123"]) {
    nP.pending_drops["17123"] = { itemId: 17123, name: "Carne picada", quantity: 0, level: 1, iconUrl: "https://api.dofusdb.fr/img/items/175008.png" };
  }
  nP.pending_drops["17123"].quantity += 6;

  db.last_combat = {
    timestamp: nowFull,
    timeStr: nowTime,
    fighters: [
      { name: "Noinoi", is_me: "Noinoi".toLowerCase() === myName.toLowerCase(), drops: [{ itemId: 17123, name: "Carne picada", quantity: 6, iconUrl: "https://api.dofusdb.fr/img/items/175008.png" }] },
      { name: "Deadman-soldier", is_me: "Deadman-soldier".toLowerCase() === myName.toLowerCase(), drops: [{ itemId: 17123, name: "Carne picada", quantity: 4, iconUrl: "https://api.dofusdb.fr/img/items/175008.png" }, { itemId: 6900, name: "Pluma de pío rojo", quantity: 2, iconUrl: "https://api.dofusdb.fr/img/items/6900.png" }] }
    ]
  };

  try {
    fs.writeFileSync(auditFile, JSON.stringify(db, null, 2), "utf-8");
  } catch (e) {}
  res.json({ success: true, db });
});

// Query DofusDB Item with server caching
app.get("/api/dofusdb/item/:id", async (req, res) => {
  const itemId = parseInt(req.params.id, 10);
  if (isNaN(itemId)) {
    return res.status(400).json({ error: "Invalid item ID" });
  }
  const item = await resolveItem(itemId);
  res.json(item);
});

// Search item cache
app.get("/api/dofusdb/search", (req, res) => {
  const q = String(req.query.q || "").toLowerCase().trim();
  if (!q) {
    return res.json(Array.from(itemCache.values()).slice(0, 50));
  }
  const results = Array.from(itemCache.values()).filter(
    (item) => item.name.toLowerCase().includes(q) || String(item.id).includes(q)
  );
  res.json(results.slice(0, 50));
});

// Ingest combat result from Python script
app.post("/api/ingest/combat", async (req, res) => {
  try {
    const payload = req.body;
    if (!payload || !payload.fighters) {
      return res.status(400).json({ error: "Missing fighters array in combat payload" });
    }

    const combatId = `combat-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const now = new Date();
    const timeStr =
      payload.timeStr ||
      now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

    // Ensure item names are resolved
    const fighters: CombatFighter[] = [];
    for (const f of payload.fighters) {
      const resolvedDrops = [];
      for (const d of f.drops || []) {
        const itemInfo = await resolveItem(d.itemId);
        resolvedDrops.push({
          itemId: d.itemId,
          name: d.name || itemInfo.name,
          quantity: d.quantity || 1,
          iconUrl: itemInfo.iconUrl,
        });
      }
      fighters.push({
        name: f.name || "Jugador Desconocido",
        isCurrentPlayer: f.isCurrentPlayer ?? true,
        xp: f.xp || 0,
        kamas: f.kamas || 0,
        drops: resolvedDrops,
      });
    }

    const record: CombatRecord = {
      id: combatId,
      timestamp: now.toISOString(),
      timeStr,
      durationSec: payload.durationSec || 0,
      fighters,
      packetCount: payload.packetCount || 1,
      rawMessages: payload.rawMessages || ["jsn", "kuf"],
    };

    combatStore.unshift(record);
    if (combatStore.length > 50) combatStore.pop();

    res.json({ success: true, combatId, message: "Combat saved successfully" });
  } catch (err: any) {
    res.status(500).json({ error: err.message || "Failed to process combat" });
  }
});

// Ingest raw packet from Python sniffer
app.post("/api/ingest/packet", (req, res) => {
  try {
    const payload = req.body;
    if (!payload) return res.status(400).json({ error: "Empty packet body" });

    const pkt: PacketRecord = {
      id: `pkt-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
      time: payload.time || new Date().toLocaleTimeString(),
      bytes: payload.bytes || (payload.raw_hex ? Math.floor(payload.raw_hex.length / 2) : 0),
      messages: payload.messages || {},
      raw_hex: payload.raw_hex,
      source: payload.source || "TCP 5555",
    };

    packetStore.unshift(pkt);
    if (packetStore.length > 200) packetStore.pop();

    res.json({ success: true, id: pkt.id });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// List combats
app.get("/api/combats", (_req, res) => {
  res.json(combatStore);
});

// List packets
app.get("/api/packets", (_req, res) => {
  res.json(packetStore);
});

// Clear packets or combats
app.delete("/api/combats", (_req, res) => {
  combatStore.length = 0;
  res.json({ success: true, message: "Combats cleared" });
});

app.delete("/api/packets", (_req, res) => {
  packetStore.length = 0;
  res.json({ success: true, message: "Packets cleared" });
});

// Protobuf Varint decoder helper for the web API
function decodeVarint(buf: Buffer, offset: number): [number, number] {
  let val = 0;
  let shift = 0;
  let read = 0;
  while (offset + read < buf.length) {
    const b = buf[offset + read];
    read++;
    val |= (b & 0x7f) << shift;
    if ((b & 0x80) === 0) break;
    shift += 7;
    if (read > 10) break;
  }
  return [val, read];
}

function parseProtobufRecursive(buf: Buffer, depth = 3): any {
  if (depth <= 0 || buf.length === 0) return {};
  const res: Record<string, any> = {};
  let p = 0;

  while (p < buf.length) {
    const [tag, tbr] = decodeVarint(buf, p);
    p += tbr;
    if (tag === 0 || tag > 1000000) break;

    const field = tag >> 3;
    const wire = tag & 7;
    if (field === 0) break;

    if (wire === 0) {
      const [v, vbr] = decodeVarint(buf, p);
      p += vbr;
      res[`field_${field}_varint`] = v;
    } else if (wire === 2) {
      const [len, lbr] = decodeVarint(buf, p);
      p += lbr;
      if (p + len > buf.length) break;
      const sub = buf.subarray(p, p + len);
      p += len;

      // Try UTF-8 string
      try {
        const str = sub.toString("utf8");
        if (str.length > 0 && /^[\x20-\x7E\u00A0-\u00FF\u0100-\u017F]+$/.test(str)) {
          res[`field_${field}_string`] = str;
          continue;
        }
      } catch (e) {
        // not string
      }

      const subDecoded = parseProtobufRecursive(sub, depth - 1);
      if (Object.keys(subDecoded).length > 0) {
        res[`field_${field}_sub`] = subDecoded;
      } else {
        res[`field_${field}_hex`] = sub.toString("hex");
      }
    } else if (wire === 1) {
      p += 8;
    } else if (wire === 5) {
      p += 4;
    } else {
      break;
    }
  }
  return res;
}

// Decode raw hex endpoint
app.post("/api/decode-hex", (req, res) => {
  try {
    const { hex } = req.body;
    if (!hex || typeof hex !== "string") {
      return res.status(400).json({ error: "A valid hex string is required" });
    }
    const cleanHex = hex.replace(/[^0-9a-fA-F]/g, "");
    const buf = Buffer.from(cleanHex, "hex");

    const decoded = parseProtobufRecursive(buf, 4);

    // Look for string markers (e.g. character names or Ankama URIs)
    const asciiStr = buf.toString("latin1").replace(/[^\x20-\x7E]/g, ".");

    res.json({
      byteLength: buf.length,
      hexClean: cleanHex,
      asciiPreview: asciiStr,
      decoded,
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message || "Failed to decode hex" });
  }
});

// START SERVER & VITE
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Dofus Unity Sniffer server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
