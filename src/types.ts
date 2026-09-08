export interface CombatDrop {
  itemId: number;
  name: string;
  quantity: number;
  iconUrl?: string;
  level?: number;
}

export interface CombatFighter {
  name: string;
  isCurrentPlayer?: boolean;
  xp?: number;
  kamas?: number;
  drops: CombatDrop[];
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

export interface PendingDrop {
  itemId: number;
  name: string;
  quantity: number;
  level?: number;
  iconUrl?: string;
}

export interface AuditedPlayer {
  key: string;
  char_id?: number | null;
  name: string;
  is_me: boolean;
  combats_count: number;
  last_seen: string;
  pending_drops: Record<string, PendingDrop>;
}

export interface SettlementRecord {
  date: string;
  playerName: string;
  totalUnits: number;
  summary: string;
}

export interface AuditDbState {
  config?: {
    my_character_name?: string;
  };
  players: Record<string, AuditedPlayer>;
  settlements: SettlementRecord[];
  last_combat: any;
}

export interface PacketRecord {
  id: string;
  time: string;
  bytes: number;
  messages: Record<string, any>;
  raw_hex?: string;
  source: string;
}

export interface HexDecodeResponse {
  byteLength: number;
  hexClean: string;
  asciiPreview: string;
  decoded: Record<string, any>;
}

export interface ItemDetail {
  id: number;
  name: string;
  iconUrl?: string;
  level?: number;
}
