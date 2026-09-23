# 📖 TapBox (BookNFC) 🚀

**TapBox** (también conocido como **BookNFC**) es un ecosistema de biblioteca digital y centro multimedia auto-alojado basado en **Flask**, diseñado para conectar el mundo físico con el digital. Permite vincular tarjetas o etiquetas físicas **NFC** a libros, mangas, cómics, películas, series, animes y música. Al escanear una tarjeta NFC, el usuario es redirigido automáticamente a la información de la obra, a su reproductor multimedia, a su lector en tira vertical continua o a la estación de música interactiva.

El proyecto está diseñado y optimizado para ser extremadamente ligero y eficiente, permitiendo su ejecución en una **Raspberry Pi**, servidor local o contenedor Docker.

---

## 📸 Capturas de Pantalla

| Galería Principal | Estación de Música Hi-Fi | Emulador de Juegos Retro |
|:---:|:---:|:---:|
| ![Galería Principal](Capturas/pantalla%20gallery.png) | ![Música Hi-Fi](Capturas/pantalla%20music.png) | ![Emulador Retro](Capturas/pantalla%20game.png) |

| Vista de Obra (NFC) | Panel de Administración | Importador por Carpetas |
|:---:|:---:|:---:|
| ![Vista Obra](Capturas/pantalla%20nfc%20A.png) | ![Panel Admin](Capturas/pantalla%20admin.png) | ![Importador](Capturas/pantalla%20folder%20import.png) |

| Carga Masiva (Batch) | Gestor de Archivos Multimedia | Conversor MP4 en Tiempo Real |
|:---:|:---:|:---:|
| ![Carga Masiva](Capturas/pantalla%20carga%20masiva.png) | ![Archivos](Capturas/pantalla%20files.png) | ![Conversor](Capturas/pantalla%20converter.png) |

| Limpiador y Huérfanos | Login de Administración | Error NFC No Asignado |
|:---:|:---:|:---:|
| ![Limpiador](Capturas/pantalla%20cleaner.png) | ![Login](Capturas/pantalla%20login.png) | ![NFC No Asignado](Capturas/pantalla%20nfc%20fail.png) |

---

## ✨ Características Principales

* **🔗 Integración NFC Dinámica**: Mapeo inteligente de tarjetas físicas a través de la ruta `/nfc/<nfc_key>`. Si se escanea una tarjeta no registrada, el sistema despliega una interfaz interactiva de asignación para vincularla a una obra existente o nueva en segundos.
* **🎮 Emulador de Videojuegos Retro Web (EmulatorJS / WebAssembly - `/category/game`)**:
  * **Emulación Directa en Navegador a 60 FPS**: Ejecución de ROMs sin requerir emuladores externos ni sobrecargar el procesador del servidor.
  * **Soporte Multiconsola Automático**: Detección inteligente de núcleos para **Super Nintendo (SNES)**, **Game Boy Advance (GBA)**, **Game Boy Color (GBC)**, **Game Boy (GB)**, **Nintendo Entertainment System (NES)**, **Nintendo 64 (N64)**, **Sega Genesis / Mega Drive (MD)**, **Nintendo DS (NDS)** y **PlayStation (PS1)**.
  * **Controles Universales**: Soporte nativo para mandos **USB y Bluetooth (Xbox, DualShock/DualSense)**, controles táctiles en pantalla para móviles/tablets y teclado configurable.
  * **Gestión de Partidas (Save States)**: Guardado y carga de partidas en cualquier punto de la aventura.
