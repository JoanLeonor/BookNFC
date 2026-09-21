import os
import re
import json
import math
import time
import uuid
import tempfile
import shutil
import random
import string
import glob
import subprocess
import urllib.request
import zipfile
import struct
import base64
import io
import mimetypes
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, jsonify, Response, stream_with_context

# Registro explícito de tipos MIME de audio modernos
mimetypes.add_type('audio/ogg', '.opus')
mimetypes.add_type('audio/opus', '.opus')
mimetypes.add_type('audio/ogg', '.ogg')
mimetypes.add_type('audio/flac', '.flac')
mimetypes.add_type('audio/mp4', '.m4a')
mimetypes.add_type('audio/aac', '.aac')

app = Flask(__name__)
app.secret_key = 'booknfc_secret_key_musi_card'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Rutas de almacenamiento
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
COVER_FOLDER = os.path.join(BASE_DIR, 'static/covers')
CACHE_FOLDER = os.path.join(BASE_DIR, 'static/cache')
DB_FILE = os.path.join(BASE_DIR, 'catalog.json')
OLD_DB_FILE = os.path.join(BASE_DIR, 'books.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['COVER_FOLDER'] = COVER_FOLDER
app.config['CACHE_FOLDER'] = CACHE_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVER_FOLDER, exist_ok=True)
os.makedirs(CACHE_FOLDER, exist_ok=True)

# ----------------- FUNCIONES AUXILIARES -----------------

def get_media_root():
    config = load_config()
    cfg_root = config.get('media_root')
    if cfg_root and os.path.exists(cfg_root):
        return os.path.abspath(cfg_root)
    # Ruta estándar en servidor Linux / Docker (/data/media)
    if os.path.exists('/data/media'):
        return '/data/media'
    # Carpeta por defecto en el entorno local de TapBox (data/media)
    default_local = os.path.join(BASE_DIR, 'data', 'media')
    os.makedirs(os.path.join(default_local, 'movies'), exist_ok=True)
    os.makedirs(os.path.join(default_local, 'series'), exist_ok=True)
    return default_local

VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.MP4', '.MKV', '.AVI', '.MOV', '.WEBM', '.M4V')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')
AUDIO_EXTS = ('.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.alac', '.aiff',
              '.MP3', '.FLAC', '.WAV', '.OGG', '.OPUS', '.M4A', '.AAC', '.WMA', '.ALAC', '.AIFF')

def extract_audio_embedded_metadata(file_source):
    """
    Extrae etiquetas de metadatos (TITLE, ARTIST, ALBUM, GENRE) y portada incrustada
    de archivos Opus, OGG, FLAC, MP3 y M4A/AAC sin dependencias externas.
    Retorna: (tags: dict, pic_bytes: bytes|None, pic_mime: str)
    """
    tags = {}
    pic_bytes = None
    pic_mime = 'image/jpeg'

    data = None
    if isinstance(file_source, str):
        if not os.path.exists(file_source):
            return tags, pic_bytes, pic_mime
        try:
            with open(file_source, 'rb') as f:
                data = f.read(5 * 1024 * 1024) # Leer primeros 5MB (suficiente para portadas y tags)
        except Exception:
            return tags, pic_bytes, pic_mime
    elif hasattr(file_source, 'read'):
        try:
            cur_pos = file_source.tell() if hasattr(file_source, 'tell') else 0
            data = file_source.read(5 * 1024 * 1024)
            if hasattr(file_source, 'seek'):
                file_source.seek(cur_pos)
        except Exception:
            return tags, pic_bytes, pic_mime
    elif isinstance(file_source, (bytes, bytearray)):
        data = file_source
    else:
        return tags, pic_bytes, pic_mime

    if not data or len(data) < 16:
        return tags, pic_bytes, pic_mime

    # 1. CONTENEDOR OGG / OPUS / VORBIS
    if data.startswith(b'OggS'):
        pos = 0
        packets = []
        cur_pkt = bytearray()
        while pos < len(data) - 27:
            if data[pos:pos+4] != b'OggS':
                next_pos = data.find(b'OggS', pos + 1)
                if next_pos == -1:
                    break
                pos = next_pos
                continue
            num_segs = data[pos + 26]
            if pos + 27 + num_segs > len(data):
                break
            seg_tbl = data[pos + 27 : pos + 27 + num_segs]
            payload_pos = pos + 27 + num_segs
            payload_len = sum(seg_tbl)
            if payload_pos + payload_len > len(data):
                break
            payload = data[payload_pos : payload_pos + payload_len]
            seg_off = 0
            for slen in seg_tbl:
                cur_pkt.extend(payload[seg_off : seg_off + slen])
                seg_off += slen
                if slen < 255:
                    packets.append(bytes(cur_pkt))
                    cur_pkt = bytearray()
            pos = payload_pos + payload_len
            if len(packets) >= 8:
                break

        for pkt in packets:
            header_len = 0
            if pkt.startswith(b'OpusTags'):
                header_len = 8
            elif pkt.startswith(b'\x03vorbis'):
                header_len = 7
            else:
                continue
            try:
                off = header_len
                v_len = struct.unpack('<I', pkt[off:off+4])[0]
                off += 4 + v_len
                c_cnt = struct.unpack('<I', pkt[off:off+4])[0]
                off += 4
                for _ in range(c_cnt):
                    if off + 4 > len(pkt):
                        break
                    c_len = struct.unpack('<I', pkt[off:off+4])[0]
                    off += 4
                    if off + c_len > len(pkt):
                        break
                    c_bytes = pkt[off:off+c_len]
                    off += c_len
                    try:
                        c_str = c_bytes.decode('utf-8', errors='ignore')
                        if '=' in c_str:
                            k, v = c_str.split('=', 1)
                            k = k.strip().upper()
                            tags[k] = v.strip()
                            if k == 'METADATA_BLOCK_PICTURE' and not pic_bytes:
                                try:
                                    raw_b = base64.b64decode(v.strip())
                                    m_len = struct.unpack('>I', raw_b[4:8])[0]
                                    pic_mime = raw_b[8:8+m_len].decode('utf-8', errors='ignore') or 'image/jpeg'
                                    d_len = struct.unpack('>I', raw_b[8+m_len:12+m_len])[0]
                                    p_off = 12 + m_len + d_len + 16
                                    p_len = struct.unpack('>I', raw_b[p_off:p_off+4])[0]
                                    p_off += 4
                                    pic_bytes = raw_b[p_off:p_off+p_len]
                                except Exception:
                                    pass
                            elif k in ('COVERART', 'COVER') and not pic_bytes:
                                try:
                                    pic_bytes = base64.b64decode(v.strip())
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

    # 2. FORMATO FLAC
    elif data.startswith(b'fLaC'):
        pos = 4
        while pos < len(data) - 4:
            b_hdr = data[pos]
            is_last = (b_hdr & 0x80) != 0
            b_type = b_hdr & 0x7F
            b_len = struct.unpack('>I', b'\x00' + data[pos+1:pos+4])[0]
            pos += 4
            if pos + b_len > len(data):
                break
            b_data = data[pos:pos+b_len]
            pos += b_len
            if b_type == 6 and not pic_bytes: # PICTURE
                try:
                    m_len = struct.unpack('>I', b_data[4:8])[0]
                    pic_mime = b_data[8:8+m_len].decode('utf-8', errors='ignore') or 'image/jpeg'
                    d_len = struct.unpack('>I', b_data[8+m_len:12+m_len])[0]
                    p_off = 12 + m_len + d_len + 16
                    p_len = struct.unpack('>I', b_data[p_off:p_off+4])[0]
                    p_off += 4
                    pic_bytes = b_data[p_off:p_off+p_len]
                except Exception:
                    pass
            elif b_type == 4: # VORBIS_COMMENT
                try:
                    v_len = struct.unpack('<I', b_data[0:4])[0]
                    c_off = 4 + v_len
                    c_cnt = struct.unpack('<I', b_data[c_off:c_off+4])[0]
                    c_off += 4
                    for _ in range(c_cnt):
                        if c_off + 4 > len(b_data):
                            break
                        c_len = struct.unpack('<I', b_data[c_off:c_off+4])[0]
                        c_off += 4
                        c_str = b_data[c_off:c_off+c_len].decode('utf-8', errors='ignore')
                        c_off += c_len
                        if '=' in c_str:
                            k, v = c_str.split('=', 1)
                            tags[k.strip().upper()] = v.strip()
                except Exception:
                    pass
            if is_last:
                break

    # 3. ID3v2 (MP3, etc.)
    elif data.startswith(b'ID3'):
        try:
            ver = data[3]
            tag_size = ((data[6] & 0x7f) << 21) | ((data[7] & 0x7f) << 14) | ((data[8] & 0x7f) << 7) | (data[9] & 0x7f)
            pos = 10
            tag_end = min(len(data), 10 + tag_size)
            while pos < tag_end - 10:
                f_id = data[pos:pos+4].decode('latin1', errors='ignore')
                if not f_id.isalnum():
                    break
                f_size = struct.unpack('>I', data[pos+4:pos+8])[0]
                if ver == 4:
                    f_size = ((data[pos+4] & 0x7f) << 21) | ((data[pos+5] & 0x7f) << 14) | ((data[pos+6] & 0x7f) << 7) | (data[pos+7] & 0x7f)
                pos += 10
                if pos + f_size > len(data):
                    break
                f_data = data[pos:pos+f_size]
                pos += f_size
                if f_id == 'APIC' and not pic_bytes:
                    try:
                        mime_end = f_data.find(b'\x00', 1)
                        if mime_end != -1:
                            pic_mime = f_data[1:mime_end].decode('latin1', errors='ignore') or 'image/jpeg'
                            desc_end = f_data.find(b'\x00', mime_end + 2)
                            if desc_end != -1:
                                pic_bytes = f_data[desc_end+1:]
                            else:
                                pic_bytes = f_data[mime_end+2:]
                    except Exception:
                        pass
                elif f_id in ('TIT2', 'TPE1', 'TALB', 'TCON'):
                    try:
                        val = f_data[1:].decode('utf-8', errors='ignore').strip('\x00').strip()
                        if f_id == 'TIT2': tags['TITLE'] = val
                        elif f_id == 'TPE1': tags['ARTIST'] = val
                        elif f_id == 'TALB': tags['ALBUM'] = val
                        elif f_id == 'TCON': tags['GENRE'] = val
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. ESCANEO DIRECTO FALLBACK (METADATA_BLOCK_PICTURE en bloque plano)
    if not pic_bytes and b'METADATA_BLOCK_PICTURE=' in data:
        try:
            m = re.search(rb'METADATA_BLOCK_PICTURE=([A-Za-z0-9+/=]+)', data)
            if m:
                raw_b = base64.b64decode(m.group(1))
                m_len = struct.unpack('>I', raw_b[4:8])[0]
                pic_mime = raw_b[8:8+m_len].decode('utf-8', errors='ignore') or 'image/jpeg'
                d_len = struct.unpack('>I', raw_b[8+m_len:12+m_len])[0]
                p_off = 12 + m_len + d_len + 16
                p_len = struct.unpack('>I', raw_b[p_off:p_off+4])[0]
                p_off += 4
                pic_bytes = raw_b[p_off:p_off+p_len]
        except Exception:
            pass

    return tags, pic_bytes, pic_mime

