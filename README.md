# 📖 TapBox (BookNFC) 🚀

**TapBox** (también conocido como **BookNFC**) es un sistema de biblioteca digital auto-alojado basado en **Flask** diseñado para conectar el mundo físico con el digital. Permite vincular tarjetas o etiquetas físicas **NFC** a libros, mangas o cómics digitales. Al escanear una tarjeta NFC, el usuario es redirigido automáticamente a la información de la obra y a un lector interactivo en tira vertical continua.

El proyecto está diseñado y optimizado para ser lo suficientemente ligero como para ejecutarse en una **Raspberry Pi Zero** o cualquier servidor local.

---

## 📸 Capturas de Pantalla

A continuación se muestran algunas de las interfaces del sistema:

| Login de Administración | Galería de Obras |
|:---:|:---:|
| ![Login](Capturas/pantalla%20login.png) | ![Galería](Capturas/pantalla%20gallery.png) |

| Vista de Obra (NFC) | Panel de Control de Administración |
|:---:|:---:|
| ![Vista Obra](Capturas/pantalla%20nfc%20A.png) | ![Panel Admin](Capturas/pantalla%20admin.png) |

| Carga Masiva (Batch) | Error NFC No Asignado |
|:---:|:---:|
| ![Carga Masiva](Capturas/pantalla%20carga%20masiva.png) | ![NFC No Asignado](Capturas/pantalla%20nfc%20fail.png) |

---

## ✨ Características Principales

*   **🔗 Integración NFC Dinámica**: Mapeo de tarjetas físicas a través de la ruta `/nfc/<nfc_key>`. Si se escanea una tarjeta no registrada, el sistema muestra una interfaz dedicada que permite al administrador asignarla rápidamente a una obra nueva.
*   **📖 Lector Web Universal**: Lector interactivo optimizado para tira vertical continua (ideal para webtoons, cómics y mangas). Extrae y cachea en tiempo real páginas de archivos `.cbr` usando utilidades del sistema (`unar` / `7z`).
*   **📂 Carga Individual y Masiva (Batch Upload)**:
    *   Formulario de carga de una sola obra en el panel de administración.
    *   Carga masiva asíncrona con barra de progreso interactiva para registrar múltiples cómics a la vez.
*   **🛡️ Panel de Administración Protegido**: Acceso restringido por contraseña para gestionar obras (añadir, eliminar) y cambiar credenciales.
*   **💾 Monitoreo de Almacenamiento**: Muestra estadísticas en tiempo real sobre el uso del espacio en disco duro directamente en el panel de administración.

---

## 📁 Estructura del Proyecto

```text
TapBox/
├── app.py                  # Servidor principal Flask y lógica del backend
├── books.json              # Base de datos local de obras en formato JSON
├── config.json             # Configuración del sistema y credenciales administrativas
├── notas.md                # Notas rápidas de comandos, accesos y estructura
├── Capturas/               # Capturas de pantalla e imágenes de demostración
├── static/
│   ├── covers/             # Portadas de las obras (formato cover_*.jpg)
│   ├── uploads/            # Archivos fuente de las obras (doc_*.cbr, doc_*.pdf, etc.)
│   └── cache/              # Directorio temporal de descompresión de archivos CBR/CBZ
└── templates/
    ├── admin.html          # Vista del panel de administración
    ├── batch_upload.html   # Vista para subidas múltiples asíncronas
    ├── gallery.html        # Galería para explorar todas las obras registradas
    ├── reader.html         # Lector web en tira continua
    ├── book.html           # Vista pública de la obra tras escanear el NFC
    ├── login.html          # Autenticación del administrador
    └── not_found.html      # Página de ayuda al escanear un NFC no asignado
```

---

## 🛠️ Requisitos e Instalación

### 1. Requisitos del Sistema
Para que el lector web procese correctamente los archivos `.cbr` (cómics comprimidos en RAR), el sistema operativo debe tener instalada alguna de las siguientes utilidades de extracción:
*   `unar` (Recomendado)
*   `p7zip-full` / `7zip`

#### En sistemas Debian/Ubuntu/Raspberry Pi OS:
```bash
sudo apt update
sudo apt install unar p7zip-full python3 python3-pip
```

### 2. Instalación de Dependencias de Python
Instala Flask y sus dependencias necesarias:
```bash
pip install Flask
```

### 3. Ejecutar el Servidor
Inicia la aplicación de Flask:
```bash
python app.py
```
Por defecto, el servidor se iniciará en `http://0.0.0.0:5000/`, lo que permite acceder a él desde cualquier dispositivo en la misma red local.

---

## 🖥️ Despliegue en Raspberry Pi Zero

Si estás utilizando una Raspberry Pi Zero en tu red local (por ejemplo, con la ip del dispositivo):

1.  Conéctate por SSH:
    ```bash
    ssh User
    # Contraseña por defecto: ************
    ```
2.  Accede a la carpeta del proyecto:
    ```bash
    cd ~/booknfc
    ```
3.  Ejecuta o edita los archivos directamente si es necesario.

---

## ⚙️ Configuración y Base de Datos

El sistema se basa en archivos JSON planos. Para proteger tu información, estos archivos están excluidos del control de versiones (git). Para iniciar el proyecto, debes crear copias locales a partir de los archivos de ejemplo proporcionados:

### 1. `config.json`
Almacena la contraseña de administrador. Crea tu copia local ejecutando:
```bash
cp config.json.example config.json
```
Contenido por defecto:
```json
{
    "admin_pass": "admin123"
}
```

### 2. `books.json`
Almacena la colección de libros. Crea tu copia local ejecutando:
```bash
cp books.json.example books.json
```
Formato de cada obra en el archivo:
```json
[
    {
        "id": "3c6d150e",
        "title": "Nombre de la Obra",
        "nfc_key": "NFC-QZP519",
        "synopsis": "Sinopsis de la obra o descripción breve.",
        "cover": "cover_3c6d150e.jpg",
        "file": "doc_3c6d150e.cbr"
    }
]
```
*   `id`: Identificador único de 8 caracteres.
*   `nfc_key`: Clave NFC asociada físicamente a la tarjeta.
*   `cover`: Nombre del archivo de portada guardado en `static/covers/`.
*   `file`: Nombre del archivo de documento guardado en `static/uploads/`.