* **🎵 Música Hi-Fi (Audiophile Edition - `/category/music`)**:
  * **Motor Web Audio API en Tiempo Real**: Análisis de frecuencias a 60 FPS con extracción de bajos, medios y agudos.
  * **5 Modos de Visualización Reactivos**:
    * **Espectro Radial 360°**: Rayos concéntricos giratorios alrededor del disco de vinilo.
    * **Vórtice de Partículas Cósmicas**: 130 partículas orbitando y emanando con halos en cada beat y constelaciones reactivas a los agudos.
    * **Onda Líquida**: 3 capas fluidas de ondas con gradientes de cian, violeta y rosa moduladas por frecuencias.
    * **Barras Hi-Fi de Estudio**: 48 bandas ecualizadoras de alta resolución con picos flotantes (*peak hold caps*) y descenso gravitacional.
    * **Aurora Glow**: 4 orbes de plasma en órbita concéntrica cuyos radios, intensidades y opacidades siguen el ritmo.
  * **Modo Inmersivo de Estudio (Vista Ampliada)**: Vinilo holográfico giratorio con sincronización de estado, atajos de teclado (`M` para alternar modos, `Espacio` para pausa/play, `ESC` para salir) y herramienta de volumen interactiva bidireccional.
  * **Navegación Dinámica**: Filtrado en vivo por Álbumes, Artistas y Canciones locales sin recargar la página.
* **📚 Soporte Multiformato y Galería Interactiva**:
  * **Mangas y Cómics**: Lector web optimizado para lectura en tira vertical continua (webtoons/mangas/cómics). Extrae y cachea páginas de archivos `.cbr` y `.cbz` mediante utilidades del sistema (`unar` / `7z`).
  * **Películas y Series / Animes**: Reproductor de video HTML5 integrado para formatos `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, etc., con selector de episodios en series.
  * **Libros Digitales**: Lector y visor de documentos PDF y EPUB.
* **🗂️ Gestión de Sagas y Portadas Inteligentes**:
  * Agrupación automática por sagas/colecciones (mostrando 1 sola tarjeta consolidada en la galería).
  * Portada fija por saga (`is_saga_cover`) o **rotación aleatoria de portadas** (`saga_random_cover`) en cada visita.
  * Control de visibilidad en la galería principal (`show_in_gallery`).
* **🔄 Sincronización Automática de Biblioteca (`/admin/library-sync`)**:
  * Escaneo directo de la carpeta multimedia del servidor (`/data/media` o personalizada).
  * Integración nativa con **Radarr**, **Sonarr** y **Lidarr**: descarga automática de sinopsis oficiales, portadas/pósters remotos en alta calidad, géneros y artistas.
  * Importación con 1 solo clic y sincronización masiva de metadatos.
* **📂 Importación Flexible**:
  * Formulario individual en el panel de control.
  * **Carga Masiva (Batch Upload)** asíncrona con barra de progreso interactiva.
  * **Importación por Carpetas (Folder Import)** para procesar librerías locales completas.
* **🛡️ Panel de Administración Seguro**:
  * Control de acceso por contraseña de administración.
  * Edición rápida de metadatos, sustitución de portadas y archivos, y cambio de clave NFC.
  * Liberación automática de espacio en disco al eliminar obras y limpiar la caché.
  * Cambio de contraseña administrativa en tiempo real.
* **💾 Monitoreo de Almacenamiento**: Estadísticas en tiempo real sobre uso total, ocupado, libre y porcentaje del disco.

---

## 📁 Estructura del Proyecto

```text
TapBox/
├── app.py                  # Servidor principal Flask y backend integrado
├── catalog.json            # Base de datos local principal en formato JSON
├── books.json              # Base de datos legacy (migración automática a catalog.json)
├── config.json             # Configuración del sistema y credenciales
├── config.json.example     # Plantilla de configuración
├── catalog.json.example    # Plantilla de base de datos de ejemplo
├── notas.md                # Notas de servidores, comandos, credenciales y puertos
├── Capturas/               # Capturas de pantalla del sistema
├── static/
│   ├── covers/             # Portadas de las obras (cover_*.jpg / cover_*.svg)
│   ├── uploads/            # Archivos fuente (doc_*.cbr, videos, media_*/, etc.)
│   └── cache/              # Caché de imágenes descomprimidas de CBR/CBZ
└── templates/
    ├── index.html          # Galería principal y resumen por categorías
    ├── category.html       # Exploración paginada por categoría (Mangas, Películas, Series, etc.)
    ├── music.html          # Reproductor Hi-Fi Audiophile Edition con visualizadores reactivos
    ├── game.html           # Emulador web de videojuegos retro (EmulatorJS / WebAssembly)
    ├── book.html           # Vista pública detallada tras escanear tarjeta NFC
    ├── reader.html         # Lector web en tira continua para cómics y mangas
    ├── player.html         # Reproductor de video interactivo para películas y series
    ├── admin.html          # Panel de administración principal y edición
    ├── batch_upload.html   # Carga masiva asíncrona por lote
    ├── folder_import.html  # Importación masiva desde carpetas locales
    ├── library_sync.html   # Sincronización e importación desde biblioteca (/data/media + *arr)
    ├── login.html          # Autenticación del administrador
    └── not_found.html      # Gestión de llaves NFC no asignadas
