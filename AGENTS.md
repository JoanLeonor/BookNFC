# Reglas del Proyecto y Despliegue Obligatorio en Servidor (TapBox)

> [!IMPORTANT]
> **REGLA CRÍTICA DE DESPLIEGUE EN PRODUCCIÓN:**
> Todo cambio realizado en el código local (backend `app.py`, plantillas `templates/*.html`, estilos CSS, base de datos `catalog.json`, portadas `static/covers/` o archivos de subidas `static/uploads/`) **DEBE SER SINCRONIZADO Y DESPLEGADO AUTOMÁTICAMENTE AL SERVIDOR REAL (`192.168.0.11`)** y el servicio `tapbox` debe ser reiniciado.

---

## 🖥️ Datos del Servidor Remoto

* **Host / IP:** `192.168.0.11`
* **Puerto SSH:** `22`
* **Usuario SSH:** `joanml`
* **Contraseña SSH / Sudo:** `joanml`
* **Ruta del Proyecto en Servidor:** `/home/joanml/tapbox`
* **Servicio Systemd:** `tapbox`
* **Comando de reinicio:** `echo joanml | sudo -S systemctl restart tapbox`

---

## 🔄 Protocolo de Sincronización Automática

Cada vez que se complete una modificación o corrección en el entorno local:
1. **Sincronizar Archivos:** Ejecutar el script `python deploy_to_server.py` o transferir vía SSH/SFTP los archivos modificados hacia `/home/joanml/tapbox/`.
2. **Reiniciar Servicio:** Ejecutar el reinicio del servicio `tapbox` en `192.168.0.11`.
3. **Verificar Salud:** Comprobar con una petición HTTP que el servicio responde exitosamente (`HTTP 200`) en `http://192.168.0.11:5000`.

---

## 🌐 URLs del Servidor

* **Inicio / Catálogo:** [http://192.168.0.11:5000](http://192.168.0.11:5000)
* **Música Hi-Fi:** [http://192.168.0.11:5000/music](http://192.168.0.11:5000/music)
* **Administración:** [http://192.168.0.11:5000/admin](http://192.168.0.11:5000/admin)
* **Importación por Carpetas:** [http://192.168.0.11:5000/admin/folder-import](http://192.168.0.11:5000/admin/folder-import)
