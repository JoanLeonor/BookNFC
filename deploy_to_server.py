import os
import sys
import json
import time
import shutil
import paramiko

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = "192.168.0.238"
USER = "joanml"
PASS = "joanml"
REMOTE_BASE = "/home/joanml/tapbox"
LOCAL_BASE = os.path.dirname(os.path.abspath(__file__))

print("==========================================")
print(f"SINCRONIZADOR & DESPLIEGUE SEGURO TAPBOX -> {HOST}")
print("==========================================")
print(f"Conectando a {USER}@{HOST} via SSH...")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(HOST, port=22, username=USER, password=PASS, timeout=10)
    print("Conexion SSH establecida.")
except Exception as e:
    print(f"Error al conectar por SSH: {e}")
    sys.exit(1)

sftp = ssh.open_sftp()

def ensure_remote_dir(remote_dir):
    dirs = []
    p = remote_dir
    while len(p) > 1 and p != "/":
        dirs.append(p)
        p = os.path.dirname(p)
    while len(dirs):
        d = dirs.pop()
        try:
            sftp.stat(d)
        except IOError:
            try:
                sftp.mkdir(d)
            except Exception:
                pass

def sync_single_file(local_path, remote_path):
    if not os.path.exists(local_path):
        return
    ensure_remote_dir(os.path.dirname(remote_path))
    try:
        try:
            r_stat = sftp.stat(remote_path)
            l_stat = os.stat(local_path)
            if r_stat.st_size == l_stat.st_size:
                return # Skip identical file
        except IOError:
            pass
        sftp.put(local_path, remote_path)
        print(f"  -> {os.path.basename(local_path)}")
    except Exception as e:
        print(f"  Error subiendo {local_path}: {e}")

# ---------------------------------------------------------
# FUSIÓN INTELIGENTE BIDIRECCIONAL DE CATÁLOGO (PROTECCIÓN TOTAL)
# ---------------------------------------------------------
print("\n1. Verificando y fusionando catalogo de forma bidireccional...")
local_catalog_file = os.path.join(LOCAL_BASE, 'catalog.json')
remote_catalog_file = f"{REMOTE_BASE}/catalog.json"

local_catalog = []
if os.path.exists(local_catalog_file):
    try:
        with open(local_catalog_file, 'r', encoding='utf-8') as f:
            local_catalog = json.load(f)
    except Exception as e:
        print(f"  Aviso leyendo catalogo local: {e}")

remote_catalog = []
try:
    with sftp.open(remote_catalog_file, 'r') as f:
        remote_catalog = json.load(f)
except Exception:
    pass

def is_obra_dummy(item):
    if not isinstance(item, dict):
        return False
    t = str(item.get('title', '')).strip()
    s = str(item.get('saga', '')).strip()
    import re
    return bool(re.match(r'^Obra\s+[0-9a-fA-F]{8}$', t, re.IGNORECASE) or s == 'Recuperados')

# Fusión por ID (excluyendo registros huérfanos/duplicados 'Obra XXXXXXXX')
items_map = {}
for item in remote_catalog:
    if isinstance(item, dict) and item.get('id') and not is_obra_dummy(item):
        items_map[item['id']] = item

for item in local_catalog:
    if isinstance(item, dict) and item.get('id') and not is_obra_dummy(item):
        items_map[item['id']] = item

merged_catalog = list(items_map.values())
print(f"  Catalogo fusionado y limpiado: {len(merged_catalog)} obras reales (Local: {len(local_catalog)}, Servidor: {len(remote_catalog)})")

# Guardar catalogo fusionado tanto en local como en remoto
with open(local_catalog_file, 'w', encoding='utf-8') as f:
    json.dump(merged_catalog, f, indent=4, ensure_ascii=False)

# Crear snapshot de respaldo con fecha en local y servidor
timestamp = time.strftime('%Y%m%d_%H%M%S')
local_backup_dir = os.path.join(LOCAL_BASE, 'backups')
os.makedirs(local_backup_dir, exist_ok=True)
shutil.copy2(local_catalog_file, os.path.join(local_backup_dir, f'catalog_snapshot_{timestamp}.json'))

sftp.put(local_catalog_file, remote_catalog_file)
print("  -> catalog.json sincronizado atomicamente y protegido en ambos extremos.")

