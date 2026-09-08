#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
AUDITOR DE BOTIN Y CONTROL DE ENTREGAS - DOFUS UNITY
================================================================================
- Captura pasiva de paquetes en TCP 5555 sin spam en consola.
- Muestra el botin obtenido por cada jugador sin XP ni Kamas.
- Registra y acumula los recursos dropeados en 'auditoria_botin.json'.
- Servidor web local integrado en http://localhost:5000 para consultar
  en tiempo real que recursos debe entregarte cada companero y resetearlos.
================================================================================
"""

import sys
import os
import time
import json
import socket
import threading
import argparse
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Intentar importar Scapy
try:
    from scapy.all import sniff, TCP, Raw
except ImportError:
    sniff, TCP, Raw = None, None, None

# Configuracion general
DOFUS_PORT = 5555
HTTP_PORT = 5000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_DB_FILE = os.path.join(BASE_DIR, "auditoria_botin.json")
ITEMS_DB_FILE = os.path.join(BASE_DIR, "items_database.json")
PLAYERS_CACHE_FILE = os.path.join(BASE_DIR, "jugadores_conocidos.json")
LAST_COMBAT_FILE = os.path.join(BASE_DIR, "ultimo_combate.json")

# Nombre de tu personaje principal (puedes escribirlo aqui o cambiarlo desde http://localhost:5000)
MY_CHARACTER_NAME = ""

# Variables de estado en memoria
KNOWN_CHARACTERS = {}      # {int(char_id): "Nombre"}
ITEMS_CACHE = {}           # {int(item_id): {"name": ..., "level": ...}}
AUDIT_DB = {
    "config": {
        "my_character_name": MY_CHARACTER_NAME
    },
    "players": {},         # {str(char_id): {"name": ..., "pending_drops": {...}, ...}}
    "settlements": [],     # Historial de entregas realizadas
    "last_combat": None    # Ultimo combate procesado
}

capture_buffer = []
is_in_combat_burst = False
last_packet_time = 0
last_trailing_packet_data = b""
sse_clients = []
db_lock = threading.Lock()
is_printing_summary = False

# ==============================================================================
# CARGA Y PERSISTENCIA DE DATOS
# ==============================================================================

def load_items_db():
    global ITEMS_CACHE
    if os.path.exists(ITEMS_DB_FILE):
        try:
            with open(ITEMS_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    try:
                        ITEMS_CACHE[int(k)] = v
                    except ValueError:
                        pass
        except Exception:
            pass

def save_items_db():
    try:
        data = {str(k): v for k, v in ITEMS_CACHE.items()}
        with open(ITEMS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def get_item_info(item_id):
    if not item_id:
        return {"name": f"Objeto #{item_id}", "level": 1, "iconUrl": f"https://api.dofusdb.fr/img/items/{item_id}.png"}
    item_id = int(item_id)
    if item_id in ITEMS_CACHE:
        info = ITEMS_CACHE[item_id]
        if info.get("iconId") and info.get("iconUrl") and not info["iconUrl"].endswith(f"/{item_id}.png"):
            return info

    # Consulta puntual a DofusDB si no existe en la base local o falta el iconId oficial
    try:
        url = f"https://api.dofusdb.fr/items/{item_id}?lang=es"
        req = urllib.request.Request(url, headers={"User-Agent": "DofusAuditor/1.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                name_field = data.get("name", {})
                if isinstance(name_field, dict):
                    name = name_field.get("es") or name_field.get("fr") or name_field.get("en")
                else:
                    name = str(name_field)
                
                img = data.get("img") or data.get("iconId")
                if img:
                    icon_url = str(img) if str(img).startswith("http") else f"https://api.dofusdb.fr/img/items/{img}.png"
                else:
                    icon_url = f"https://api.dofusdb.fr/img/items/{item_id}.png"

                info = {
                    "name": (name or f"Objeto #{item_id}").strip(),
                    "level": data.get("level", 1),
                    "iconId": data.get("iconId"),
                    "iconUrl": icon_url
                }
                ITEMS_CACHE[item_id] = info
                save_items_db()
                return info
    except Exception:
        pass

    fallback = {"name": f"Objeto #{item_id}", "level": 1, "iconUrl": f"https://api.dofusdb.fr/img/items/{item_id}.png"}
    ITEMS_CACHE[item_id] = fallback
    return fallback

def load_known_players():
    global KNOWN_CHARACTERS
    if os.path.exists(PLAYERS_CACHE_FILE):
        try:
            with open(PLAYERS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    try:
                        KNOWN_CHARACTERS[int(k)] = str(v)
                    except ValueError:
                        pass
        except Exception:
            pass

def save_known_player(char_id, name):
    if not char_id or not name:
        return
    cid = int(char_id)
    if KNOWN_CHARACTERS.get(cid) == name:
        return
    KNOWN_CHARACTERS[cid] = name
    try:
        with open(PLAYERS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(KNOWN_CHARACTERS, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def load_audit_db():
    global AUDIT_DB, MY_CHARACTER_NAME
    if os.path.exists(AUDIT_DB_FILE):
        try:
            with open(AUDIT_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    AUDIT_DB = data
                    if "config" not in AUDIT_DB:
                        AUDIT_DB["config"] = {"my_character_name": MY_CHARACTER_NAME}
                    else:
                        loaded_name = AUDIT_DB["config"].get("my_character_name")
                        if loaded_name:
                            MY_CHARACTER_NAME = loaded_name
                    if "players" not in AUDIT_DB:
                        AUDIT_DB["players"] = {}
                    if "settlements" not in AUDIT_DB:
                        AUDIT_DB["settlements"] = []
        except Exception:
            pass
    if "config" not in AUDIT_DB:
        AUDIT_DB["config"] = {"my_character_name": MY_CHARACTER_NAME}

def save_audit_db():
    with db_lock:
        try:
            if "config" not in AUDIT_DB:
                AUDIT_DB["config"] = {}
            if MY_CHARACTER_NAME and not AUDIT_DB["config"].get("my_character_name"):
                AUDIT_DB["config"]["my_character_name"] = MY_CHARACTER_NAME
            with open(AUDIT_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(AUDIT_DB, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def notify_sse_clients():
    data_str = json.dumps({"type": "UPDATE", "timestamp": time.time()})
    msg = f"data: {data_str}\n\n".encode("utf-8")
    dead = []
    for client in sse_clients:
        try:
            client.wfile.write(msg)
            client.wfile.flush()
        except Exception:
            dead.append(client)
    for d in dead:
        if d in sse_clients:
            sse_clients.remove(d)

# Cargar bases de datos iniciales
load_items_db()
load_known_players()
load_audit_db()

# ==============================================================================
# DECODIFICADOR DE PROTOBUF Y EXTRACTOR DE JUGADORES
# ==============================================================================

def decode_varint(buf, offset):
    val = 0
    shift = 0
    read = 0
    while offset + read < len(buf):
        b = buf[offset + read]
        read += 1
        val |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
        if read > 10:
            break
    return val, read

def encode_varint(val):
    res = bytearray()
    while val > 0x7F:
        res.append((val & 0x7F) | 0x80)
        val >>= 7
    res.append(val & 0x7F)
    return bytes(res)

def extract_all_player_names_and_ids(raw):
    found_pairs = {}
    found_names = []
    
    SYSTEM_WORDS = {
        "type.ankama.com", "ankama", "protobuf", "damage", "health", "water", 
        "earth", "fire", "air", "kuf", "jyg", "jsn", "jss", "idu", "iom", 
        "jru", "lqu", "kub", "kml", "kmp", "ktz", "lzp", "jxo", "iwf", "iwm"
    }
    
    p = 0
    while p < len(raw) - 4:
        if raw[p] == 0x0a:
            slen, lr = decode_varint(raw, p + 1)
            if lr > 0 and 2 <= slen <= 25 and p + 1 + lr + slen <= len(raw):
                sbytes = raw[p + 1 + lr : p + 1 + lr + slen]
                try:
                    s = sbytes.decode("utf-8")
                    if all(c.isalnum() or c in "-_" for c in s) and not s.isdigit():
                        if s.lower() not in SYSTEM_WORDS and not s.startswith("http"):
                            if s not in found_names:
                                found_names.append(s)
                            
                            w_start = max(0, p - 350)
                            w_end = min(len(raw), p + 1 + lr + slen + 350)
                            win = raw[w_start:w_end]
                            
                            wp = 0
                            best_id = None
                            best_dist = 999999
                            while wp < len(win):
                                tag, tr = decode_varint(win, wp)
                                if tr > 0 and (tag & 7) == 0:
                                    val, vr = decode_varint(win, wp + tr)
                                    if 100_000_000_000 < val < 10_000_000_000_000:
                                        dist = abs((w_start + wp) - p)
                                        if tag == 0x18 or dist < best_dist:
                                            best_dist = dist
                                            best_id = val
                                wp += 1
                                
                            if best_id:
                                found_pairs[best_id] = s
                except Exception:
                    pass
        p += 1
    return found_pairs, found_names

def find_name_for_char_id_in_packets(char_id, packets):
    if not char_id:
        return None
    vb = encode_varint(char_id)
    
    SYSTEM_WORDS = {
        "type.ankama.com", "ankama", "protobuf", "damage", "health", "water", 
        "earth", "fire", "air", "kuf", "jyg", "jsn", "jss", "idu", "iwf", "iwm"
    }
    
    for pkt in packets:
        raw = bytes.fromhex(pkt.get("raw_hex", ""))
        pos = 0
        while True:
            idx = raw.find(vb, pos)
            if idx == -1: break
            w_start = max(0, idx - 450)
            w_end = min(len(raw), idx + len(vb) + 450)
            win = raw[w_start:w_end]
            
            p = 0
            best_name = None
            min_dist = 999999
            while p < len(win) - 4:
                if win[p] == 0x0a:
                    slen, lr = decode_varint(win, p + 1)
                    if lr > 0 and 2 <= slen <= 25 and p + 1 + lr + slen <= len(win):
                        sbytes = win[p + 1 + lr : p + 1 + lr + slen]
                        try:
                            s = sbytes.decode("utf-8")
                            if all(c.isalnum() or c in "-_" for c in s) and not s.isdigit():
                                if s.lower() not in SYSTEM_WORDS and not s.startswith("http"):
                                    dist = abs((w_start + p) - idx)
                                    if dist < min_dist:
                                        min_dist = dist
                                        best_name = s
                        except Exception:
                            pass
                p += 1
            if best_name:
                return best_name
            pos = idx + len(vb)
    return None

def deep_decode_protobuf(buf, max_depth=3):
    if max_depth <= 0 or not buf:
        return {}
    res = {}
    p = 0
    while p < len(buf):
        tag_info = decode_varint(buf, p)
        tag = tag_info[0]
        p += tag_info[1]
        if tag == 0 or tag > 1000000:
            break
        
        field = tag >> 3
        wire = tag & 7
        if field == 0:
            break

        if wire == 0:
            v, vbr = decode_varint(buf, p); p += vbr
            res[f"f_{field}_int"] = v
        elif wire == 2:
            l, lbr = decode_varint(buf, p); p += lbr
            if p + l > len(buf): break
            sub = buf[p:p + l]; p += l
            try:
                txt = sub.decode("utf-8")
                if len(txt) > 0 and all(32 <= ord(c) < 127 or ord(c) > 160 for c in txt):
                    res[f"f_{field}_str"] = txt
                    continue
            except Exception:
                pass
            sub_decoded = deep_decode_protobuf(sub, max_depth - 1)
            if sub_decoded:
                res[f"f_{field}_sub"] = sub_decoded
            else:
                res[f"f_{field}_hex"] = sub[:32].hex()
        elif wire == 1: p += 8
        elif wire == 5: p += 4
        else: break
    return res

def parse_kuf_xp(payload):
    idx = payload.find(b"type.ankama.com/kuf")
    if idx == -1: return None
    off_12 = payload.find(b"\x12", idx, idx + 30)
    if off_12 == -1: return None
    plen, br = decode_varint(payload, off_12 + 1)
    p_data = payload[off_12 + 1 + br : off_12 + 1 + br + plen]
    if not p_data: return None
    v, _ = decode_varint(p_data, 1)
    return v if v > 0 else None

def extract_all_fighters_from_jyg(payload):
    fighters = []
    idx = payload.find(b"type.ankama.com/jyg")
    if idx == -1:
        idx = payload.find(b"/jyg")
    if idx == -1:
        idx = payload.find(b"jyg")
    if idx == -1:
        return fighters
    off_12 = payload.find(b"\x12", idx, idx + 35)
    if off_12 == -1:
        return fighters
    
    plen, br = decode_varint(payload, off_12 + 1)
    body = payload[off_12 + 1 + br : off_12 + 1 + br + plen]
    
    p = 0
    while p < len(body):
        tag, tr = decode_varint(body, p); p += tr
        if tag == 0: break
        f = tag >> 3; w = tag & 7
        if w == 2 and f == 2:
            l, lr = decode_varint(body, p); p += lr
            sub = body[p : p + l]; p += l
            
            char_id = None
            xp_val = 0
            kamas_val = 0
            drops = {}
            level_val = 0
            
            sp = 0
            while sp < len(sub):
                stag, str_ = decode_varint(sub, sp); sp += str_
                if stag == 0: break
                sf = stag >> 3; sw = stag & 7
                if sw == 0:
                    sv, svr = decode_varint(sub, sp); sp += svr
                elif sw == 2:
                    sl, slr = decode_varint(sub, sp); sp += slr
                    ssub = sub[sp : sp + sl]; sp += sl
                    if sf == 2:
                        ssp = 0
                        while ssp < len(ssub):
                            mtag, mtr = decode_varint(ssub, ssp); ssp += mtr
                            if mtag == 0: break
                            mf = mtag >> 3; mw = mtag & 7
                            if mw == 0:
                                mv, mvr = decode_varint(ssub, ssp); ssp += mvr
                                if mf == 1 and mv > 0:
                                    kamas_val = mv
                            elif mw == 2:
                                ml, mlr = decode_varint(ssub, ssp); ssp += mlr
                                dblock = ssub[ssp : ssp + ml]; ssp += ml
                                dp = 0
                                while dp < len(dblock):
                                    dtag, dtr = decode_varint(dblock, dp); dp += dtr
                                    if dtag == 0: break
                                    df = dtag >> 3; dw = dtag & 7
                                    if dw == 0:
                                        dv, dvr = decode_varint(dblock, dp); dp += dvr
                                    elif dw == 2:
                                        dl, dlr = decode_varint(dblock, dp); dp += dlr
                                        dsub = dblock[dp : dp + dl]; dp += dl
                                        if df == 1:
                                            qp = 0
                                            i_id, i_qty = 0, 1
                                            while qp < len(dsub):
                                                qtag, qtr = decode_varint(dsub, qp); qp += qtr
                                                if qtag == 0: break
                                                qf = qtag >> 3; qw = qtag & 7
                                                if qw == 0:
                                                    qv, qvr = decode_varint(dsub, qp); qp += qvr
                                                    if qf == 2: i_qty = qv
                                                    elif qf == 4: i_id = qv
                                                elif qw == 2:
                                                    ql, qlr = decode_varint(dsub, qp); qp += qlr + ql
                                                else: break
                                            if i_id > 0:
                                                drops[i_id] = drops.get(i_id, 0) + i_qty
                                    else: break
                    elif sf == 3:
                        cp = 0
                        while cp < len(ssub):
                            ctag, ctr = decode_varint(ssub, cp); cp += ctr
                            if ctag == 0: break
                            cf = ctag >> 3; cw = ctag & 7
                            if cw == 0:
                                cv, cvr = decode_varint(ssub, cp); cp += cvr
                                if cf == 1: char_id = cv
                            elif cw == 2:
                                cl, clr = decode_varint(ssub, cp); cp += clr
                                xp_sub = ssub[cp : cp + cl]; cp += cl
                                dec_xp = deep_decode_protobuf(xp_sub, 4)
                                level_val = dec_xp.get("f_2_int", 0)
                                try:
                                    f1 = dec_xp.get("f_1_sub", {})
                                    f2 = f1.get("f_2_sub", {})
                                    if "f_1_int" in f2:
                                        xp_val = f2["f_1_int"]
                                except Exception:
                                    pass
                else: break
            
            # Filtro: Solo jugadores reales (ID positivo < 10^12 o con recompensas / XP)
            if (char_id is not None and 0 < char_id < 1000000000000) or kamas_val > 0 or drops or xp_val > 0:
                fighters.append({
                    "char_id": char_id,
                    "kamas": kamas_val,
                    "drops": drops,
                    "xp": xp_val,
                    "level": level_val
                })
        elif w == 0:
            v, vr = decode_varint(body, p); p += vr
        else: break
            
    return fighters

def extract_player_identities_jsn(packets):
    id_to_name = {}
    ordered_names = []
    
    for pkt in packets:
        raw = bytes.fromhex(pkt.get("raw_hex", ""))
        pos = 0
        while True:
            idx = raw.find(b"type.ankama.com/jsn", pos)
            if idx == -1: break
            pos = idx + 19
            off_12 = raw.find(b"\x12", idx, idx + 35)
            if off_12 == -1: continue
            plen, br = decode_varint(raw, off_12 + 1)
            body = raw[off_12 + 1 + br : off_12 + 1 + br + plen]
            
            p = 0
            while p < len(body):
                tag, tr = decode_varint(body, p); p += tr
                if tag == 0: break
                f = tag >> 3; w = tag & 7
                if w == 2:
                    l, lr = decode_varint(body, p); p += lr
                    sub = body[p : p + l]; p += l
                    if f == 1:
                        cid = None
                        cname = None
                        sp = 0
                        while sp < len(sub):
                            stag, str_ = decode_varint(sub, sp); sp += str_
                            if stag == 0: break
                            sf = stag >> 3; sw = stag & 7
                            if sw == 0:
                                sv, svr = decode_varint(sub, sp); sp += svr
                                if sf == 3 and 0 < sv < 1000000000000:
                                    cid = sv
                            elif sw == 2:
                                sl, slr = decode_varint(sub, sp); sp += slr
                                ssub = sub[sp : sp + sl]; sp += sl
                                if sf == 2:
                                    for o in range(len(ssub) - 2):
                                        if ssub[o] == 0x0a:
                                            slen, sbr = decode_varint(ssub, o + 1)
                                            if 2 <= slen <= 25 and o + 1 + sbr + slen <= len(ssub):
                                                try:
                                                    s = ssub[o + 1 + sbr : o + 1 + sbr + slen].decode("utf-8")
                                                    if all(c.isalnum() or c in "-_" for c in s) and not s.isdigit():
                                                        cname = s
                                                        if s not in ordered_names:
                                                            ordered_names.append(s)
                                                except Exception:
                                                    pass
                            else: break
                        if cid and cname:
                            id_to_name[cid] = cname
                elif w == 0:
                    _, vr = decode_varint(body, p); p += vr
                else: break
    return id_to_name, ordered_names

def parse_idu_inventory(payload):
    drops = []
    start = 0
    while True:
        idx = payload.find(b"idu", start)
        if idx == -1: break
        start = idx + 3
        off_12 = payload.find(b"\x12", idx, idx + 25)
        if off_12 == -1: continue
        plen, br = decode_varint(payload, off_12 + 1)
        p_data = payload[off_12 + 1 + br : off_12 + 1 + br + plen]
        p = 0
        while p < len(p_data):
            tag, tbr = decode_varint(p_data, p); p += tbr
            wire = tag & 7
            if wire == 0:
                v, vbr = decode_varint(p_data, p); p += vbr
            elif wire == 2:
                l, lbr = decode_varint(p_data, p); p += lbr
                sub = p_data[p : p + l]; p += l
                sp, item_id, qty = 0, 0, 1
                while sp < len(sub):
                    stag, stbr = decode_varint(sub, sp); sp += stbr
                    swire = stag & 7
                    sfield = stag >> 3
                    if swire == 0:
                        sv, svbr = decode_varint(sub, sp); sp += svbr
                        if sfield in (1, 2) and sv > 10 and item_id == 0: item_id = sv
                        elif sfield in (3, 4, 5) and 0 < sv < 1000: qty = sv
                    elif swire == 2:
                        sl, slbr = decode_varint(sub, sp); sp += slbr + sl
                    else: break
                if item_id > 10: drops.append((item_id, qty))
            else: break
    return drops

# ==============================================================================
# PROCESAMIENTO Y AUDITORIA
# ==============================================================================

def process_combat_and_update_db(packets_captured):
    global is_printing_summary, AUDIT_DB
    
    # Ensamblar flujo TCP continuo para evitar pérdidas por segmentación de paquetes
    full_stream = b"".join([bytes.fromhex(pkt.get("raw_hex", "")) for pkt in packets_captured])
    
    # 1. Extraer nombres desde jsn (probando flujo continuo y paquetes individuales)
    id_to_name, ordered_names = extract_player_identities_jsn([{"raw_hex": full_stream.hex()}] + packets_captured)
    
    # 2. Recompensas de luchadores desde jyg (flujo continuo primero)
    raw_fighters = extract_all_fighters_from_jyg(full_stream)
    if not raw_fighters:
        for pkt in packets_captured:
            payload = bytes.fromhex(pkt.get("raw_hex", ""))
            if b"jyg" in payload:
                extracted = extract_all_fighters_from_jyg(payload)
                if extracted:
                    raw_fighters = extracted
                    break

    # 3. Objetos directos de inventario desde idu
    idu_drops = parse_idu_inventory(full_stream)
    if not idu_drops:
        for pkt in packets_captured:
            payload = bytes.fromhex(pkt.get("raw_hex", ""))
            if b"idu" in payload:
                for item_id, qty in parse_idu_inventory(payload):
                    idu_drops.append((item_id, qty))
    
    # 4. Resolver nombre y botin de cada jugador
    my_target_name = (AUDIT_DB.get("config", {}).get("my_character_name") or MY_CHARACTER_NAME or "").strip().lower()
    processed_fighters = []
    if raw_fighters:
        temp_fighters = []
        my_fighter_idx = None

        for i, f in enumerate(raw_fighters):
            cid = f.get("char_id")
            pname = None

            # 1. Base de datos conocida
            if cid and cid in KNOWN_CHARACTERS:
                pname = KNOWN_CHARACTERS[cid]

            # 2. Busqueda exacta de varint en los paquetes
            if not pname and cid:
                pname = find_name_for_char_id_in_packets(cid, packets_captured)

            # 3. Mapeo jsn
            if not pname and cid:
                pname = id_to_name.get(cid)

            # 4. Nombre ordenado
            if not pname and i < len(ordered_names):
                pname = ordered_names[i]

            # 5. Fallback
            if not pname:
                pname = f"Jugador_{cid}" if cid else f"Luchador_{i + 1}"
            elif cid:
                save_known_player(cid, pname)

            temp_fighters.append((cid, pname, f.get("drops", {})))
            if my_target_name and pname.strip().lower() == my_target_name:
                my_fighter_idx = i

        # Si no se configuró nombre o no coincidió, el primer luchador se toma por defecto
        if my_fighter_idx is None:
            my_fighter_idx = 0

        for i, (cid, pname, raw_drops) in enumerate(temp_fighters):
            is_me = (i == my_fighter_idx)
            fdrops = dict(raw_drops)
            if is_me and idu_drops:
                for i_id, i_qty in idu_drops:
                    if i_id not in fdrops:
                        fdrops[i_id] = fdrops.get(i_id, 0) + i_qty

            processed_fighters.append({
                "char_id": cid,
                "name": pname,
                "is_me": is_me,
                "drops": fdrops
            })
    else:
        main_name = AUDIT_DB.get("config", {}).get("my_character_name") or (ordered_names[0] if ordered_names else "Mi_Personaje")
        solo_drops = {}
        for i_id, i_qty in idu_drops:
            solo_drops[i_id] = solo_drops.get(i_id, 0) + i_qty
        processed_fighters.append({
            "char_id": None,
            "name": main_name,
            "is_me": True,
            "drops": solo_drops
        })

    # Pre-cargar informacion de items
    for f in processed_fighters:
        for item_id in f["drops"].keys():
            get_item_info(item_id)

    # Actualizar base de datos de auditoria acumulada
    now_str = datetime.now().strftime("%H:%M:%S")
    now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    combat_summary_for_web = []
    
    with db_lock:
        for f in processed_fighters:
            pname = f["name"]
            cid_key = str(f["char_id"]) if f["char_id"] else pname
            
            # Buscar si ya existe por char_id O por nombre para no duplicar fichas
            matched_key = None
            if cid_key in AUDIT_DB["players"]:
                matched_key = cid_key
            else:
                for k, p in AUDIT_DB["players"].items():
                    if p.get("name", "").strip().lower() == pname.strip().lower():
                        matched_key = k
                        break
            
            if not matched_key:
                matched_key = cid_key
                AUDIT_DB["players"][matched_key] = {
                    "key": matched_key,
                    "char_id": f["char_id"],
                    "name": pname,
                    "is_me": f["is_me"],
                    "combats_count": 0,
                    "last_seen": now_full,
                    "pending_drops": {}
                }
            elif f["char_id"] and matched_key == pname and cid_key != pname:
                # Migrar de clave por nombre a clave por char_id
                AUDIT_DB["players"][cid_key] = AUDIT_DB["players"].pop(pname)
                matched_key = cid_key
                AUDIT_DB["players"][matched_key]["key"] = cid_key
                AUDIT_DB["players"][matched_key]["char_id"] = f["char_id"]
            
            # Limpiar clave huérfana de nombre si existe por separado
            if matched_key != pname and pname in AUDIT_DB["players"]:
                old_p = AUDIT_DB["players"].pop(pname)
                AUDIT_DB["players"][matched_key]["combats_count"] += old_p.get("combats_count", 0)
                for oid, oitem in old_p.get("pending_drops", {}).items():
                    if oid not in AUDIT_DB["players"][matched_key]["pending_drops"]:
                        AUDIT_DB["players"][matched_key]["pending_drops"][oid] = oitem
                    else:
                        AUDIT_DB["players"][matched_key]["pending_drops"][oid]["quantity"] += oitem.get("quantity", 0)
            
            p_record = AUDIT_DB["players"][matched_key]
            p_record["name"] = pname
            p_record["is_me"] = f["is_me"]
            p_record["last_seen"] = now_full
            p_record["combats_count"] += 1
            if f["char_id"] and not p_record.get("char_id"):
                p_record["char_id"] = f["char_id"]
            
            # Acumular botin en pending_drops
            f_web_drops = []
            for item_id, qty in f["drops"].items():
                info = get_item_info(item_id)
                iid_str = str(item_id)
                item_icon = info.get("iconUrl") or f"https://api.dofusdb.fr/img/items/{item_id}.png"
                
                if iid_str not in p_record["pending_drops"]:
                    p_record["pending_drops"][iid_str] = {
                        "itemId": item_id,
                        "name": info["name"],
                        "level": info.get("level", 1),
                        "iconUrl": item_icon,
                        "quantity": 0
                    }
                else:
                    if not p_record["pending_drops"][iid_str].get("iconUrl"):
                        p_record["pending_drops"][iid_str]["iconUrl"] = item_icon
                p_record["pending_drops"][iid_str]["quantity"] += qty
                
                f_web_drops.append({
                    "itemId": item_id,
                    "name": info["name"],
                    "iconUrl": item_icon,
                    "quantity": qty
                })
            
            combat_summary_for_web.append({
                "name": pname,
                "is_me": f["is_me"],
                "drops": f_web_drops
            })
            
        AUDIT_DB["last_combat"] = {
            "timestamp": now_full,
            "timeStr": now_str,
            "fighters": combat_summary_for_web
        }
        
    save_audit_db()
    notify_sse_clients()

    # Guardar ráfaga cruda para depuración
    try:
        with open(LAST_COMBAT_FILE, "w", encoding="utf-8") as f:
            json.dump(packets_captured, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Imprimir en consola de forma limpia (SIN EMOJIS, SIN XP, SIN KAMAS)
    is_printing_summary = True
    try:
        print("\n" + "-" * 70)
        print(f"COMBATE FINALIZADO [{now_str}]")
        print("-" * 70)
        
        for idx, f in enumerate(processed_fighters, 1):
            tag = f"{f['name']} (Tu personaje)" if f["is_me"] else f["name"]
            print(f"[{idx}] {tag}")
            if f["drops"]:
                for item_id, qty in f["drops"].items():
                    info = get_item_info(item_id)
                    print(f"    - {info['name']} x{qty} (ID {item_id})")
            else:
                print("    - Sin botin en este combate")
                
        print("-" * 70)
        print(f"[i] Botin acumulado guardado en {AUDIT_DB_FILE}")
        print(f"[i] Consulta y reinicia entregas en: http://localhost:{HTTP_PORT}")
        print("-" * 70 + "\n")
    finally:
        is_printing_summary = False

# ==============================================================================
# SNIFFER DE RED (TCP 5555)
# ==============================================================================

def check_combat_timeout():
    global is_in_combat_burst, capture_buffer
    while True:
        time.sleep(0.3)
        if is_in_combat_burst and (time.time() - last_packet_time) >= 1.5:
            is_in_combat_burst = False
            packets_to_process = list(capture_buffer)
            capture_buffer = []
            threading.Thread(target=process_combat_and_update_db, args=(packets_to_process,), daemon=True).start()

def packet_callback(pkt):
    global is_in_combat_burst, last_packet_time, capture_buffer, last_trailing_packet_data
    
    if not pkt.haslayer(Raw) or not pkt.haslayer(TCP):
        return
        
    payload = bytes(pkt[Raw].load)
    if not payload:
        return

    now_str = datetime.now().strftime("%H:%M:%S")

    # Si detectamos kuf o jyg (incluso a través de la frontera de paquetes segmentados)
    boundary_check = last_trailing_packet_data + payload[:40]
    has_combat_sig = (b"kuf" in payload or b"jyg" in payload or b"kuf" in boundary_check or b"jyg" in boundary_check)
    last_trailing_packet_data = payload[-40:]

    if has_combat_sig:
        if not is_in_combat_burst:
            is_in_combat_burst = True
            capture_buffer = []
        last_packet_time = time.time()

    if is_in_combat_burst:
        last_packet_time = time.time()
        capture_buffer.append({
            "time": now_str,
            "bytes": len(payload),
            "raw_hex": payload.hex()
        })

    # Registro silencioso de personajes
    try:
        rt_pairs, _ = extract_all_player_names_and_ids(payload)
        for r_cid, r_name in rt_pairs.items():
            if r_cid not in KNOWN_CHARACTERS:
                save_known_player(r_cid, r_name)
    except Exception:
        pass

def start_sniffer():
    if sniff is None:
        print("\n[!] Scapy no esta instalado en este entorno de Python.")
        print("    Para capturar paquetes ejecuta: pip install scapy")
        print("    (En Windows requiere tener instalado Npcap: https://npcap.com)\n")
        print(f"[i] Sin embargo, el servidor web local sigue funcionando en http://localhost:{HTTP_PORT}")
        return

    timeout_thread = threading.Thread(target=check_combat_timeout, daemon=True)
    timeout_thread.start()
    
    filter_expr = f"tcp and (port {DOFUS_PORT})"
    try:
        sniff(filter=filter_expr, prn=packet_callback, store=0)
    except PermissionError:
        print("\n[ERROR] Se requieren permisos de Administrador / root para capturar paquetes de red.")
        print("        En Windows: abre la consola de comandos como Administrador.")
        print("        En Linux/Mac: ejecuta con 'sudo python dofus_auditor.py'\n")
    except Exception as e:
        print(f"\n[ERROR] Fallo al iniciar el sniffer de red: {e}\n")

# ==============================================================================
# SERVIDOR WEB LOCAL (HTML/CSS/JS INTEGRADO)
# ==============================================================================

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Auditor de Botín - Dofus Unity</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f293d;
      --text: #f8fafc;
      --text-muted: #64748b;
      --accent: #0ea5e9;
      --accent-hover: #0284c7;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --success: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 16px 20px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 12px;
      margin-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 700;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
    }
    .badge-status {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: var(--success);
    }
    .badge-port {
      background: rgba(14, 165, 233, 0.12);
      border: 1px solid rgba(14, 165, 233, 0.35);
      color: var(--accent);
      margin-left: 6px;
    }
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 12px;
      margin-bottom: 14px;
    }
    .char-setting {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
    }
    .char-input {
      background: #060911;
      border: 1px solid var(--border);
      color: #fff;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 12px;
      width: 160px;
      outline: none;
    }
    .char-input:focus { border-color: var(--accent); }
    .btn {
      padding: 5px 12px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-primary:hover { background: var(--accent-hover); }
    .btn-danger {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
    }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }
    .btn-reset {
      width: 100%;
      background: #ef4444;
      color: #fff;
      padding: 7px;
      margin-top: 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .btn-reset:hover { background: var(--danger-hover); }
    .btn-reset:disabled { opacity: 0.35; cursor: not-allowed; }
    .tabs { display: flex; gap: 4px; }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 5px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
    }
    .tab-btn.active {
      background: #1e293b;
      color: #fff;
      border-color: var(--border);
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 12px;
    }
    .player-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
    }
    .player-card.is-me {
      border-color: rgba(14, 165, 233, 0.5);
      background: #0d1525;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .player-name {
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .tag-me {
      font-size: 10px;
      font-weight: 700;
      background: #0284c7;
      color: #fff;
      padding: 1px 6px;
      border-radius: 4px;
    }
    .btn-tag {
      background: #1e293b;
      border: 1px solid var(--border);
      color: var(--text-muted);
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
      cursor: pointer;
    }
    .btn-tag:hover { color: #fff; border-color: var(--accent); }
    .pending-units {
      font-size: 13px;
      font-weight: 700;
      color: #38bdf8;
    }
    .items-box {
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex: 1;
    }
    .item-chip {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 8px;
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 6px;
    }
    .item-img {
      width: 28px;
      height: 28px;
      object-fit: contain;
      border-radius: 4px;
      background: #070b14;
      border: 1px solid #1e293b;
      flex-shrink: 0;
    }
    .item-name {
      font-size: 12px;
      font-weight: 500;
      color: #e2e8f0;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item-qty {
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 1px 6px;
      border-radius: 5px;
      flex-shrink: 0;
    }
    .empty-state {
      text-align: center;
      padding: 40px 16px;
      color: var(--text-muted);
      background: var(--card-bg);
      border: 1px dashed var(--border);
      border-radius: 8px;
      font-size: 13px;
    }
    .table-view {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .table-view th {
      text-align: left;
      padding: 8px 10px;
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--border);
    }
    .table-view td {
      padding: 8px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <span>Auditor de Botín</span>
        <span class="badge badge-port">TCP 5555</span>
      </div>
      <div class="badge badge-status" id="connStatus">
        &bull; Sniffer Activo
      </div>
    </header>

    <div class="top-bar">
      <div class="char-setting">
        <span>Mi Personaje:</span>
        <input type="text" id="myCharInput" class="char-input" placeholder="Nombre..." onkeydown="if(event.key==='Enter') saveMyCharacterName()">
        <button class="btn btn-primary" onclick="saveMyCharacterName()">Guardar</button>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <div class="tabs">
          <button class="tab-btn active" onclick="showTab('audit', this)">Jugadores</button>
          <button class="tab-btn" onclick="showTab('last', this)">Último Combate</button>
          <button class="tab-btn" onclick="showTab('history', this)">Historial</button>
        </div>
        <button class="btn btn-danger" onclick="resetAll()">Resetear Todo a 0</button>
      </div>
    </div>

    <!-- TAB 1: AUDITORIA -->
    <div id="tab-audit" class="tab-content active">
      <div id="playersGrid" class="grid">
        <div class="empty-state" style="grid-column: 1 / -1;">
          Esperando actividad de combate en Dofus...
        </div>
      </div>
    </div>

    <!-- TAB 2: ULTIMO COMBATE -->
    <div id="tab-last" class="tab-content">
      <div id="lastCombatContent" class="player-card">
        <p style="color: var(--text-muted); font-size: 13px;">Sin datos de combate reciente.</p>
      </div>
    </div>

    <!-- TAB 3: HISTORIAL -->
    <div id="tab-history" class="tab-content">
      <div class="player-card" id="historyList">
        <p style="color: var(--text-muted); font-size: 13px;">Sin liquidaciones registradas.</p>
      </div>
    </div>
  </div>

  <script>
    function showTab(name, btn) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      if (btn) btn.classList.add('active');
      const target = document.getElementById('tab-' + name);
      if (target) target.classList.add('active');
    }

    function getItemIcon(item) {
      if (item.iconUrl) return item.iconUrl;
      const id = item.itemId || item.id;
      return 'https://api.dofusdb.fr/img/items/' + id + '.png';
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        const myName = (data.config && data.config.my_character_name) ? data.config.my_character_name : '';
        const charInput = document.getElementById('myCharInput');
        if (charInput && !charInput.value && myName) {
          charInput.value = myName;
        }
        renderAudit(data.players || {}, myName);
        renderLastCombat(data.last_combat);
        renderHistory(data.settlements || []);
      } catch (e) {
        console.error("Error al obtener estado:", e);
      }
    }

    async function saveMyCharacterName(overrideName) {
      const charInput = document.getElementById('myCharInput');
      const val = overrideName !== undefined ? overrideName : (charInput ? charInput.value.trim() : '');
      try {
        await fetch('/api/config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ my_character_name: val })
        });
        if (charInput && overrideName !== undefined) {
          charInput.value = overrideName;
        }
        fetchStatus();
      } catch (e) {
        console.error("Error al guardar personaje:", e);
      }
    }

    function renderAudit(players, myName) {
      const grid = document.getElementById('playersGrid');
      const keys = Object.keys(players);
      if (keys.length === 0) {
        grid.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1;">Esperando actividad de combate en Dofus...</div>';
        return;
      }

      let html = '';
      keys.forEach(k => {
        const p = players[k];
        const drops = Object.values(p.pending_drops || {});
        const totalItems = drops.reduce((sum, d) => sum + (d.quantity || 0), 0);
        const isMe = p.is_me;
        const meBadge = isMe 
          ? '<span class="tag-me">Tú</span>'
          : `<button onclick="saveMyCharacterName('${p.name}')" class="btn-tag">Marcar como yo</button>`;

        html += `
          <div class="player-card ${isMe ? 'is-me' : ''}">
            <div class="card-header">
              <div class="player-name">${p.name} ${meBadge}</div>
              <div class="pending-units">${totalItems} uds</div>
            </div>

            <div class="items-box">
              ${drops.length > 0 ? drops.map(d => `
                <div class="item-chip">
                  <img src="${getItemIcon(d)}" alt="" class="item-img" onerror="this.onerror=null;this.src='https://api.dofusdb.fr/img/items/' + ${d.itemId} + '.png';" />
                  <span class="item-name" title="${d.name}">${d.name}</span>
                  <span class="item-qty">x${d.quantity}</span>
                </div>
              `).join('') : '<p style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 12px 0;">0 recursos pendientes</p>'}
            </div>

            <button class="btn btn-reset" onclick="resetPlayer('${k}', '${p.name}')" ${totalItems === 0 ? 'disabled' : ''}>
              Liquidado &bull; Reiniciar a 0
            </button>
          </div>
        `;
      });
      grid.innerHTML = html;
    }

    function renderLastCombat(combat) {
      const container = document.getElementById('lastCombatContent');
      if (!combat || !combat.fighters || combat.fighters.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">Sin datos de combate reciente.</p>';
        return;
      }
      let html = `<div style="font-weight: 700; font-size: 13px; margin-bottom: 10px; color: var(--accent);">Combate a las ${combat.timeStr}</div>`;
      combat.fighters.forEach(f => {
        html += `
          <div style="margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.2); border-radius: 6px;">
            <div style="font-weight: 600; font-size: 13px; margin-bottom: 4px;">
              ${f.name} ${f.is_me ? '<span class="tag-me">Tú</span>' : ''}
            </div>
            <div style="display: flex; flex-direction: column; gap: 4px;">
              ${(f.drops && f.drops.length > 0) ? f.drops.map(d => `
                <div class="item-chip" style="padding: 3px 6px;">
                  <img src="${getItemIcon(d)}" alt="" class="item-img" style="width: 22px; height: 22px;" onerror="this.onerror=null;this.src='https://api.dofusdb.fr/img/items/' + ${d.itemId} + '.png';" />
                  <span class="item-name">${d.name}</span>
                  <span class="item-qty">x${d.quantity}</span>
                </div>
              `).join('') : '<span style="color: var(--text-muted); font-size: 11px;">Sin botín</span>'}
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
    }

    function renderHistory(settlements) {
      const container = document.getElementById('historyList');
      if (!settlements || settlements.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">Sin liquidaciones registradas.</p>';
        return;
      }
      container.innerHTML = `
        <table class="table-view">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Jugador</th>
              <th style="text-align: right;">Total</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            ${settlements.slice().reverse().map(s => `
              <tr>
                <td style="color: var(--text-muted); font-mono; font-size: 11px;">${s.date}</td>
                <td style="font-weight: 600;">${s.playerName}</td>
                <td style="text-align: right; font-weight: 700; color: #38bdf8;">${s.totalUnits} uds</td>
                <td style="color: #cbd5e1;">${s.summary}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    async function resetPlayer(key, name) {
      if (!confirm(`¿Confirmas liquidar y reiniciar los recursos de ${name}?`)) return;
      try {
        const res = await fetch('/api/reset', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ key: key })
        });
        if (res.ok) fetchStatus();
      } catch (e) {
        alert("Error: " + e);
      }
    }

    async function resetAll() {
      if (!confirm("¿Reiniciar los recursos de TODOS los jugadores a 0?")) return;
      try {
        const res = await fetch('/api/reset', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ all: true })
        });
        if (res.ok) fetchStatus();
      } catch (e) {
        alert("Error: " + e);
      }
    }

    fetchStatus();
    setInterval(fetchStatus, 3000);

    const evtSource = new EventSource('/api/events');
    evtSource.onmessage = function() { fetchStatus(); };
    evtSource.onerror = function() {
      const statusEl = document.getElementById('connStatus');
      if (statusEl) {
        statusEl.innerHTML = '&bull; Reconectando...';
        statusEl.style.color = 'var(--text-muted)';
      }
    };
    evtSource.onopen = function() {
      const statusEl = document.getElementById('connStatus');
      if (statusEl) {
        statusEl.innerHTML = '&bull; Sniffer Activo';
        statusEl.style.color = 'var(--success)';
      }
    };
  </script>
</body>
</html>"""

class AuditServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silenciar logs HTTP en consola para no interferir con la salida limpia
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            with db_lock:
                data = json.dumps(AUDIT_DB)
            self.wfile.write(data.encode("utf-8"))
        elif self.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            sse_clients.append(self)
            try:
                while True:
                    time.sleep(1)
            except Exception:
                pass
            finally:
                if self in sse_clients:
                    sse_clients.remove(self)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/reset":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                params = json.loads(body.decode("utf-8"))
            except Exception:
                params = {}

            now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with db_lock:
                if params.get("all"):
                    # Resetear todos
                    for pkey, p in AUDIT_DB["players"].items():
                        drops = p.get("pending_drops", {})
                        if drops:
                            items_summary = ", ".join([f"{d['name']} x{d['quantity']}" for d in drops.values()])
                            total_u = sum(d["quantity"] for d in drops.values())
                            AUDIT_DB["settlements"].append({
                                "date": now_full,
                                "playerName": p["name"],
                                "totalUnits": total_u,
                                "summary": items_summary
                            })
                            p["pending_drops"] = {}
                else:
                    pkey = params.get("key")
                    if pkey and pkey in AUDIT_DB["players"]:
                        p = AUDIT_DB["players"][pkey]
                        drops = p.get("pending_drops", {})
                        if drops:
                            items_summary = ", ".join([f"{d['name']} x{d['quantity']}" for d in drops.values()])
                            total_u = sum(d["quantity"] for d in drops.values())
                            AUDIT_DB["settlements"].append({
                                "date": now_full,
                                "playerName": p["name"],
                                "totalUnits": total_u,
                                "summary": items_summary
                            })
                            p["pending_drops"] = {}

            save_audit_db()
            notify_sse_clients()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success": true}')
        elif self.path == "/api/config":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                params = json.loads(body.decode("utf-8"))
            except Exception:
                params = {}
            new_name = str(params.get("my_character_name", "")).strip()

            with db_lock:
                if "config" not in AUDIT_DB:
                    AUDIT_DB["config"] = {}
                AUDIT_DB["config"]["my_character_name"] = new_name
                global MY_CHARACTER_NAME
                MY_CHARACTER_NAME = new_name
                for p in AUDIT_DB.get("players", {}).values():
                    if new_name:
                        p["is_me"] = (p.get("name", "").strip().lower() == new_name.lower())
                    else:
                        p["is_me"] = False

            save_audit_db()
            notify_sse_clients()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success": true}')
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server():
    server_address = ("0.0.0.0", HTTP_PORT)
    try:
        httpd = ThreadingHTTPServer(server_address, AuditServerHandler)
        httpd.serve_forever()
    except Exception as e:
        print(f"[!] Error al levantar servidor HTTP en puerto {HTTP_PORT}: {e}")

