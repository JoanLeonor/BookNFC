import os
import sys
import paramiko

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = "192.168.0.11"
USER = "joanml"
PASS = "joanml"
REMOTE_BASE = "/home/joanml/tapbox"
LOCAL_BASE = os.path.dirname(os.path.abspath(__file__))

print("==========================================")
print(f"SINCRONIZADOR & DESPLIEGUE TAPBOX -> {HOST}")
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
        # Check size / mtime if exists to avoid uploading identical large files
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

# 1. Sincronizar archivos raiz
print("\n1. Sincronizando scripts principales y catalogo...")
for f in ["app.py", "catalog.json", "config.json", "AGENTS.md", "notas.md"]:
    l_path = os.path.join(LOCAL_BASE, f)
    r_path = f"{REMOTE_BASE}/{f}"
    sync_single_file(l_path, r_path)

# 2. Sincronizar plantillas
print("\n2. Sincronizando plantillas HTML...")
tpl_dir = os.path.join(LOCAL_BASE, "templates")
if os.path.exists(tpl_dir):
    for f in os.listdir(tpl_dir):
        if f.endswith(".html"):
            sync_single_file(os.path.join(tpl_dir, f), f"{REMOTE_BASE}/templates/{f}")

# 3. Sincronizar portadas
print("\n3. Sincronizando portadas...")
cov_dir = os.path.join(LOCAL_BASE, "static", "covers")
if os.path.exists(cov_dir):
    for f in os.listdir(cov_dir):
        sync_single_file(os.path.join(cov_dir, f), f"{REMOTE_BASE}/static/covers/{f}")

# 4. Sincronizar subidas multimedia (CBRs, musica, etc.)
print("\n4. Sincronizando archivos multimedia subidos...")
uploads_dir = os.path.join(LOCAL_BASE, "static", "uploads")
if os.path.exists(uploads_dir):
    for root, dirs, files in os.walk(uploads_dir):
        for f in files:
            full_local = os.path.join(root, f)
            rel_path = os.path.relpath(full_local, LOCAL_BASE).replace("\\", "/")
            full_remote = f"{REMOTE_BASE}/{rel_path}"
            sync_single_file(full_local, full_remote)

sftp.close()

# 5. Reiniciar servicio TapBox en el servidor
print("\n5. Reiniciando servicio TapBox en el servidor...")
stdin, stdout, stderr = ssh.exec_command(f"echo {PASS} | sudo -S systemctl restart tapbox")
stdout.read()

stdin, stdout, stderr = ssh.exec_command("sudo systemctl is-active tapbox")
status = stdout.read().decode('utf-8', errors='ignore').strip()
print(f"Estado del servicio: {status}")

ssh.close()
print("\nDespliegue y sincronizacion finalizada con exito!")