def natural_sort_filename_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def clean_movie_title(raw_name):
    """Extrae título limpio y año de nombres como 'The Matrix (1999)' o 'Matrix.1999.1080p'"""
    name = os.path.splitext(raw_name)[0]
    name = name.replace('.', ' ').replace('_', ' ')
    match = re.search(r'^(.*?)(?:[\(\[\s]+(19\d\d|20\d\d)[\)\]\s]*)', name)
    if match:
        clean_title = match.group(1).strip()
        year = match.group(2).strip()
        if clean_title:
            return f"{clean_title} ({year})"
    return name.strip()

def find_poster_in_folder(folder_path):
    """Busca imágenes de portada en una carpeta dada (poster, cover, folder, etc.)"""
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return None
    try:
        files = os.listdir(folder_path)
        # 1. Prefer poster, cover, folder
        for pref in ['poster', 'cover', 'folder', 'default']:
            for f in files:
                if f.lower().startswith(pref) and f.endswith(IMAGE_EXTS):
                    return os.path.join(folder_path, f)
        # 2. Cualquier imagen
        for f in files:
            if f.endswith(IMAGE_EXTS):
                return os.path.join(folder_path, f)
    except Exception:
        pass
    return None

def get_radarr_movies():
    """Consulta la API de Radarr si está disponible"""
    config = load_config()
    radarr_url = config.get('radarr_url', 'http://127.0.0.1:7878').rstrip('/')
    radarr_api_key = config.get('radarr_api_key', '53ea9f5be1ca47da998fcfd8a2394288')
    try:
        req = urllib.request.Request(f"{radarr_url}/api/v3/movie?apiKey={radarr_api_key}", headers={'User-Agent': 'TapBox'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return []

def get_sonarr_series():
    """Consulta la API de Sonarr si está disponible"""
    config = load_config()
    sonarr_url = config.get('sonarr_url', 'http://127.0.0.1:8989').rstrip('/')
    sonarr_api_key = config.get('sonarr_api_key', 'dd73a8f684104a48b018d33b23e0fefa')
    try:
        req = urllib.request.Request(f"{sonarr_url}/api/v3/series?apiKey={sonarr_api_key}", headers={'User-Agent': 'TapBox'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return []

def download_image_to_file(image_url, dest_path):
    """Descarga una imagen de portada remota de forma segura"""
    try:
        req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            if len(content) > 500:
                with open(dest_path, 'wb') as f:
                    f.write(content)
                return True
    except Exception as e:
        print(f"Error descargando imagen desde {image_url}: {e}")
    return False

def find_radarr_match(folder_name, file_rel, radarr_movies):
    """Encuentra la película correspondiente en Radarr"""
    clean_search = clean_movie_title(folder_name or os.path.basename(file_rel)).lower()
    for m in radarr_movies:
        path = m.get('path', '')
        if path and (folder_name and folder_name.lower() in path.lower() or os.path.basename(path).lower() == folder_name.lower()):
            return m
        m_title = m.get('title', '').lower()
        if m_title and (m_title in clean_search or clean_search in m_title):
            return m
    return None

def find_sonarr_match(series_folder, sonarr_series_list):
    """Encuentra la serie correspondiente en Sonarr"""
    clean_search = clean_movie_title(series_folder).lower()
    for s in sonarr_series_list:
        path = s.get('path', '')
        if path and (series_folder and series_folder.lower() in path.lower() or os.path.basename(path).lower() == series_folder.lower()):
            return s
        s_title = s.get('title', '').lower()
        if s_title and (s_title in clean_search or clean_search in s_title):
            return s
    return None

def scan_media_library():
    media_root = get_media_root()
    movies_dir = os.path.join(media_root, 'movies')
    series_dir = os.path.join(media_root, 'series')
    os.makedirs(movies_dir, exist_ok=True)
    os.makedirs(series_dir, exist_ok=True)

    radarr_movies = get_radarr_movies()
    sonarr_series_list = get_sonarr_series()

    books = load_books()
    existing_files = set()
    existing_titles = set()
    for b in books:
        t = b.get('title', '').strip().lower()
        if t:
            existing_titles.add(t)
        f_val = b.get('file')
        if isinstance(f_val, list):
            for x in f_val:
                existing_files.add(str(x).replace('\\', '/'))
        elif f_val:
            existing_files.add(str(f_val).replace('\\', '/'))

    discovered_movies = []
    # Escaneo de películas
    if os.path.exists(movies_dir):
        for entry in sorted(os.listdir(movies_dir)):
            full_entry_path = os.path.join(movies_dir, entry)
            if os.path.isdir(full_entry_path):
                # Carpeta por película (ej. Matrix (1999)/Matrix.mp4)
                video_files = []
                for root, _, files in os.walk(full_entry_path):
                    for f in files:
                        if f.endswith(VIDEO_EXTS):
                            video_files.append(os.path.join(root, f))
                if video_files:
                    video_files.sort(key=os.path.getsize, reverse=True)
                    main_video = video_files[0]
                    rel_video = os.path.relpath(main_video, media_root).replace('\\', '/')
                    poster_path = find_poster_in_folder(full_entry_path)
                    rel_poster = os.path.relpath(poster_path, media_root).replace('\\', '/') if poster_path else None
                    title = clean_movie_title(entry)
                    already = (rel_video in existing_files) or (title.lower() in existing_titles)
                    
                    # Metadatos desde Radarr
                    rad_match = find_radarr_match(entry, rel_video, radarr_movies)
                    synopsis = rad_match.get('overview') if rad_match else None
                    poster_url = None
                    genres = ", ".join(rad_match.get('genres', [])) if rad_match and rad_match.get('genres') else 'Película'
                    author = rad_match.get('studio') if rad_match else ''
                    if rad_match:
                        for img in rad_match.get('images', []):
                            if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                                poster_url = img.get('remoteUrl')
                                break

                    discovered_movies.append({
                        'title': title,
                        'folder': entry,
                        'file': rel_video,
                        'cover_rel': rel_poster,
                        'poster_remote_url': poster_url,
                        'synopsis': synopsis or "Película de alta definición.",
                        'category': genres or "Película",
                        'author': author or "",
                        'type': 'movie',
                        'size_mb': round(os.path.getsize(main_video) / (1024 * 1024), 1),
                        'already_imported': already
                    })
            elif entry.endswith(VIDEO_EXTS):
                # Archivo suelto en movies/
                rel_video = os.path.relpath(full_entry_path, media_root).replace('\\', '/')
                title = clean_movie_title(entry)
                already = (rel_video in existing_files) or (title.lower() in existing_titles)
                
                rad_match = find_radarr_match('', rel_video, radarr_movies)
                synopsis = rad_match.get('overview') if rad_match else None
                poster_url = None
                genres = ", ".join(rad_match.get('genres', [])) if rad_match and rad_match.get('genres') else 'Película'
                author = rad_match.get('studio') if rad_match else ''
                if rad_match:
                    for img in rad_match.get('images', []):
                        if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                            poster_url = img.get('remoteUrl')
                            break

                discovered_movies.append({
                    'title': title,
                    'folder': '',
                    'file': rel_video,
                    'cover_rel': None,
                    'poster_remote_url': poster_url,
                    'synopsis': synopsis or "Película de alta definición.",
                    'category': genres or "Película",
                    'author': author or "",
                    'type': 'movie',
                    'size_mb': round(os.path.getsize(full_entry_path) / (1024 * 1024), 1),
                    'already_imported': already
                })

    discovered_series = []
    # Escaneo de series / anime
    if os.path.exists(series_dir):
        for series_folder in sorted(os.listdir(series_dir)):
            full_series_path = os.path.join(series_dir, series_folder)
            if os.path.isdir(full_series_path):
                video_files = []
                total_size = 0
                for root, _, files in os.walk(full_series_path):
                    for f in files:
                        if f.endswith(VIDEO_EXTS):
                            p = os.path.join(root, f)
                            video_files.append(p)
                            total_size += os.path.getsize(p)
                if video_files:
                    video_files.sort(key=natural_sort_filename_key)
                    rel_files = [os.path.relpath(p, media_root).replace('\\', '/') for p in video_files]
                    poster_path = find_poster_in_folder(full_series_path)
                    rel_poster = os.path.relpath(poster_path, media_root).replace('\\', '/') if poster_path else None
                    title = clean_movie_title(series_folder)
                    already = any(rf in existing_files for rf in rel_files) or (title.lower() in existing_titles)
                    
                    son_match = find_sonarr_match(series_folder, sonarr_series_list)
                    synopsis = son_match.get('overview') if son_match else None
                    poster_url = None
                    genres = ", ".join(son_match.get('genres', [])) if son_match and son_match.get('genres') else 'Serie'
                    author = son_match.get('network') if son_match else ''
                    if son_match:
                        for img in son_match.get('images', []):
                            if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                                poster_url = img.get('remoteUrl')
                                break

                    discovered_series.append({
                        'title': title,
                        'folder': series_folder,
                        'file': rel_files,
                        'files': rel_files,
                        'episodes_count': len(rel_files),
                        'cover_rel': rel_poster,
                        'poster_remote_url': poster_url,
                        'synopsis': synopsis or "Serie de televisión / Anime.",
                        'category': genres or "Serie",
                        'author': author or "",
                        'type': 'series',
                        'size_mb': round(total_size / (1024 * 1024), 1),
                        'already_imported': already
                    })

    return {
        'media_root': media_root,
        'movies': discovered_movies,
        'series': discovered_series,
        'stats': {
            'total_movies': len(discovered_movies),
            'new_movies': len([m for m in discovered_movies if not m['already_imported']]),
            'total_series': len(discovered_series),
            'new_series': len([s for s in discovered_series if not s['already_imported']])
        }
    }

def generate_nfc_key():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"NFC-{chars}"

def get_disk_status():
    gb = 1024 * 1024 * 1024
    mounts = ['/', '/data/media', '/data/storage2', '/data/ssd']
    tot_bytes = 0
    usd_bytes = 0
    fre_bytes = 0

    media_info = None
    storage2_info = None
    ssd_info = None
    root_info = None

    for m in mounts:
        if os.path.exists(m):
            try:
                t, u, f = shutil.disk_usage(m)
                tot_bytes += t
                usd_bytes += u
                fre_bytes += f
                info = {
                    'total': round(t / gb, 1),
                    'used': round(u / gb, 1),
                    'free': round(f / gb, 1),
                    'percent_used': round((u / t) * 100, 1) if t > 0 else 0
                }
                if m == '/':
                    root_info = info
                elif m == '/data/media':
                    media_info = info
                elif m == '/data/storage2':
                    storage2_info = info
                elif m == '/data/ssd':
                    ssd_info = info
            except Exception:
                pass

    if tot_bytes == 0:
        t, u, f = shutil.disk_usage(BASE_DIR)
        tot_bytes, usd_bytes, fre_bytes = t, u, f

    return {
        'total': round(tot_bytes / gb, 1),
        'used': round(usd_bytes / gb, 1),
        'free': round(fre_bytes / gb, 1),
        'percent_used': round((usd_bytes / tot_bytes) * 100, 1) if tot_bytes > 0 else 0,
        'media': media_info,
        'storage2': storage2_info,
        'ssd': ssd_info,
        'root': root_info
    }

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"admin_pass": "admin123"}

def save_config(config):
    dir_name = os.path.dirname(CONFIG_FILE)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        json.dump(config, tf, indent=4, ensure_ascii=False)
        temp_name = tf.name
    os.replace(temp_name, CONFIG_FILE)

def load_books():
    # Migrar de books.json a catalog.json si el viejo existe y el nuevo no
    if not os.path.exists(DB_FILE) and os.path.exists(OLD_DB_FILE):
        try:
            with open(OLD_DB_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            # Agregar tipo 'book' por defecto a las obras antiguas
            for item in old_data:
                if 'type' not in item:
                    item['type'] = 'book'
            save_books(old_data)
        except Exception as e:
            print("Error migrando base de datos:", e)

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_books(books):
    dir_name = os.path.dirname(DB_FILE)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        json.dump(books, tf, indent=4, ensure_ascii=False)
        temp_name = tf.name
    os.replace(temp_name, DB_FILE)

UNAR_BIN = shutil.which('unar') or '/usr/bin/unar'
UNRAR_BIN = shutil.which('unrar') or '/usr/bin/unrar'
SEVENZ_BIN = shutil.which('7z') or '/usr/bin/7z'
RAR_BIN = shutil.which('rar') or '/usr/bin/rar'

def extract_cbr_pages(book_id, filepath):
    """ Extrae un archivo CBR/RAR a la carpeta de caché y mapea las imágenes incluso dentro de subcarpetas con orden natural """
    if not filepath:
        return []
        
    resolved_path = resolve_media_file_path(filepath) or filepath
    if not os.path.exists(resolved_path):
        resolved_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(filepath))
        if not os.path.exists(resolved_path):
            print(f"[CBR Extract] Archivo no encontrado: {filepath}")
            return []

    target_dir = os.path.join(CACHE_FOLDER, book_id)
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')

    def get_existing_images():
        imgs = []
        if os.path.exists(target_dir):
            for root, _, files in os.walk(target_dir):
                for f in files:
                    if f.endswith(valid_exts):
                        full_p = os.path.join(root, f)
                        if os.path.getsize(full_p) > 0:
                            rel_p = os.path.relpath(full_p, target_dir).replace('\\', '/')
                            imgs.append(rel_p)
        return imgs

    images = get_existing_images()
    
    if not images:
        os.makedirs(target_dir, exist_ok=True)
        extracted = False

        # Método 1: unar (El más universal y tolerante para CBR/RAR)
        try:
            res = subprocess.run([UNAR_BIN, "-o", target_dir, "-f", resolved_path], capture_output=True, timeout=30)
            if res.returncode == 0 and len(get_existing_images()) > 0:
                extracted = True
        except Exception as e:
            print(f"[CBR Extract unar error]: {e}")

        # Método 2: unrar
        if not extracted:
            try:
                res = subprocess.run([UNRAR_BIN, "x", "-o+", "-y", resolved_path, target_dir + "/"], capture_output=True, timeout=30)
                if res.returncode == 0 and len(get_existing_images()) > 0:
                    extracted = True
            except Exception as e:
                print(f"[CBR Extract unrar error]: {e}")

        # Método 3: 7z
        if not extracted:
            try:
                res = subprocess.run([SEVENZ_BIN, "x", "-y", f"-o{target_dir}", resolved_path], capture_output=True, timeout=30)
                if res.returncode == 0 and len(get_existing_images()) > 0:
                    extracted = True
            except Exception as e:
                print(f"[CBR Extract 7z error]: {e}")

        # Método 4: rar
        if not extracted:
            try:
                res = subprocess.run([RAR_BIN, "x", "-y", "-o+", resolved_path, target_dir + "/"], capture_output=True, timeout=30)
                if res.returncode == 0 and len(get_existing_images()) > 0:
                    extracted = True
            except Exception as e:
                print(f"[CBR Extract rar error]: {e}")

        # Método 5: zipfile nativo de Python (muchos CBRs son internamente ZIPs renombrados)
        if not extracted:
            try:
                with zipfile.ZipFile(resolved_path, 'r') as zf:
                    zf.extractall(target_dir)
                if len(get_existing_images()) > 0:
                    extracted = True
            except Exception:
                pass

        # Método 6: rarfile de Python si estuviera instalado
        if not extracted:
            try:
                rarfile_mod = __import__('rarfile')
                with rarfile_mod.RarFile(resolved_path, 'r') as rf:
                    rf.extractall(target_dir)
                if len(get_existing_images()) > 0:
                    extracted = True
            except Exception:
                pass

        images = get_existing_images()

    # Ordenamiento natural para que las páginas queden en secuencia numérica real
    images.sort(key=natural_sort_filename_key)
    
    # Genera las URLs soportando la subcarpeta interna y escapando caracteres especiales (#, espacios, etc.)
    urls = [f"/cache_file/{book_id}/{urllib.parse.quote(filename, safe='/')}" for filename in images]
    return urls

# ----------------- RUTAS PÚBLICAS Y LECTOR WEB -----------------

def natural_sort_key(book):
    """Sort key that extracts numbers for natural episode/volume ordering (Tomo 1 < Tomo 2 < Tomo 10)."""
    title = book.get('title', '')
    nums = [int(n) for n in re.findall(r'\d+', title)]
    clean_title = re.sub(r'[^\w\s]', '', title.lower())
    return (nums[0] if nums else 999999, clean_title, title)

def get_grouped_category_books(filtered_books, allow_random=True):
    """
    Agrupa obras por saga para Manga, Anime, Series, Música, Libros, etc.
    Solo muestra 1 tarjeta por saga en la galería.
    Soporta:
    - is_saga_cover: tomo explícito fijado como portada de la saga.
    - saga_random_cover: rotación aleatoria de portada en cada visita a la galería.
    - show_in_gallery: False para ocultar tomos individuales si se desea.
    """
    saga_groups = {}
    no_saga_books = []
    
    for b in filtered_books:
        # Si explícitamente se configuró show_in_gallery == False, no se muestra en la galería principal
        if b.get('show_in_gallery') is False:
            continue
            
        saga_name = b.get('saga', '').strip()
        if saga_name:
            s_key = saga_name.lower()
            if s_key not in saga_groups:
                saga_groups[s_key] = []
            saga_groups[s_key].append(b)
        else:
            no_saga_books.append(b)
            
    grouped_books = []
    for s_key, items in saga_groups.items():
        try:
            items.sort(key=natural_sort_key)
        except Exception:
            pass
        
        # Verificar si la saga tiene rotación aleatoria activada
        has_random = any(it.get('saga_random_cover') is True for it in items)
        
        # Verificar si algún tomo está marcado explícitamente como portada fija
        featured = next((it for it in items if it.get('is_saga_cover') is True), None)
        
        if has_random and allow_random and len(items) > 1:
            chosen = random.choice(items)
        elif featured:
            chosen = featured
        else:
            chosen = items[0] # Por defecto el primer tomo
            
        card_item = dict(chosen)
        card_item['saga_total_items'] = len(items)
        card_item['is_saga_group'] = True
        card_item['has_random_cover'] = has_random
        grouped_books.append(card_item)
        
    return grouped_books + no_saga_books

@app.route('/')
def index():
    books = load_books()
    
    # Calcular cantidades por tipo de contenido para el index (contando sagas únicas + obras independientes)
    type_counts = {'book': 0, 'manga': 0, 'movie': 0, 'series': 0, 'music': 0, 'anime': 0}
    for t in type_counts.keys():
        t_books = [b for b in books if b.get('type', 'book') == t]
        type_counts[t] = len(get_grouped_category_books(t_books, allow_random=False))
            
    # Obtener las últimas obras agrupadas por saga para la galería de recientes
    recent_grouped = get_grouped_category_books(list(reversed(books)), allow_random=False)[:12]
            
    return render_template('index.html', type_counts=type_counts, recent_books=recent_grouped)

@app.route('/music')
@app.route('/category/<category_name>')
def category_view(category_name='music'):
    books = load_books()
    raw_filtered = [b for b in books if b.get('type', 'book') == category_name]
    
    # Vista especializada estilo Apple Music para Música
    if category_name == 'music':
        return render_template(
            'music.html',
            books=raw_filtered,
            category_name=category_name,
            category_title='Música'
        )

    # Agrupar obras por saga para Manga, Anime, Series, Libros
    filtered_books = get_grouped_category_books(raw_filtered, allow_random=True)
    
    # Lógica de Paginación (20 elementos por página)
    try:
        page = request.args.get('page', 1, type=int)
    except Exception:
        page = 1
        
    per_page = 20
    total_items = len(filtered_books)
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
        
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_books = filtered_books[start_idx:end_idx]
    
    # Mapeo de nombres legibles para la interfaz
    category_titles = {
        'book': 'Libros',
        'manga': 'Mangas',
        'movie': 'Películas',
        'series': 'Series',
        'music': 'Música',
        'anime': 'Animes'
    }
    title = category_titles.get(category_name, category_name.capitalize())
    
    return render_template(
        'category.html', 
        books=paginated_books, 
        category_name=category_name, 
        category_title=title,
        page=page,
        total_pages=total_pages,
        total_items=total_items
    )

@app.route('/nfc/<nfc_key>')
def nfc_reader(nfc_key):
    books = load_books()
    book = next((b for b in books if b.get('nfc_key', '').upper() == nfc_key.upper()), None)
    if book:
        return redirect(url_for('book_detail', book_id=book['id']))
    return render_template('not_found.html', nfc_key=nfc_key), 404

@app.route('/book/<book_id>')
def book_detail(book_id):
    books = load_books()
    book = next((b for b in books if b.get('id') == book_id), None)
    if not book:
        flash("Obra no encontrada", "error")
        return redirect(url_for('index'))
    
    # Obras del mismo autor (excluyendo la actual)
    author = book.get('author', '').strip()
    related_author = []
    if author:
        related_author = [b for b in books if b.get('author') and b.get('author').strip().lower() == author.lower() and b.get('id') != book_id]
        try:
            related_author.sort(key=natural_sort_key)
        except Exception:
            pass
        
    # Obras de la misma saga / grupo / álbum (excluyendo la actual)
    saga = book.get('saga', '').strip()
    related_saga = []
    saga_books = []
    if saga:
        related_saga = [b for b in books if b.get('saga') and b.get('saga').strip().lower() == saga.lower() and b.get('id') != book_id]
        # Todos los capítulos del lote/saga ordenados
        saga_books = [b for b in books if b.get('saga') and b.get('saga').strip().lower() == saga.lower()]
        try:
            related_saga.sort(key=natural_sort_key)
            saga_books.sort(key=natural_sort_key)
        except Exception:
            pass
        
    return render_template('book.html', book=book, related_author=related_author, related_saga=related_saga, saga_books=saga_books)

@app.route('/read/<book_id>')
def web_reader(book_id):
    books = load_books()
    book = next((b for b in books if b.get('id') == book_id), None)
    if book:
        media_type = book.get('type', 'book')
        if media_type not in ['book', 'manga']:
            return redirect(url_for('web_player', media_id=book_id))
            
        filename = book.get('file', '')
        file_ext = os.path.splitext(filename)[1].replace('.', '').strip().lower()
        
        cbr_images = []
        if file_ext == 'cbr':
            filepath = resolve_media_file_path(filename) or os.path.join(app.config['UPLOAD_FOLDER'], filename)
            cbr_images = extract_cbr_pages(book_id, filepath)

        return render_template('reader.html', book=book, file_ext=file_ext, cbr_images=cbr_images)
    flash("Obra no encontrada", "error")
    return redirect(url_for('admin'))

@app.route('/player/<media_id>')
def web_player(media_id):
    books = load_books()
    book = next((b for b in books if b.get('id') == media_id), None)
    if book:
        media_type = book.get('type', 'movie')
        if media_type in ['book', 'manga']:
            return redirect(url_for('web_reader', book_id=media_id))
            
        saga = book.get('saga', '').strip()
        saga_books = []
        if saga and media_type in ['series', 'anime', 'music']:
            saga_books = [b for b in books if b.get('saga') and b.get('saga').strip().lower() == saga.lower()]
            try:
                saga_books.sort(key=natural_sort_key)
            except Exception:
                pass

        file_val = book.get('file')
        return render_template('player.html', media=book, media_type=media_type, file_val=file_val, saga_books=saga_books)
    flash("Obra no encontrada", "error")
    return redirect(url_for('admin'))

FFMPEG_BIN = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'
FFPROBE_BIN = shutil.which('ffprobe') or '/usr/bin/ffprobe'
MEDIA_PROBE_CACHE = {}

def probe_media_codecs(file_path):
    """Analiza los códecs de video y audio con ffprobe, almacenando el resultado en caché."""
    if not file_path or not os.path.exists(file_path):
        return {'video_codec': None, 'audio_codec': None, 'duration': 0, 'mtime': 0}
    
    try:
        mtime = os.path.getmtime(file_path)
    except Exception:
        mtime = 0
        
    cached = MEDIA_PROBE_CACHE.get(file_path)
    if cached and cached.get('mtime') == mtime:
        return cached

    v_codec = None
    a_codec = None
    duration = 0.0

    try:
        cmd = [
            FFPROBE_BIN, "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            for st in data.get('streams', []):
                if st.get('codec_type') == 'video' and not v_codec:
                    v_codec = st.get('codec_name', '').lower()
                elif st.get('codec_type') == 'audio' and not a_codec:
                    a_codec = st.get('codec_name', '').lower()
                    
            try:
                duration = float(data.get('format', {}).get('duration', 0))
            except Exception:
                duration = 0.0
    except Exception as e:
        print(f"Error analizando códecs para {file_path}:", e)

    result = {
        'video_codec': v_codec,
        'audio_codec': a_codec,
        'duration': duration,
        'mtime': mtime
    }
    MEDIA_PROBE_CACHE[file_path] = result
    return result

def resolve_media_file_path(filename):
    """Resuelve la ruta física absoluta de un archivo multimedia según las carpetas configuradas."""
    if not filename:
        return None

    # 1. Buscar en static/uploads
    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(upload_path) and os.path.isfile(upload_path):
        return upload_path
    
    # 2. Buscar en media_root (/data/media o data/media)
    media_root = get_media_root()
    media_path = os.path.join(media_root, filename)
    if os.path.exists(media_path) and os.path.isfile(media_path):
        return media_path

    # 3. Ruta absoluta
    if os.path.isabs(filename) and os.path.exists(filename) and os.path.isfile(filename):
        return filename

    return None

def stream_video_file_pipeline(file_path, start_time=0.0):
    """
    Genera un flujo de video MP4 compatible con cualquier navegador web:
    - Direct Play: Si el video ya es MP4 con H.264 y AAC/MP3.
    - Remux (Copia Directa): Si el video es H.264 pero está en MKV o audio incompatible (0% CPU, calidad 100%).
    - Transcode Ligero: Si el video es x265/HEVC/XviD, se convierte en tiempo real con preset muy rápido.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext not in VIDEO_EXTS:
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), conditional=True)

    probe = probe_media_codecs(file_path)
    v_codec = probe.get('video_codec')
    a_codec = probe.get('audio_codec')

    # Si ya es MP4 nativo con codecs compatibles y sin salto inicial, servir directo por HTTP
    if ext == '.mp4' and v_codec in ['h264', 'avc1'] and a_codec in ['aac', 'mp3', None] and start_time == 0:
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), conditional=True)

    video_copy = (v_codec in ['h264', 'avc1'])

    cmd = [FFMPEG_BIN, "-loglevel", "error"]
    if start_time > 0:
        cmd.extend(["-ss", str(start_time)])
        
    cmd.extend(["-i", file_path])

    if video_copy:
        # Copia directa de video sin recodificar (100% calidad original, 0% CPU)
        cmd.extend(["-c:v", "copy"])
    else:
        # Transcodificación ultra-rápida (115+ FPS / 5x tiempo real): elimina por completo el buffering
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "23",
            "-vf", "scale=trunc(min(1280,iw)/2)*2:trunc(ow/a/2)*2",
            "-pix_fmt", "yuv420p",
            "-threads", "4"
        ])

    # Audio convertido a AAC estéreo universal
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4",
        "pipe:1"
    ])

    def generate_video_stream():
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**6)
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass

    return Response(stream_with_context(generate_video_stream()), mimetype='video/mp4')

@app.route('/stream/<path:filename>')
def stream_media(filename):
    """ Endpoint principal de streaming adaptativo en vivo para películas y videos individuales """
    file_path = resolve_media_file_path(filename)
    if not file_path:
        return ("Archivo no encontrado", 404)

    start_time = request.args.get('t', default=0, type=float)
    return stream_video_file_pipeline(file_path, start_time)

# =========================================================================
# MONITOR Y CONVERSOR DE FORMATOS WEB
# =========================================================================
@app.route('/converter')
@app.route('/admin/converter')
def converter_view():
    """ Vista visual interactiva para monitorear el progreso de conversión a MP4 """
    return render_template('converter.html')

@app.route('/api/converter/status')
def converter_api_status():
    """ API JSON que devuelve el estado en tiempo real del conversor """
    status_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'conversion_status.json')
    data = {
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
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass

    # Comprobar si el proceso o servicio sigue activo en el sistema
    try:
        res = subprocess.run(['pgrep', '-f', 'convert_movies_to_mp4.py'], capture_output=True, text=True)
        is_proc_running = bool(res.stdout.strip())
        data['is_running'] = is_proc_running
    except Exception:
        pass

    # Calcular progreso en MB del archivo actual si se está procesando
    current_title = data.get('current_title')
    data['current_mb_written'] = 0
    data['current_mb_total'] = 0
    data['current_file_percent'] = 0
    
    if data.get('is_running') and current_title:
        media_root = get_media_root()
        movie_dir = os.path.join(media_root, 'movies', current_title)
        if os.path.exists(movie_dir):
            for f in os.listdir(movie_dir):
                if '_web.mp4' in f:
                    web_p = os.path.join(movie_dir, f)
                    try:
                        data['current_mb_written'] = round(os.path.getsize(web_p) / (1024 * 1024), 1)
                    except Exception:
                        pass
                elif f.lower().endswith(('.mkv', '.avi', '.mp4', '.m4v')) and not f.endswith('_web.mp4'):
                    orig_p = os.path.join(movie_dir, f)
                    try:
                        data['current_mb_total'] = round(os.path.getsize(orig_p) / (1024 * 1024), 1)
                    except Exception:
                        pass

        total_mb = float(data.get('current_mb_total') or 0)
        written_mb = float(data.get('current_mb_written') or 0)
        if total_mb > 0.0 and written_mb > 0.0:
            data['current_file_percent'] = min(100.0, round((written_mb / total_mb) * 100, 1))

    return jsonify(data)

@app.route('/api/converter/start', methods=['POST'])
def converter_api_start():
    """ Inicia o reanuda la conversión masiva en segundo plano """
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'tapbox-converter'], check=False)
        return jsonify({"success": True, "message": "Conversión iniciada exitosamente"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/converter/stop', methods=['POST'])
def converter_api_stop():
    """ Detiene la conversión """
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'tapbox-converter'], check=False)
        return jsonify({"success": True, "message": "Conversión detenida"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =========================================================================
# OPTIMIZADOR Y LIMPIEZA DE ALMACENAMIENTO
# =========================================================================
@app.route('/cleaner')
@app.route('/admin/cleaner')
def cleaner_view():
    """ Vista interactiva para diagnosticar y liberar espacio en disco """
    return render_template('cleaner.html')

def get_dir_size(path):
    total = 0
    if os.path.exists(path):
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    return total

@app.route('/api/cleaner/status')
def cleaner_api_status():
    """ API para obtener estadísticas de disco, duplicados y temporales """
    disk_total = "454 GB"
    disk_used = "284 GB"
    disk_avail = "147 GB"
    disk_percent = 66.0
    try:
        st = shutil.disk_usage('/')
        disk_total = f"{round(st.total / (1024**3), 1)} GB"
        disk_used = f"{round(st.used / (1024**3), 1)} GB"
        disk_avail = f"{round(st.free / (1024**3), 1)} GB"
        disk_percent = round((st.used / st.total) * 100, 1)
    except Exception:
        pass

    media_root = get_media_root()
    movies_dir = os.path.join(media_root, 'movies')
    torrents_dir = '/data/torrents'
    uploads_dir = app.config['UPLOAD_FOLDER']

    movies_sz = get_dir_size(movies_dir)
    torrents_sz = get_dir_size(torrents_dir) if os.path.exists(torrents_dir) else 0
    uploads_sz = get_dir_size(uploads_dir)

    converted_titles = []
    if os.path.exists(movies_dir):
        for root, dirs, files in os.walk(movies_dir):
            mp4s = [f for f in files if f.lower().endswith('.mp4') and not f.endswith('_web.mp4')]
            if mp4s:
                converted_titles.append(os.path.basename(root).lower())

    duplicates = []
    if os.path.exists(torrents_dir):
        for entry in os.listdir(torrents_dir):
            full_p = os.path.join(torrents_dir, entry)
            low_e = entry.lower()
            match = False
            for ct in converted_titles:
                clean_ct = ct.split('(')[0].strip()
                if clean_ct and len(clean_ct) > 3 and clean_ct in low_e:
                    match = True
                    break
            
            if match:
                try:
                    if os.path.isfile(full_p):
                        sz = os.path.getsize(full_p)
                    else:
                        sz = get_dir_size(full_p)
                    duplicates.append({
                        "name": entry,
                        "path": full_p,
                        "size_bytes": sz,
                        "size_formatted": format_file_size(sz),
                        "type": "file" if os.path.isfile(full_p) else "folder"
                    })
                except Exception:
                    pass

    temp_files = []
    if os.path.exists(movies_dir):
        for root, dirs, files in os.walk(movies_dir):
            for f in files:
                if f.endswith('_web.mp4') or f.endswith('.tmp') or f.endswith('.part'):
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        temp_files.append({
                            "name": f,
                            "path": fp,
                            "size_bytes": sz,
                            "size_formatted": format_file_size(sz)
                        })
                    except Exception:
                        pass

    return jsonify({
        "disk_total": disk_total,
        "disk_used": disk_used,
        "disk_avail": disk_avail,
        "disk_used_percent": disk_percent,
        "movies_size": format_file_size(movies_sz),
        "torrents_size": format_file_size(torrents_sz),
        "uploads_size": format_file_size(uploads_sz),
        "duplicates": duplicates,
        "temp_files": temp_files
    })

@app.route('/api/cleaner/clean-duplicates', methods=['POST'])
def cleaner_api_clean_duplicates():
    """ Limpia automáticamente torrents ya convertidos y archivos temporales """
    freed_bytes = 0
    deleted = []
    
    media_root = get_media_root()
    movies_dir = os.path.join(media_root, 'movies')
    if os.path.exists(movies_dir):
        for root, dirs, files in os.walk(movies_dir):
            for f in files:
                if f.endswith('_web.mp4') or f.endswith('.tmp') or f.endswith('.part'):
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        os.remove(fp)
                        freed_bytes += sz
                        deleted.append(f)
                    except Exception:
                        pass

    torrents_dir = '/data/torrents'
    converted_titles = []
    if os.path.exists(movies_dir):
        for root, dirs, files in os.walk(movies_dir):
            mp4s = [f for f in files if f.lower().endswith('.mp4') and not f.endswith('_web.mp4')]
            if mp4s:
                converted_titles.append(os.path.basename(root).lower())

    if os.path.exists(torrents_dir):
        for entry in os.listdir(torrents_dir):
            full_p = os.path.join(torrents_dir, entry)
            low_e = entry.lower()
            match = False
            for ct in converted_titles:
                clean_ct = ct.split('(')[0].strip()
                if clean_ct and len(clean_ct) > 3 and clean_ct in low_e:
                    match = True
                    break
            
            if match:
                try:
                    if os.path.isfile(full_p):
                        sz = os.path.getsize(full_p)
                        os.remove(full_p)
                        freed_bytes += sz
                        deleted.append(entry)
                    elif os.path.isdir(full_p):
                        sz = get_dir_size(full_p)
                        shutil.rmtree(full_p)
                        freed_bytes += sz
                        deleted.append(entry)
                except Exception:
                    pass

    return jsonify({
        "success": True,
        "freed_bytes": freed_bytes,
        "freed_formatted": format_file_size(freed_bytes),
        "deleted_items": deleted
    })

@app.route('/api/cleaner/delete-item', methods=['POST'])
def cleaner_api_delete_item():
    """ Elimina un archivo o carpeta individual detectada """
    req_data = request.get_json(silent=True) or {}
    path = req_data.get('path', '').strip()
    if not path or not os.path.exists(path):
        return jsonify({"success": False, "error": "Ruta inválida o inexistente"}), 400
    
    norm_path = os.path.abspath(path)
    allowed_roots = ['/data/torrents', '/data/media', app.config['UPLOAD_FOLDER']]
    if not any(norm_path.startswith(os.path.abspath(ar)) for ar in allowed_roots if os.path.exists(ar)):
        return jsonify({"success": False, "error": "Operación no permitida fuera de las áreas multimedia"}), 403

    try:
        if os.path.isfile(norm_path):
            os.remove(norm_path)
        elif os.path.isdir(norm_path):
            shutil.rmtree(norm_path)
        return jsonify({"success": True, "path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =========================================================================
# GESTOR Y LISTA COMPLETA DE ARCHIVOS DEL SERVIDOR
# =========================================================================
def format_file_size(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024 * 1024), 2)} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024), 1)} MB"
    elif size_bytes >= 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    return f"{size_bytes} B"

def get_file_content_type(ext, path=""):
    ext = ext.lower()
    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v']:
        if '/series/' in path.replace('\\', '/') or 'anime' in path.lower():
            return ('series', 'Serie / Anime')
        return ('movie', 'Película')
    elif ext in ['.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma', '.alac', '.aiff']:
        return ('music', 'Música')
    elif ext in ['.cbr', '.cbz']:
        return ('manga', 'Manga / Cómic')
    elif ext in ['.pdf', '.epub']:
        return ('book', 'Libro / Documento')
    elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
        return ('image', 'Imagen / Portada')
    elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
        return ('archive', 'Archivo Comprimido')
    return ('other', 'Otro Archivo')

def scan_all_storage_files():
    """
    Escanea todos los archivos físicos en /data/media y static/uploads,
    asociándolos con el catálogo si están registrados, eliminando duplicados por enlaces simbólicos.
    """
    books = load_books()
    file_to_book = {}
    for b in books:
        f_val = b.get('file')
        b_id = b.get('id')
        b_type = b.get('type')
        b_title = b.get('title')
        if isinstance(f_val, list):
            for item in f_val:
                file_to_book[item.replace('\\', '/')] = (b_id, b_type, b_title)
                file_to_book[os.path.basename(item)] = (b_id, b_type, b_title)
        elif isinstance(f_val, str):
            file_to_book[f_val.replace('\\', '/')] = (b_id, b_type, b_title)
            file_to_book[os.path.basename(f_val)] = (b_id, b_type, b_title)

    media_root = get_media_root()
    upload_folder = app.config['UPLOAD_FOLDER']
    
    seen_paths = set()
    files_list = []

    # 1. Escaneo en /data/media
    if os.path.exists(media_root):
        for root, _, files in os.walk(media_root):
            for f in files:
                if f.startswith('.'):
                    continue
                full_p = os.path.join(root, f)
                try:
                    real_p = os.path.realpath(full_p)
                except Exception:
                    real_p = full_p
                if real_p in seen_paths:
                    continue
                seen_paths.add(real_p)
                
                try:
                    st = os.stat(full_p)
                    size_bytes = st.st_size
                    mtime = st.st_mtime
                except Exception:
                    continue

                rel_p = os.path.relpath(full_p, media_root).replace('\\', '/')
                ext = os.path.splitext(f)[1].lower()
                c_type, c_label = get_file_content_type(ext, full_p)
                
                book_info = file_to_book.get(rel_p) or file_to_book.get(f)
                book_id = book_info[0] if book_info else None
                if book_info and book_info[1]:
                    c_type = book_info[1]
                    c_label = {'movie': 'Película', 'series': 'Serie', 'anime': 'Anime', 'music': 'Música', 'book': 'Libro', 'manga': 'Manga'}.get(c_type, c_label)
                book_title = book_info[2] if book_info else os.path.splitext(f)[0]

                files_list.append({
                    'filename': f,
                    'title': book_title,
                    'path': full_p,
                    'rel_path': f"/data/media/{rel_p}",
                    'size_bytes': size_bytes,
                    'size_formatted': format_file_size(size_bytes),
                    'mtime': mtime,
                    'date_formatted': time.strftime('%d/%m/%Y %H:%M', time.localtime(mtime)),
                    'ext': ext,
                    'type': c_type,
                    'type_label': c_label,
                    'book_id': book_id,
                    'is_video': ext in VIDEO_EXTS,
                    'is_mp4': ext == '.mp4'
                })

    # 2. Escaneo en static/uploads (solo si no fue cubierto por media_root)
    if os.path.exists(upload_folder):
        for root, _, files in os.walk(upload_folder):
            for f in files:
                if f.startswith('.'):
                    continue
                full_p = os.path.join(root, f)
                try:
                    real_p = os.path.realpath(full_p)
                except Exception:
                    real_p = full_p
                if real_p in seen_paths:
                    continue
                seen_paths.add(real_p)

                try:
                    st = os.stat(full_p)
                    size_bytes = st.st_size
                    mtime = st.st_mtime
                except Exception:
                    continue

                rel_p = os.path.relpath(full_p, BASE_DIR).replace('\\', '/')
                ext = os.path.splitext(f)[1].lower()
                c_type, c_label = get_file_content_type(ext, full_p)

                book_info = file_to_book.get(f)
                book_id = book_info[0] if book_info else None
                if book_info and book_info[1]:
                    c_type = book_info[1]
                    c_label = {'movie': 'Película', 'series': 'Serie', 'anime': 'Anime', 'music': 'Música', 'book': 'Libro', 'manga': 'Manga'}.get(c_type, c_label)
                book_title = book_info[2] if book_info else os.path.splitext(f)[0]

                files_list.append({
                    'filename': f,
                    'title': book_title,
                    'path': full_p,
                    'rel_path': rel_p,
                    'size_bytes': size_bytes,
                    'size_formatted': format_file_size(size_bytes),
                    'mtime': mtime,
                    'date_formatted': time.strftime('%d/%m/%Y %H:%M', time.localtime(mtime)),
                    'ext': ext,
                    'type': c_type,
                    'type_label': c_label,
                    'book_id': book_id,
                    'is_video': ext in VIDEO_EXTS,
                    'is_mp4': ext == '.mp4'
                })

    files_list.sort(key=lambda x: x['mtime'], reverse=True)
    return files_list

@app.route('/files')
@app.route('/admin/files')
def files_view():
    """ Vista completa de gestión de archivos y almacenamiento """
    return render_template('files.html')

@app.route('/api/files/list')
def api_files_list():
    """ Devuelve la lista completa de archivos con sus tamaños, fechas, tipos y rutas """
    files_list = scan_all_storage_files()
    disk = get_disk_status()
    total_size = sum(f['size_bytes'] for f in files_list)
    
    # Resumen por tipos
    type_counts = {}
    type_sizes = {}
    for f in files_list:
        t = f['type']
        type_counts[t] = type_counts.get(t, 0) + 1
        type_sizes[t] = type_sizes.get(t, 0) + f['size_bytes']

    return jsonify({
        'files': files_list,
        'total_count': len(files_list),
        'total_size_bytes': total_size,
        'total_size_formatted': format_file_size(total_size),
        'type_counts': type_counts,
        'type_sizes': {k: format_file_size(v) for k, v in type_sizes.items()},
        'disk': disk
    })

@app.route('/api/files/delete', methods=['POST'])
def api_files_delete():
    """ Elimina un archivo físico del servidor y actualiza el catálogo si aplica """
    req_data = request.get_json() or {}
    file_path = req_data.get('filepath', '').strip()
    book_id = req_data.get('book_id')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'success': False, 'error': 'El archivo no existe en el servidor'}), 404

    media_root = get_media_root()
    upload_folder = app.config['UPLOAD_FOLDER']
    abs_path = os.path.abspath(file_path)
    
    is_safe = (abs_path.startswith(os.path.abspath(media_root)) or 
               abs_path.startswith(os.path.abspath(upload_folder)))
    if not is_safe:
        return jsonify({'success': False, 'error': 'Ruta no permitida para eliminación'}), 403

    try:
        size_freed = os.path.getsize(abs_path)
        os.remove(abs_path)

        # Si la subcarpeta queda vacía, eliminarla
        parent_dir = os.path.dirname(abs_path)
        if os.path.exists(parent_dir) and len(os.listdir(parent_dir)) == 0 and parent_dir not in [media_root, upload_folder]:
            try:
                os.rmdir(parent_dir)
            except Exception:
                pass

        # Actualizar catálogo si está asociado
        books = load_books()
        updated_catalog = False
        new_books = []
        fname = os.path.basename(abs_path)

        for b in books:
            b_file = b.get('file')
            if isinstance(b_file, list):
                b['file'] = [f for f in b_file if os.path.basename(f) != fname and f != abs_path]
                if len(b['file']) == 0:
                    updated_catalog = True
                    continue
                elif len(b['file']) != len(b_file):
                    updated_catalog = True
            elif isinstance(b_file, str):
                if os.path.basename(b_file) == fname or b_file == abs_path or (book_id and b.get('id') == book_id):
                    updated_catalog = True
                    continue
            new_books.append(b)

        if updated_catalog:
            save_books(new_books)

        return jsonify({
            'success': True, 
            'message': f"Archivo eliminado ({format_file_size(size_freed)} liberados)",
            'freed_bytes': size_freed
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/delete-batch', methods=['POST'])
def api_files_delete_batch():
    """ Elimina múltiples archivos seleccionados para liberar espacio masivo """
    req_data = request.get_json() or {}
    file_paths = req_data.get('filepaths', [])
    if not file_paths or not isinstance(file_paths, list):
        return jsonify({'success': False, 'error': 'No se especificaron archivos'}), 400

    media_root = os.path.abspath(get_media_root())
    upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
    
    total_freed = 0
    deleted_count = 0
    errors = []

    for fp in file_paths:
        abs_p = os.path.abspath(fp)
        if (abs_p.startswith(media_root) or abs_p.startswith(upload_folder)) and os.path.exists(abs_p):
            try:
                sz = os.path.getsize(abs_p)
                os.remove(abs_p)
                total_freed += sz
                deleted_count += 1
            except Exception as e:
                errors.append(f"{os.path.basename(abs_p)}: {str(e)}")

    # Sincronizar catálogo para remover archivos eliminados
    if deleted_count > 0:
        books = load_books()
        deleted_basenames = {os.path.basename(fp) for fp in file_paths}
        new_books = []
        for b in books:
            b_file = b.get('file')
            if isinstance(b_file, list):
                b['file'] = [f for f in b_file if os.path.basename(f) not in deleted_basenames and f not in file_paths]
                if len(b['file']) > 0:
                    new_books.append(b)
            elif isinstance(b_file, str):
                if os.path.basename(b_file) not in deleted_basenames and b_file not in file_paths:
                    new_books.append(b)
        save_books(new_books)

    return jsonify({
        'success': True,
        'deleted_count': deleted_count,
        'total_freed_bytes': total_freed,
        'total_freed_formatted': format_file_size(total_freed),
        'errors': errors
    })


@app.route('/media_file/<media_id>/<path:filename>')
def serve_media_file(media_id, filename):
    """ Sirve un archivo de audio o video específico para series o música (soporta subidas locales y biblioteca) """
    start_time = request.args.get('t', default=0, type=float)
    
    # 1. Buscar en static/uploads/media_<media_id>/
    media_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"media_{media_id}")
    candidate = os.path.join(media_dir, filename)
    if os.path.exists(candidate) and os.path.isfile(candidate):
        ext = os.path.splitext(candidate)[1].lower()
        if ext in VIDEO_EXTS:
            return stream_video_file_pipeline(candidate, start_time)
        return send_from_directory(media_dir, filename, conditional=True)
    
    # 2. Buscar directamente en media_root si la ruta relativa coincide
    media_root = get_media_root()
    direct_media_p = os.path.join(media_root, filename)
    if os.path.exists(direct_media_p) and os.path.isfile(direct_media_p):
        ext = os.path.splitext(direct_media_p)[1].lower()
        if ext in VIDEO_EXTS:
            return stream_video_file_pipeline(direct_media_p, start_time)
        return send_from_directory(os.path.dirname(direct_media_p), os.path.basename(direct_media_p), conditional=True)

    # 3. Consultar la obra en el catálogo para resolver la ruta si solo vino el nombre base
    books = load_books()
    book = next((b for b in books if b.get('id') == media_id), None)
    if book and book.get('file'):
        file_val = book.get('file')
        if isinstance(file_val, list):
            for item_path in file_val:
                clean_item = item_path.replace('\\', '/')
                if os.path.basename(clean_item) == os.path.basename(filename) or clean_item == filename:
                    full_p = os.path.join(media_root, clean_item) if not os.path.isabs(clean_item) else clean_item
                    if os.path.exists(full_p):
                        ext = os.path.splitext(full_p)[1].lower()
                        if ext in VIDEO_EXTS:
                            return stream_video_file_pipeline(full_p, start_time)
                        return send_from_directory(os.path.dirname(full_p), os.path.basename(full_p), conditional=True)
        elif isinstance(file_val, str):
            clean_item = file_val.replace('\\', '/')
            full_p = os.path.join(media_root, clean_item) if not os.path.isabs(clean_item) else clean_item
            if os.path.exists(full_p):
                ext = os.path.splitext(full_p)[1].lower()
                if ext in VIDEO_EXTS:
                    return stream_video_file_pipeline(full_p, start_time)
                return send_from_directory(os.path.dirname(full_p), os.path.basename(full_p), conditional=True)

    return send_from_directory(media_dir, filename, conditional=True)

@app.route('/download/<path:filename>')
def download(filename):
    file_path = resolve_media_file_path(filename)
    if file_path and os.path.exists(file_path):
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), conditional=True)

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, conditional=True)


@app.route('/media_cover_raw/<path:relpath>')
def serve_media_cover_raw(relpath):
    """ Servir portadas detectadas directamente desde la carpeta de medios para previsualización """
    media_root = get_media_root()
    full_path = os.path.join(media_root, relpath)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
    return ('', 404)

@app.route('/cache_file/<book_id>/<path:filename>')
def serve_cache_file(book_id, filename):
    """ Servir imágenes descomprimidas soportando subcarpetas anidadas (<path:filename>) """
    cache_dir = os.path.join(app.config['CACHE_FOLDER'], book_id)
    clean_fn = urllib.parse.unquote(filename)
    if os.path.exists(os.path.join(cache_dir, clean_fn)):
        return send_from_directory(cache_dir, clean_fn)
    return send_from_directory(cache_dir, filename)

# ----------------- RUTAS ADMIN -----------------

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    config = load_config()
    
    if request.method == 'POST' and 'login_pass' in request.form:
        if request.form.get('login_pass') == config.get('admin_pass'):
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash("Contraseña incorrecta", "error")

    if not session.get('logged_in'):
        return render_template('login.html')

    books = load_books()
    
    # Calcular cantidades por tipo de contenido
    type_counts = {'book': 0, 'movie': 0, 'series': 0, 'music': 0, 'anime': 0, 'manga': 0}
    for b in books:
        t = b.get('type', 'book')
        if t in type_counts:
            type_counts[t] += 1
            
    # Calcular cantidades por categoría
    category_counts = {}
    for b in books:
        cats = b.get('category', '')
        if cats:
            for cat in cats.split(','):
                clean_cat = cat.strip()
                if clean_cat:
                    clean_cat = clean_cat.capitalize()
                    category_counts[clean_cat] = category_counts.get(clean_cat, 0) + 1

    disk = get_disk_status()
    random_nfc = generate_nfc_key()
    
    return render_template('admin.html', 
                           books=books, 
                           config=config, 
                           disk=disk, 
                           random_nfc=random_nfc,
                           type_counts=type_counts,
                           category_counts=category_counts)

@app.route('/admin/batch')
def batch_upload_view():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    return render_template('batch_upload.html')

@app.route('/admin/folder-import')
def folder_import_view():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    return render_template('folder_import.html')

def save_media_cover(unique_id, cover_file, media_files, default_prefix="cover"):
    """
    Guarda la portada subida o la extrae automáticamente de archivos de audio (Opus, MP3, FLAC, OGG, etc.)
    Retorna el nombre del archivo de portada guardado (e.g. cover_12345678.jpg / .svg).
    """
    # 1. Si se envió un archivo de portada explícito
    if cover_file and getattr(cover_file, 'filename', None) and cover_file.filename.strip():
        ext_cover = os.path.splitext(cover_file.filename)[1].lower() or '.jpg'
        cover_filename = f"{default_prefix}_{unique_id}{ext_cover}"
        cover_file.save(os.path.join(app.config['COVER_FOLDER'], cover_filename))
        return cover_filename

    # 2. Intentar extraer portada incrustada de los archivos multimedia (audio/opus/flac/mp3/etc.)
    if media_files:
        for f in media_files:
            if not f or not getattr(f, 'filename', None):
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in AUDIO_EXTS:
                try:
                    tags, pic_bytes, pic_mime = extract_audio_embedded_metadata(f)
                    if hasattr(f, 'seek'):
                        f.seek(0)
                    if pic_bytes:
                        ext_pic = '.png' if 'png' in pic_mime.lower() else ('.webp' if 'webp' in pic_mime.lower() else '.jpg')
                        cover_filename = f"{default_prefix}_{unique_id}{ext_pic}"
                        with open(os.path.join(app.config['COVER_FOLDER'], cover_filename), 'wb') as cov_out:
                            cov_out.write(pic_bytes)
                        return cover_filename
                except Exception:
                    if hasattr(f, 'seek'):
                        f.seek(0)
                    pass

    # 3. Portada genérica estilizada si no se encontró ninguna
    cover_filename = f"{default_prefix}_{unique_id}.svg"
    dest_path = os.path.join(app.config['COVER_FOLDER'], cover_filename)
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
        <defs>
            <linearGradient id="g_{unique_id}" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#0f172a"/>
                <stop offset="100%" stop-color="#1e293b"/>
            </linearGradient>
        </defs>
        <rect width="400" height="400" fill="url(#g_{unique_id})"/>
        <circle cx="200" cy="180" r="60" fill="rgba(0, 242, 254, 0.15)" stroke="#00f2fe" stroke-width="3"/>
        <text x="200" y="195" font-family="sans-serif" font-size="36" fill="#00f2fe" text-anchor="middle">🎵</text>
        <text x="200" y="280" font-family="sans-serif" font-size="16" font-weight="bold" fill="#f3f4f6" text-anchor="middle">Audio TapBox</text>
    </svg>'''
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    return cover_filename

@app.route('/api/extract-audio-metadata', methods=['POST'])
def api_extract_audio_metadata():
    """ Extrae metadatos y portada incrustada de un archivo de audio (Opus, MP3, FLAC, etc.) para autocompletar en el frontend """
    audio_file = request.files.get('file') or request.files.get('audio')
    if not audio_file:
        return jsonify({"success": False, "error": "No se envió ningún archivo de audio"}), 400

    try:
        tags, pic_bytes, pic_mime = extract_audio_embedded_metadata(audio_file)
        cover_data_url = None
        if pic_bytes:
            b64_img = base64.b64encode(pic_bytes).decode('utf-8')
            cover_data_url = f"data:{pic_mime};base64,{b64_img}"

        return jsonify({
            "success": True,
            "filename": audio_file.filename,
            "title": tags.get('TITLE', ''),
            "artist": tags.get('ARTIST', '') or tags.get('PERFORMER', '') or tags.get('ALBUMARTIST', ''),
            "album": tags.get('ALBUM', ''),
            "genre": tags.get('GENRE', ''),
            "has_cover": pic_bytes is not None,
            "cover_data_url": cover_data_url,
            "cover_mime": pic_mime
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/batch-upload', methods=['POST'])
def batch_upload_process():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))

    titles = request.form.getlist('title[]')
    authors = request.form.getlist('author[]')
    sagas = request.form.getlist('saga[]')
    nfc_keys = request.form.getlist('nfc_key[]')
    synopses = request.form.getlist('synopsis[]')
    types = request.form.getlist('type[]')
    covers = request.files.getlist('cover[]')

    books = load_books()
    added_count = 0

    for i in range(len(titles)):
        title = titles[i].strip() if i < len(titles) else ''
        author = authors[i].strip() if i < len(authors) else ''
        saga = sagas[i].strip() if i < len(sagas) else ''
        nfc_key = nfc_keys[i].strip().upper() if i < len(nfc_keys) and nfc_keys[i].strip() else generate_nfc_key()
        synopsis = synopses[i].strip() if i < len(synopses) and synopses[i].strip() else "Sin sinopsis disponible."
        media_type = types[i].strip() if i < len(types) else 'book'
        cover_file = covers[i] if i < len(covers) else None
        
        # Obtener archivos correspondientes a esta tarjeta en base a su índice i
        card_files = request.files.getlist(f'file_{i}[]')

        if (title or (card_files and len(card_files) > 0 and card_files[0].filename != '')) and card_files and len(card_files) > 0 and card_files[0].filename != '':
            unique_id = str(uuid.uuid4())[:8]

            # Autodetección de metadatos si vienen vacíos en audio
            if media_type == 'music' and card_files:
                for f in card_files:
                    if f and f.filename and os.path.splitext(f.filename)[1].lower() in AUDIO_EXTS:
                        t_tags, _, _ = extract_audio_embedded_metadata(f)
                        if hasattr(f, 'seek'):
                            f.seek(0)
                        if not title and t_tags.get('TITLE'):
                            title = t_tags['TITLE']
                        if not author and (t_tags.get('ARTIST') or t_tags.get('PERFORMER')):
                            author = t_tags.get('ARTIST') or t_tags.get('PERFORMER')
                        if not saga and t_tags.get('ALBUM'):
                            saga = t_tags['ALBUM']
                        break

            if not title:
                title = os.path.splitext(os.path.basename(card_files[0].filename))[0]

            cover_filename = save_media_cover(unique_id, cover_file, card_files)

            if media_type in ['book', 'manga', 'movie']:
                # Archivo único
                first_file = card_files[0]
                ext_file = os.path.splitext(first_file.filename)[1]
                book_filename = f"doc_{unique_id}{ext_file}"
                first_file.save(os.path.join(app.config['UPLOAD_FOLDER'], book_filename))
                file_val = book_filename
            else:
                # Múltiples archivos (series, música)
                saved_filenames = []
                media_subfolder = f"media_{unique_id}"
                media_path = os.path.join(app.config['UPLOAD_FOLDER'], media_subfolder)
                os.makedirs(media_path, exist_ok=True)
                for f in card_files:
                    if f and f.filename:
                        secure_name = os.path.basename(f.filename)
                        f.save(os.path.join(media_path, secure_name))
                        saved_filenames.append(secure_name)
                file_val = saved_filenames

            books.append({
                'id': unique_id,
                'title': title,
                'type': media_type,
                'author': author,
                'saga': saga,
                'nfc_key': nfc_key,
                'synopsis': synopsis,
                'cover': cover_filename,
                'file': file_val
            })
            added_count += 1

    if added_count > 0:
        save_books(books)
        flash(f"¡Se han registrado {added_count} obras exitosamente!", "success")
    else:
        flash("No se pudo registrar ninguna obra. Verifica los archivos.", "error")

    return redirect(url_for('admin'))

@app.route('/admin/folder-upload-api', methods=['POST'])
def folder_upload_api():
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401

    title = request.form.get('title', '').strip()
    media_type = request.form.get('type', 'book').strip()
    author = request.form.get('author', '').strip()
    saga = request.form.get('saga', '').strip()
    category = request.form.get('category', '').strip() or request.form.get('genre', '').strip()
    nfc_key = request.form.get('nfc_key', '').strip().upper()
    if not nfc_key:
        nfc_key = generate_nfc_key()
    synopsis = request.form.get('synopsis', '').strip() or "Sin sinopsis disponible."
    
    cover_file = request.files.get('cover')
    uploaded_files = request.files.getlist('files[]')

    if not uploaded_files or len(uploaded_files) == 0 or uploaded_files[0].filename == '':
        return jsonify({"success": False, "error": "Falta el archivo de contenido"}), 400

    if not title:
        title = os.path.splitext(os.path.basename(uploaded_files[0].filename))[0]

    try:
        unique_id = str(uuid.uuid4())[:8]
        cover_filename = save_media_cover(unique_id, cover_file, uploaded_files)

        if media_type in ['book', 'manga', 'movie']:
            # Archivo único
            first_file = uploaded_files[0]
            ext_file = os.path.splitext(first_file.filename)[1]
            book_filename = f"doc_{unique_id}{ext_file}"
            first_file.save(os.path.join(app.config['UPLOAD_FOLDER'], book_filename))
            file_val = book_filename
        else:
            # Múltiples archivos (series, música)
            saved_filenames = []
            media_subfolder = f"media_{unique_id}"
            media_path = os.path.join(app.config['UPLOAD_FOLDER'], media_subfolder)
            os.makedirs(media_path, exist_ok=True)
            for f in uploaded_files:
                if f and f.filename:
                    secure_name = os.path.basename(f.filename)
                    f.save(os.path.join(media_path, secure_name))
                    saved_filenames.append(secure_name)
            file_val = saved_filenames

        books = load_books()
        books.append({
            'id': unique_id,
            'title': title,
            'type': media_type,
            'author': author,
            'saga': saga,
            'category': category,
            'nfc_key': nfc_key,
            'synopsis': synopsis,
            'cover': cover_filename,
            'file': file_val
        })
        save_books(books)
        return jsonify({"success": True, "title": title, "nfc_key": nfc_key})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/upload', methods=['POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))

    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    saga = request.form.get('saga', '').strip()
    nfc_key = request.form.get('nfc_key', '').strip().upper()
    if not nfc_key:
        nfc_key = generate_nfc_key()

    synopsis = request.form.get('synopsis', '').strip()
    media_type = request.form.get('type', 'book')
    cover_file = request.files.get('cover')
    uploaded_files = request.files.getlist('file')

    if uploaded_files and len(uploaded_files) > 0 and uploaded_files[0].filename != '':
        if not title:
            title = os.path.splitext(os.path.basename(uploaded_files[0].filename))[0]

        unique_id = str(uuid.uuid4())[:8]
        cover_filename = save_media_cover(unique_id, cover_file, uploaded_files)

        if media_type in ['book', 'manga', 'movie']:
            # Archivo único
            first_file = uploaded_files[0]
            ext_file = os.path.splitext(first_file.filename)[1]
            book_filename = f"doc_{unique_id}{ext_file}"
            first_file.save(os.path.join(app.config['UPLOAD_FOLDER'], book_filename))
            file_val = book_filename
        else:
            saved_filenames = []
            media_subfolder = f"media_{unique_id}"
            media_path = os.path.join(app.config['UPLOAD_FOLDER'], media_subfolder)
            os.makedirs(media_path, exist_ok=True)
            for f in uploaded_files:
                if f and f.filename:
                    secure_name = os.path.basename(f.filename)
                    f.save(os.path.join(media_path, secure_name))
                    saved_filenames.append(secure_name)
            file_val = saved_filenames

        books = load_books()
        books.append({
            'id': unique_id,
            'title': title,
            'type': media_type,
            'author': author,
            'saga': saga,
            'nfc_key': nfc_key,
            'synopsis': synopsis if synopsis else "Sin sinopsis disponible.",
            'cover': cover_filename,
            'file': file_val
        })
        save_books(books)
        flash(f"Obra registrada correctamente con la llave NFC: {nfc_key}", "success")

    return redirect(url_for('admin'))

@app.route('/admin/change-pass', methods=['POST'])
def change_pass():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    
    new_pass = request.form.get('new_pass', '').strip()
    if new_pass:
        config = load_config()
        config['admin_pass'] = new_pass
        save_config(config)
        flash("Contraseña cambiada exitosamente", "success")
    else:
        flash("La contraseña no puede estar vacía", "error")
    
    return redirect(url_for('admin'))

@app.route('/admin/delete/<book_id>')
def delete_book(book_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    
    books = load_books()
    book_to_delete = next((b for b in books if b.get('id') == book_id), None)

    if book_to_delete:
        try:
            cover_path = os.path.join(app.config['COVER_FOLDER'], book_to_delete['cover'])
            file_val = book_to_delete.get('file')
            
            if isinstance(file_val, list):
                media_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"media_{book_id}")
                if os.path.exists(media_dir):
                    shutil.rmtree(media_dir, ignore_errors=True)
            else:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_val)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            cache_dir = os.path.join(app.config['CACHE_FOLDER'], book_id)

            if os.path.exists(cover_path): os.remove(cover_path)
            if os.path.exists(cache_dir): shutil.rmtree(cache_dir, ignore_errors=True)
        except Exception:
            pass

        books = [b for b in books if b.get('id') != book_id]
        save_books(books)
        flash("Obra eliminada y espacio liberado", "success")
        
    return redirect(url_for('admin'))

@app.route('/admin/get-book/<book_id>')
def get_book_details(book_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    books = load_books()
    book = next((b for b in books if b.get('id') == book_id), None)
    if not book:
        return jsonify({'error': 'Obra no encontrada'}), 404
        
    return jsonify({
        'id': book.get('id'),
        'title': book.get('title'),
        'type': book.get('type', 'book'),
        'author': book.get('author', ''),
        'saga': book.get('saga', ''),
        'category': book.get('category', ''),
        'nfc_key': book.get('nfc_key', ''),
        'synopsis': book.get('synopsis', '')
    })

@app.route('/admin/edit/<book_id>', methods=['POST'])
def edit_book(book_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
        
    books = load_books()
    book_idx = next((i for i, b in enumerate(books) if b.get('id') == book_id), None)
    
    if book_idx is not None:
        books[book_idx]['title'] = request.form.get('title', '').strip()
        books[book_idx]['type'] = request.form.get('type', 'book').strip()
        books[book_idx]['author'] = request.form.get('author', '').strip()
        books[book_idx]['saga'] = request.form.get('saga', '').strip()
        books[book_idx]['category'] = request.form.get('category', '').strip()
        books[book_idx]['nfc_key'] = request.form.get('nfc_key', '').strip().upper()
        books[book_idx]['synopsis'] = request.form.get('synopsis', '').strip()
        
        # Opciones de visualización en Galería y Saga
        show_in_gal = request.form.get('show_in_gallery')
        books[book_idx]['show_in_gallery'] = (show_in_gal != '0' and show_in_gal != 'false' and show_in_gal is not None)
        
        is_cover = request.form.get('is_saga_cover') in ['1', 'true', 'on']
        books[book_idx]['is_saga_cover'] = is_cover
        
        random_cover = request.form.get('saga_random_cover') in ['1', 'true', 'on']
        books[book_idx]['saga_random_cover'] = random_cover
        
        # Si la obra pertenece a una saga, sincronizar opciones con los demás tomos
        current_saga = books[book_idx].get('saga', '').strip()
        if current_saga:
            for b in books:
                if b.get('saga', '').strip().lower() == current_saga.lower():
                    b['saga_random_cover'] = random_cover
                    if is_cover and b.get('id') != book_id:
                        b['is_saga_cover'] = False
        
        # Portada opcional
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            # Eliminar vieja si existe
            old_cover = books[book_idx].get('cover')
            if old_cover:
                old_cover_path = os.path.join(app.config['COVER_FOLDER'], old_cover)
                if os.path.exists(old_cover_path):
                    try: os.remove(old_cover_path)
                    except Exception: pass
            
            ext = os.path.splitext(cover_file.filename)[1]
            new_cover_name = f"{book_id}{ext}"
            cover_path = os.path.join(app.config['COVER_FOLDER'], new_cover_name)
            cover_file.save(cover_path)
            books[book_idx]['cover'] = new_cover_name
            
        # Archivos opcionales
        new_files = request.files.getlist('files[]')
        if not new_files or (len(new_files) == 1 and new_files[0].filename == ''):
            single_file = request.files.get('file')
            if single_file and single_file.filename:
                new_files = [single_file]
            else:
                new_files = []
                
        if new_files and len(new_files) > 0 and new_files[0].filename != '':
            media_type = books[book_idx]['type']
            
            # Borrar archivos anteriores
            old_file_val = books[book_idx].get('file')
            if old_file_val:
                try:
                    if isinstance(old_file_val, list):
                        media_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"media_{book_id}")
                        if os.path.exists(media_dir):
                            shutil.rmtree(media_dir, ignore_errors=True)
                    else:
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], old_file_val)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                except Exception:
                    pass
            
            # Guardar nuevos archivos
            if media_type in ['book', 'manga', 'movie']:
                f = new_files[0]
                ext = os.path.splitext(f.filename)[1]
                filename = f"{book_id}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(filepath)
                books[book_idx]['file'] = filename
                
                if media_type in ['book', 'manga']:
                    cache_dir = os.path.join(app.config['CACHE_FOLDER'], book_id)
                    if os.path.exists(cache_dir):
                        shutil.rmtree(cache_dir, ignore_errors=True)
                    extract_cbr_pages(book_id, filepath)
            else:
                # Series, Anime, Música
                media_path = os.path.join(app.config['UPLOAD_FOLDER'], f"media_{book_id}")
                os.makedirs(media_path, exist_ok=True)
                saved_filenames = []
                for f in new_files:
                    if f and f.filename:
                        secure_name = os.path.basename(f.filename)
                        f.save(os.path.join(media_path, secure_name))
                        saved_filenames.append(f"media_{book_id}/{secure_name}")
                books[book_idx]['file'] = saved_filenames

        save_books(books)
        flash("Obra modificada correctamente", "success")
        
    return redirect(url_for('book_detail', book_id=book_id))

# ----------------- RUTAS DE SINCRONIZACIÓN DE BIBLIOTECA (DESCARGAS) -----------------

@app.route('/admin/library-sync')
def library_sync():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    config = load_config()
    media_root = get_media_root()
    scan_data = scan_media_library()
    return render_template('library_sync.html', 
                           config=config, 
                           media_root=media_root, 
                           movies=scan_data['movies'], 
                           series=scan_data['series'], 
                           stats=scan_data['stats'])

@app.route('/admin/api/library-scan', methods=['GET', 'POST'])
def api_library_scan():
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    scan_data = scan_media_library()
    return jsonify({"success": True, **scan_data})

@app.route('/admin/api/library-import', methods=['POST'])
def api_library_import():
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({"success": False, "error": "No se seleccionó ninguna obra para importar"}), 400

    media_root = get_media_root()
    books = load_books()
    imported_count = 0
    imported_titles = []

    for item in items:
        title = item.get('title', '').strip()
        m_type = item.get('type', 'movie') # 'movie' or 'series'
        file_val = item.get('file') or item.get('files')
        cover_rel = item.get('cover_rel')
        nfc_key = item.get('nfc_key', '').strip() or generate_nfc_key()
        category = item.get('category', 'Película' if m_type == 'movie' else 'Serie').strip()
        saga = item.get('saga', title if m_type == 'series' else '').strip()
        author = item.get('author', '').strip()
        synopsis = item.get('synopsis', f"Importado desde la biblioteca de {m_type}s.").strip()

        if not title or not file_val:
            continue

        unique_id = str(uuid.uuid4())[:8]

        # Portada: Descargar remota (TMDB/Radarr/Sonarr) si existe, o copiar local, o generar SVG
        cover_filename = f"cover_{unique_id}.jpg"
        cover_saved = False
        poster_remote = item.get('poster_remote_url')
        if poster_remote and (poster_remote.startswith('http://') or poster_remote.startswith('https://')):
            cover_saved = download_image_to_file(poster_remote, os.path.join(app.config['COVER_FOLDER'], cover_filename))
        
        if not cover_saved and cover_rel and os.path.exists(os.path.join(media_root, cover_rel)):
            src_cover = os.path.join(media_root, cover_rel)
            ext = os.path.splitext(src_cover)[1].lower() or '.jpg'
            cover_filename = f"cover_{unique_id}{ext}"
            shutil.copy2(src_cover, os.path.join(app.config['COVER_FOLDER'], cover_filename))
            cover_saved = True

        if not cover_saved:
            svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600">
                <defs>
                    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#0f172a"/>
                        <stop offset="100%" stop-color="#1e293b"/>
                    </linearGradient>
                </defs>
                <rect width="400" height="600" fill="url(#g)"/>
                <circle cx="200" cy="240" r="60" fill="rgba(0, 245, 212, 0.15)" stroke="#00f5d4" stroke-width="3"/>
                <text x="200" y="248" font-family="sans-serif" font-size="28" fill="#00f5d4" text-anchor="middle">{"🎬" if m_type == "movie" else "📺"}</text>
                <text x="200" y="360" font-family="sans-serif" font-size="20" font-weight="bold" fill="#ffffff" text-anchor="middle">{title[:28]}</text>
                <text x="200" y="390" font-family="sans-serif" font-size="14" fill="#94a3b8" text-anchor="middle">{category.upper()}</text>
            </svg>'''
            cover_filename = f"cover_{unique_id}.svg"
            with open(os.path.join(app.config['COVER_FOLDER'], cover_filename), 'w', encoding='utf-8') as f:
                f.write(svg_content)

        new_book = {
            'id': unique_id,
            'title': title,
            'type': m_type,
            'author': author,
            'saga': saga,
            'category': category,
            'nfc_key': nfc_key,
            'synopsis': synopsis,
            'cover': cover_filename,
            'file': file_val,
            'storage': 'media_library'
        }
        books.append(new_book)
        imported_count += 1
        imported_titles.append(title)

    if imported_count > 0:
        save_books(books)
        return jsonify({"success": True, "count": imported_count, "titles": imported_titles})
    else:
        return jsonify({"success": False, "error": "No se pudo importar ninguna obra"}), 400

@app.route('/admin/api/sync-all-metadata', methods=['POST'])
def api_sync_all_metadata():
    """Actualiza metadatos, sinopsis oficial y portadas desde Radarr y Sonarr para obras existentes"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    
    radarr_movies = get_radarr_movies()
    sonarr_series_list = get_sonarr_series()
    books = load_books()
    updated_count = 0

    for b in books:
        m_type = b.get('type')
        title = b.get('title', '')
        file_val = b.get('file', '')
        
        if m_type == 'movie' and radarr_movies:
            r_match = find_radarr_match(title, str(file_val), radarr_movies)
            if r_match:
                if r_match.get('overview'):
                    b['synopsis'] = r_match.get('overview')
                if r_match.get('genres'):
                    b['category'] = ", ".join(r_match.get('genres'))
                if r_match.get('studio'):
                    b['author'] = r_match.get('studio')
                
                # Descargar portada real si no la tiene o si es un cover SVG
                current_cover = str(b.get('cover', ''))
                for img in r_match.get('images', []):
                    if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                        cover_fn = f"cover_{b['id']}.jpg"
                        dest = os.path.join(app.config['COVER_FOLDER'], cover_fn)
                        if download_image_to_file(img['remoteUrl'], dest):
                            b['cover'] = cover_fn
                        break
                updated_count += 1
                
        elif m_type in ['series', 'anime'] and sonarr_series_list:
            s_match = find_sonarr_match(b.get('saga') or title, sonarr_series_list)
            if s_match:
                if s_match.get('overview'):
                    b['synopsis'] = s_match.get('overview')
                if s_match.get('genres'):
                    b['category'] = ", ".join(s_match.get('genres'))
                if s_match.get('network'):
                    b['author'] = s_match.get('network')
                
                for img in s_match.get('images', []):
                    if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                        cover_fn = f"cover_{b['id']}.jpg"
                        dest = os.path.join(app.config['COVER_FOLDER'], cover_fn)
                        if download_image_to_file(img['remoteUrl'], dest):
                            b['cover'] = cover_fn
                        break
                updated_count += 1

    if updated_count > 0:
        save_books(books)
        return jsonify({"success": True, "count": updated_count})
    return jsonify({"success": True, "count": 0, "message": "No se encontraron obras para actualizar"})

@app.route('/admin/api/sync-book-metadata/<book_id>', methods=['POST'])
def api_sync_single_book_metadata(book_id):
    """Actualiza metadatos y portada de una obra específica desde Radarr/Sonarr"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    
    books = load_books()
    book = next((b for b in books if b.get('id') == book_id), None)
    if not book:
        return jsonify({"success": False, "error": "Obra no encontrada"}), 404

    m_type = book.get('type')
    title = book.get('title', '')
    file_val = book.get('file', '')
    updated = False

    if m_type == 'movie':
        radarr_movies = get_radarr_movies()
        r_match = find_radarr_match(title, str(file_val), radarr_movies)
        if r_match:
            if r_match.get('overview'):
                book['synopsis'] = r_match.get('overview')
            if r_match.get('genres'):
                book['category'] = ", ".join(r_match.get('genres'))
            if r_match.get('studio'):
                book['author'] = r_match.get('studio')
            
            for img in r_match.get('images', []):
                if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                    cover_fn = f"cover_{book['id']}.jpg"
                    dest = os.path.join(app.config['COVER_FOLDER'], cover_fn)
                    if download_image_to_file(img['remoteUrl'], dest):
                        book['cover'] = cover_fn
                    break
            updated = True

    elif m_type in ['series', 'anime']:
        sonarr_series_list = get_sonarr_series()
        s_match = find_sonarr_match(book.get('saga') or title, sonarr_series_list)
        if s_match:
            if s_match.get('overview'):
                book['synopsis'] = s_match.get('overview')
            if s_match.get('genres'):
                book['category'] = ", ".join(s_match.get('genres'))
            if s_match.get('network'):
                book['author'] = s_match.get('network')
            
            for img in s_match.get('images', []):
                if img.get('coverType') == 'poster' and img.get('remoteUrl'):
                    cover_fn = f"cover_{book['id']}.jpg"
                    dest = os.path.join(app.config['COVER_FOLDER'], cover_fn)
                    if download_image_to_file(img['remoteUrl'], dest):
                        book['cover'] = cover_fn
                    break
            updated = True

    if updated:
        save_books(books)
        return jsonify({"success": True, "book": book})
    return jsonify({"success": False, "error": "No se encontró coincidencia en Radarr/Sonarr"}), 404

@app.route('/admin/api/save-media-root', methods=['POST'])
def api_save_media_root():
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "No autorizado"}), 401
    new_root = request.form.get('media_root', '').strip()
    if not new_root:
        return jsonify({"success": False, "error": "Ruta inválida"}), 400
    
    config = load_config()
    config['media_root'] = new_root
    save_config(config)
    
    os.makedirs(os.path.join(new_root, 'movies'), exist_ok=True)
    os.makedirs(os.path.join(new_root, 'series'), exist_ok=True)
    
    return jsonify({"success": True, "media_root": new_root})

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)