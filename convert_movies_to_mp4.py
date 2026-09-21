#!/usr/bin/env python3
"""
TapBox - Conversor Automático de Películas y Videos a MP4 Web-Optimized
----------------------------------------------------------------------
Convierte archivos MKV / AVI / HEVC a MP4 H.264 + AAC compatible 100% con navegadores web
- Si el video ya es H.264, realiza un Remux directo (sin recodificar video, 100% calidad, ultra rápido).
- Si el video es HEVC/x265/XviD, codifica a H.264 de alta calidad (CRF 20) con faststart.
- Actualiza catalog.json automáticamente con la nueva ruta .mp4.
"""

import os
import sys
import json
import time
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..')) if os.path.basename(BASE_DIR) == 'scripts' else BASE_DIR
CATALOG_PATH = os.path.join(PROJECT_ROOT, 'catalog.json')
STATUS_PATH = os.path.join(PROJECT_ROOT, 'conversion_status.json')

CONVERSION_STATE = {
    "is_running": False,
    "current_file": None,
    "current_title": None,
    "current_mode": None,
    "v_codec": None,
    "a_codec": None,
    "total_files": 0,
    "completed_files": 0,
    "current_index": 0,
    "percent_total": 0,
    "start_time": 0,
    "last_update": 0,
    "completed_list": [],
    "recent_logs": []
}