```

---

## 🛠️ Requisitos e Instalación

### 1. Requisitos del Sistema
Para la descompresión en tiempo real de cómics (`.cbr` / `.cbz`), instala las utilidades de extracción en tu sistema operativo:

#### En Debian / Ubuntu / Raspberry Pi OS:
```bash
sudo apt update
sudo apt install unar p7zip-full python3 python3-pip
```

### 2. Instalación de Dependencias de Python
Instala Flask y sus librerías requeridas:
```bash
pip install Flask
```

### 3. Configuración Inicial
Crea tu archivo local de configuración desde la plantilla:
```bash
cp config.json.example config.json
```
*(Opcional)* Si tienes una base de datos previa `books.json`, el sistema la migrará automáticamente a `catalog.json` al iniciar.

### 4. Ejecutar el Servidor
Inicia la aplicación:
```bash
python app.py
```
El servidor se ejecutará por defecto en `http://0.0.0.0:5000/`, accesible desde cualquier dispositivo en la red local.

---

## 🖥️ Despliegue en Servidor Local (IP Actual: 192.168.0.11)

Para conectarte al servidor local vía SSH:

```bash
ssh joanml@192.168.0.11
# Contraseña: joanml
cd ~/tapbox
```

### Gestión del Servicio en Ubuntu:
```bash
# Ver estado del servicio
sudo systemctl status tapbox

# Reiniciar servicio
sudo systemctl restart tapbox

# Ver registros en vivo
journalctl -u tapbox -f
```

---

## ⚙️ Configuración de Archivos JSON

El sistema utiliza archivos JSON excluidos de Git para proteger la información privada:

### 1. `config.json`
Almacena la contraseña administrativa, la ruta de la biblioteca multimedia y las conexiones a los servicios de descarga/metadatos:
```json
{
    "admin_pass": "admin123",
    "media_root": "/data/media",
    "radarr_url": "http://127.0.0.1:7878",
    "radarr_api_key": "TU_API_KEY",
    "sonarr_url": "http://127.0.0.1:8989",
    "sonarr_api_key": "TU_API_KEY",
    "lidarr_url": "http://127.0.0.1:8686",
    "lidarr_api_key": "TU_API_KEY"
}
```

### 2. `catalog.json`
Estructura de registro de una obra en el catálogo:
```json
[
    {
        "id": "3c6d150e",
        "title": "Nombre de la Obra",
        "type": "manga",
        "author": "Nombre del Autor / Estudio",
        "saga": "Nombre de la Saga",
        "category": "Acción, Fantasía",
        "nfc_key": "NFC-QZP519",
        "synopsis": "Sinopsis o descripción de la obra.",
        "cover": "cover_3c6d150e.jpg",
        "file": "doc_3c6d150e.cbr",
        "show_in_gallery": true,
        "is_saga_cover": false,
        "saga_random_cover": true
    }
]
```

* `id`: Identificador único de 8 caracteres.
* `type`: Tipo de contenido (`book`, `manga`, `movie`, `series`, `anime`, `music`).
* `nfc_key`: Clave vinculada a la etiqueta NFC física.
* `cover`: Portada en `static/covers/`.
* `file`: Archivo principal o lista de archivos de episodios en `static/uploads/` o ruta de biblioteca.