# ==============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditor de Botin Dofus Unity")
    parser.add_argument("-n", "--nombre", dest="my_name", help="Nombre de tu personaje principal", default=None)
    args, _ = parser.parse_known_args()
    if args.my_name:
        MY_CHARACTER_NAME = args.my_name.strip()
        if "config" not in AUDIT_DB:
            AUDIT_DB["config"] = {}
        AUDIT_DB["config"]["my_character_name"] = MY_CHARACTER_NAME
        for p in AUDIT_DB.get("players", {}).values():
            p["is_me"] = (p.get("name", "").strip().lower() == MY_CHARACTER_NAME.lower())
        save_audit_db()

    active_name = AUDIT_DB.get("config", {}).get("my_character_name") or MY_CHARACTER_NAME

    print("=" * 70)
    print("AUDITOR DE BOTIN DOFUS UNITY - SERVIDOR LOCAL")
    print("=" * 70)
    print(f"[+] Personaje configurado        : {active_name if active_name else '(Auto-detectar o configurar en http://localhost:5000)'}")
    print(f"[+] Interfaz web local activa en : http://localhost:{HTTP_PORT}")
    print(f"[+] Escuchando trafico Dofus (TCP {DOFUS_PORT})...")
    print(f"[+] Base de datos de auditoria   : {AUDIT_DB_FILE}")
    print(f"[+] Catalogo local de objetos    : {ITEMS_DB_FILE}")
    print(f"[+] Memoria de jugadores         : {PLAYERS_CACHE_FILE}")
    print("=" * 70)
    print("(Esperando combates... La consola se mantendra en silencio)\n")

    # Iniciar servidor HTTP en segundo plano
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Intentar abrir el navegador automáticamente
    try:
        webbrowser.open_new_tab(f"http://localhost:{HTTP_PORT}")
    except Exception:
        pass

    # Iniciar sniffer en hilo principal
    start_sniffer()