def update_status_file(extra_log=None):
    if extra_log:
        CONVERSION_STATE["recent_logs"].append(f"[{time.strftime('%H:%M:%S')}] {extra_log}")
        if len(CONVERSION_STATE["recent_logs"]) > 50:
            CONVERSION_STATE["recent_logs"] = CONVERSION_STATE["recent_logs"][-50:]
    CONVERSION_STATE["last_update"] = time.time()
    if CONVERSION_STATE["total_files"] > 0:
        CONVERSION_STATE["percent_total"] = round((CONVERSION_STATE["completed_files"] / CONVERSION_STATE["total_files"]) * 100, 1)
    try:
        with open(STATUS_PATH, 'w', encoding='utf-8') as f:
            json.dump(CONVERSION_STATE, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass

def load_catalog():
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_catalog(data):
    with open(CATALOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def probe_video(file_path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", file_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None
    data = json.loads(res.stdout)
    v_codec = None
    a_codec = None
    duration = 0.0
    for st in data.get('streams', []):
        if st.get('codec_type') == 'video' and not v_codec:
            v_codec = st.get('codec_name', '').lower()
        elif st.get('codec_type') == 'audio' and not a_codec:
            a_codec = st.get('codec_name', '').lower()
    try:
        duration = float(data.get('format', {}).get('duration', 0))
    except Exception:
        pass
    return {'v_codec': v_codec, 'a_codec': a_codec, 'duration': duration}

def convert_single_video(input_path, delete_original=True):
    if not os.path.exists(input_path):
        msg = f"[ERROR] Archivo no existe: {input_path}"
        print(msg, flush=True)
        update_status_file(msg)
        return None

    info = probe_video(input_path)
    if not info:
        msg = f"[ERROR] No se pudo analizar {input_path}"
        print(msg, flush=True)
        update_status_file(msg)
        return None

    v_codec = info['v_codec']
    a_codec = info['a_codec']
    ext = os.path.splitext(input_path)[1].lower()

    # Si ya es MP4 con H264 y AAC, no necesita conversión
    if ext == '.mp4' and v_codec in ['h264', 'avc1'] and a_codec in ['aac', 'mp3']:
        msg = f"[INFO] Ya está optimizado para web: {os.path.basename(input_path)}"
        print(msg, flush=True)
        update_status_file(msg)
        return input_path

    out_path = os.path.splitext(input_path)[0] + "_web.mp4"
    if out_path == input_path:
        out_path = os.path.splitext(input_path)[0] + "_optimized.mp4"

    video_copy = (v_codec in ['h264', 'avc1'])
    mode_str = "REMUX DIRECTO (Copia sin pérdida)" if video_copy else "RECODIFICACIÓN H.264"

    fname = os.path.basename(input_path)
    parent_dir = os.path.basename(os.path.dirname(input_path))
    clean_title = parent_dir if parent_dir != 'movies' else fname

    CONVERSION_STATE["current_file"] = fname
    CONVERSION_STATE["current_title"] = clean_title
    CONVERSION_STATE["current_mode"] = mode_str
    CONVERSION_STATE["v_codec"] = v_codec
    CONVERSION_STATE["a_codec"] = a_codec
    update_status_file(f"🎬 Iniciando conversión de '{clean_title}' [{mode_str}]")

    print(f"\n=======================================================", flush=True)
    print(f"🎬 Procesando: {fname}", flush=True)
    print(f"📦 Códecs originales: Video={v_codec}, Audio={a_codec}", flush=True)
    print(f"⚡ Modo: {mode_str}", flush=True)
    print(f"🎯 Destino: {os.path.basename(out_path)}", flush=True)
    print(f"=======================================================", flush=True)

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if video_copy:
        cmd.extend(["-c:v", "copy"])
    else:
        # Codificación H.264 de alta calidad y buen rendimiento para almacenamiento
        cmd.extend(["-c:v", "libx264", "-preset", "faster", "-crf", "20", "-pix_fmt", "yuv420p"])

    cmd.extend(["-c:a", "aac", "-b:a", "256k", "-ac", "2", "-movflags", "+faststart", out_path])

    start_t = time.time()
    res = subprocess.run(cmd)
    elapsed = round(time.time() - start_t, 1)

    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        final_mp4_path = os.path.splitext(input_path)[0] + ".mp4"
        if delete_original and input_path != final_mp4_path:
            try:
                os.remove(input_path)
                print(f"🗑️ Archivo original eliminado: {fname}", flush=True)
            except Exception as e:
                print(f"Advertencia eliminando original: {e}", flush=True)

        if out_path != final_mp4_path:
            os.replace(out_path, final_mp4_path)
            out_path = final_mp4_path

        # Actualizar catalog.json
        catalog = load_catalog()
        updated = False
        rel_in = input_path.replace('/data/media/', '').replace('\\', '/')
        rel_out = out_path.replace('/data/media/', '').replace('\\', '/')
        
        for item in catalog:
            item_f = str(item.get('file', '')).replace('\\', '/')
            if item_f == rel_in or os.path.basename(item_f) == fname:
                item['file'] = rel_out
                updated = True
                print(f"📝 Catálogo actualizado para obra: {item.get('title')}", flush=True)

        if updated:
            save_catalog(catalog)

        CONVERSION_STATE["completed_files"] += 1
        CONVERSION_STATE["completed_list"].append({
            "title": clean_title,
            "file": os.path.basename(out_path),
            "elapsed_s": elapsed,
            "mode": "Remux" if video_copy else "Transcode"
        })
        msg = f"✅ Completado '{clean_title}' en {elapsed}s"
        print(msg, flush=True)
        update_status_file(msg)
        return out_path
    else:
        msg = f"❌ Error durante la conversión de {input_path}"
        print(msg, flush=True)
        update_status_file(msg)
        if os.path.exists(out_path):
            try: os.remove(out_path)
            except Exception: pass
        return None

def convert_all_movies(media_root="/data/media/movies"):
    print(f"🔍 Escaneando carpeta de películas: {media_root}", flush=True)
    video_files = []
    for root, _, files in os.walk(media_root):
        for f in files:
            if f.lower().endswith(('.mkv', '.avi', '.mp4', '.m4v', '.webm')):
                video_files.append(os.path.join(root, f))

    CONVERSION_STATE["is_running"] = True
    CONVERSION_STATE["total_files"] = len(video_files)
    CONVERSION_STATE["start_time"] = time.time()
    update_status_file(f"🚀 Iniciando optimización masiva de {len(video_files)} películas")

    print(f"Total videos encontrados: {len(video_files)}", flush=True)

    # 1. Procesar primero los que solo requieren Remux
    print("\n--- FASE 1: Remux Ultra Rápido de videos H.264 ---", flush=True)
    update_status_file("Iniciando FASE 1: Remux ultra rápido de videos H.264")
    remaining = []
    for vp in video_files:
        info = probe_video(vp)
        if info and info.get('v_codec') in ['h264', 'avc1'] and (vp.endswith('.mkv') or info.get('a_codec') not in ['aac', 'mp3']):
            CONVERSION_STATE["current_index"] += 1
            convert_single_video(vp)
        else:
            remaining.append(vp)

    # 2. Procesar los que requieren recodificación
    print(f"\n--- FASE 2: Recodificación de videos HEVC/XviD ({len(remaining)} restantes) ---", flush=True)
    update_status_file(f"Iniciando FASE 2: Recodificación de {len(remaining)} películas HEVC/XviD")
    for vp in remaining:
        info = probe_video(vp)
        if info and (info.get('v_codec') not in ['h264', 'avc1'] or not vp.endswith('.mp4')):
            CONVERSION_STATE["current_index"] += 1
            convert_single_video(vp)

    CONVERSION_STATE["is_running"] = False
    CONVERSION_STATE["current_file"] = None
    CONVERSION_STATE["current_title"] = None
    CONVERSION_STATE["current_mode"] = None
    update_status_file("🎉 ¡Proceso de optimización masiva completado exitosamente!")
    print(f"\n🎉 ¡Proceso finalizado! Total videos optimizados: {CONVERSION_STATE['completed_files']}", flush=True)

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "/data/media/movies"
    if os.path.isfile(target):
        CONVERSION_STATE["is_running"] = True
        CONVERSION_STATE["total_files"] = 1
        CONVERSION_STATE["start_time"] = time.time()
        convert_single_video(target)
        CONVERSION_STATE["is_running"] = False
        update_status_file("Proceso individual finalizado")
    else:
        convert_all_movies(target)