# 2. Sincronizar scripts principales
print("\n2. Sincronizando scripts principales...")
for f in ["app.py", "db.py", "config.json", "migrate_json_to_postgres.py", "AGENTS.md", "notas.md"]:
    l_path = os.path.join(LOCAL_BASE, f)
    r_path = f"{REMOTE_BASE}/{f}"
    sync_single_file(l_path, r_path)

# Limpiar archivos viejos si existen
for old_f in [f"{REMOTE_BASE}/unifier_engine.py", f"{REMOTE_BASE}/templates/unifier.html"]:
    try:
        sftp.remove(old_f)
    except IOError:
        pass

# 3. Sincronizar plantillas
print("\n3. Sincronizando plantillas HTML...")
tpl_dir = os.path.join(LOCAL_BASE, "templates")
if os.path.exists(tpl_dir):
    for f in os.listdir(tpl_dir):
        if f.endswith(".html"):
            sync_single_file(os.path.join(tpl_dir, f), f"{REMOTE_BASE}/templates/{f}")

# 4. Sincronizar portadas
print("\n4. Sincronizando portadas...")
cov_dir = os.path.join(LOCAL_BASE, "static", "covers")
if os.path.exists(cov_dir):
    for f in os.listdir(cov_dir):
        sync_single_file(os.path.join(cov_dir, f), f"{REMOTE_BASE}/static/covers/{f}")

# 5. Sincronizar subidas multimedia
print("\n5. Sincronizando archivos multimedia subidos...")
uploads_dir = os.path.join(LOCAL_BASE, "static", "uploads")
if os.path.exists(uploads_dir):
    for root, dirs, files in os.walk(uploads_dir):
        for f in files:
            full_local = os.path.join(root, f)
            rel_path = os.path.relpath(full_local, LOCAL_BASE).replace("\\", "/")
            full_remote = f"{REMOTE_BASE}/{rel_path}"
            sync_single_file(full_local, full_remote)

# 6. Sincronizar plantillas QR de categorías
print("\n6. Sincronizando plantillas QR de categorías...")
qr_tpl_dir = os.path.join(LOCAL_BASE, "static", "qr_templates")
if os.path.exists(qr_tpl_dir):
    for f in os.listdir(qr_tpl_dir):
        sync_single_file(os.path.join(qr_tpl_dir, f), f"{REMOTE_BASE}/static/qr_templates/{f}")

sftp.close()

# 7. Verificar/instalar dependencias (qrcode, psycopg2) en el servidor y limpiar cache de QR
print("\n7. Verificando dependencias Python (qrcode, psycopg2) en el servidor...")
stdin, stdout, stderr = ssh.exec_command(f"{REMOTE_BASE}/venv/bin/python -c 'import qrcode, psycopg2' 2>/dev/null || {REMOTE_BASE}/venv/bin/pip install qrcode psycopg2-binary")
out = stdout.read().decode('utf-8', errors='ignore').strip()
print(f"  Dependencias: {out or 'OK'}")

# Limpiar cache de QR para regenerar con nuevos ajustes
stdin, stdout, stderr = ssh.exec_command(f"rm -rf {REMOTE_BASE}/static/cache/qr_covers/*")
stdout.read()

# 8. Reiniciar servicio TapBox en el servidor
print("\n8. Reiniciando servicio TapBox en el servidor...")
stdin, stdout, stderr = ssh.exec_command(f"echo {PASS} | sudo -S systemctl restart tapbox")
stdout.read()

time.sleep(1)
stdin, stdout, stderr = ssh.exec_command("sudo systemctl is-active tapbox")
status = stdout.read().decode('utf-8', errors='ignore').strip()
print(f"Estado del servicio: {status}")

# 9. Verificar salud HTTP
print(f"\n9. Verificando salud HTTP (http://{HOST}:5000)...")
try:
    import urllib.request
    req = urllib.request.urlopen(f"http://{HOST}:5000", timeout=5)
    print(f"  Respuesta HTTP: {req.status} OK")
except Exception as e:
    print(f"  Aviso verificando HTTP: {e}")

ssh.close()
print("\nDespliegue y sincronizacion finalizada con exito!")

