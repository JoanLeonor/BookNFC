import os
import re
import io
import math
import shutil
import zipfile
import tempfile
from PIL import Image
import pypdf
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black

PAGE_SIZES = {
    'LETTER': (612, 792),
    'A4': (595.27, 841.89),
    'TABLOID_TCG': (828, 1260)
}

# Dimensiones estándar de cartas coleccionables / Tarjetas NFC (63 x 88 mm = 178.58 x 249.45 pt)
CARD_WIDTH = 178.58
CARD_HEIGHT = 249.45

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

def natural_sort_key(s):
    """Orden natural alfanumérico para ordenar páginas y capítulos (ej. 1, 2, 10 en lugar de 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

def extract_archive_images(archive_path, extract_to):
    """Extrae todas las imágenes de un archivo CBZ, ZIP, CBR o RAR."""
    ext = os.path.splitext(archive_path)[1].lower()
    os.makedirs(extract_to, exist_ok=True)
    
    if ext in ['.zip', '.cbz']:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(extract_to)
    elif ext in ['.rar', '.cbr']:
        try:
            import rarfile
            with rarfile.RarFile(archive_path, 'r') as rf:
                rf.extractall(extract_to)
        except Exception:
            # Fallback a 7z / unrar si está disponible
            try:
                import subprocess
                subprocess.run(['unrar', 'x', '-y', archive_path, extract_to], check=True, stdout=subprocess.DEVNULL)
            except Exception:
                # Si es un zip disfrazado de cbr
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_to)
    elif os.path.isdir(archive_path):
        shutil.copytree(archive_path, extract_to, dirs_exist_ok=True)
    elif ext in IMAGE_EXTENSIONS:
        shutil.copy2(archive_path, os.path.join(extract_to, os.path.basename(archive_path)))

def collect_images_recursive(directory):
    """Recolecta y ordena todas las imágenes de un directorio."""
    images = []
    for root, _, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                images.append(os.path.join(root, file))
    images.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    return images

# =============================================================
# 1. UNIFICADOR DE DOCUMENTOS PDF
# =============================================================
def merge_pdf_files(file_paths, output_path, cover_image_path=None):
    """Une múltiples archivos PDF en uno solo, con opción de incrustar portada al inicio."""
    writer = pypdf.PdfWriter()

    # Si hay portada, convertir imagen a primera página PDF
    if cover_image_path and os.path.exists(cover_image_path):
        try:
            img = Image.open(cover_image_path).convert('RGB')
            cover_io = io.BytesIO()
            img.save(cover_io, format='PDF')
            cover_io.seek(0)
            cover_reader = pypdf.PdfReader(cover_io)
            writer.add_page(cover_reader.pages[0])
        except Exception as e:
            print(f"Error procesando portada en PDF: {e}")

    # Agregar todas las páginas de los PDFs en orden
    for path in file_paths:
        if not os.path.exists(path):
            continue
        try:
            reader = pypdf.PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            print(f"Error leyendo PDF {path}: {e}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f_out:
        writer.write(f_out)

    return output_path

# =============================================================
# 2. UNIFICADOR DE CÓMICS / MANGA (CBZ / CBR -> CBZ)
# =============================================================
def merge_comic_files(file_paths, output_path, cover_image_path=None):
    """Une múltiples cómics (CBZ, CBR, ZIP) o imágenes en un único archivo CBZ secuencial."""
    with tempfile.TemporaryDirectory(prefix="tapbox_comic_merge_") as temp_dir:
        extracted_images = []
        
        # 1. Si hay portada inicial seleccionada
        if cover_image_path and os.path.exists(cover_image_path):
            cover_dest = os.path.join(temp_dir, "00000_cover.jpg")
            shutil.copy2(cover_image_path, cover_dest)
            extracted_images.append(cover_dest)

        # 2. Extraer cada archivo en subcarpetas temporales
        for idx, file_path in enumerate(file_paths):
            if not os.path.exists(file_path):
                continue
            sub_dir = os.path.join(temp_dir, f"comic_{idx:04d}")
            extract_archive_images(file_path, sub_dir)
            images_in_sub = collect_images_recursive(sub_dir)
            extracted_images.extend(images_in_sub)

        if not extracted_images:
            raise ValueError("No se encontraron imágenes válidas para unificar.")

        # 3. Crear archivo CBZ con compresión y nombres normalizados
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as cbz:
            for page_idx, img_path in enumerate(extracted_images):
                ext = os.path.splitext(img_path)[1].lower()
                arcname = f"page_{page_idx + 1:05d}{ext}"
                cbz.write(img_path, arcname=arcname)

    return output_path

# =============================================================
# 3. AGRUPADOR EN TOMOS / VOLÚMENES
# =============================================================
def group_comics_into_tomos(file_paths, chapters_per_tomo, output_dir, prefix="Tomo", cover_image_path=None):
    """Agrupa una lista de capítulos en tomos de N capítulos cada uno."""
    os.makedirs(output_dir, exist_ok=True)
    total_files = len(file_paths)
    tomos_count = math.ceil(total_files / chapters_per_tomo)
    generated_tomos = []

    for tomo_idx in range(tomos_count):
        start_idx = tomo_idx * chapters_per_tomo
        end_idx = min(start_idx + chapters_per_tomo, total_files)
        batch = file_paths[start_idx:end_idx]

        tomo_name = f"{prefix}_{tomo_idx + 1:02d}.cbz"
        tomo_path = os.path.join(output_dir, tomo_name)

        merge_comic_files(batch, tomo_path, cover_image_path)
        generated_tomos.append(tomo_path)

    return generated_tomos

# =============================================================
# 4. MAQUETADOR DE CARTAS TCG & TARJETAS NFC (PDF DOBLE CARA)
# =============================================================
def generate_tcg_sheet(card_images, output_path, page_size='LETTER', back_image_path=None, crop_marks=True, border_size=0):
    """Genera un pliego PDF para impresión de cartas coleccionables / Tarjetas NFC con reverso espejado."""
    page_dim = PAGE_SIZES.get(page_size, PAGE_SIZES['LETTER'])
    page_w, page_h = page_dim

    if page_size == 'TABLOID_TCG':
        cols, rows = 4, 5
    else:
        cols, rows = 3, 3

    cards_per_page = cols * rows
    grid_w = cols * CARD_WIDTH
    grid_h = rows * CARD_HEIGHT
    margin_x = (page_w - grid_w) / 2
    margin_y = (page_h - grid_h) / 2

    total_cards = len(card_images)
    total_pages = math.ceil(total_cards / cards_per_page)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    c = canvas.Canvas(output_path, pagesize=page_dim)

    for p in range(total_pages):
        start_idx = p * cards_per_page
        end_idx = min(start_idx + cards_per_page, total_cards)
        page_batch = card_images[start_idx:end_idx]

        # ----------------- FRENTE (CARA A) -----------------
        for i, card_path in enumerate(page_batch):
            col = i % cols
            row = i // cols
            x = margin_x + col * CARD_WIDTH
            y = page_h - margin_y - (row + 1) * CARD_HEIGHT

            if os.path.exists(card_path):
                try:
                    c.drawImage(card_path, x, y, width=CARD_WIDTH, height=CARD_HEIGHT, preserveAspectRatio=False)
                except Exception as e:
                    print(f"Error dibujando carta {card_path}: {e}")

            # Badge numérico (#001)
            card_num = start_idx + i + 1
            badge_text = f"#{card_num:03d}"
            c.setFillColor(black)
            c.rect(x + CARD_WIDTH - 38, y + CARD_HEIGHT - 18, 34, 14, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + CARD_WIDTH - 21, y + CARD_HEIGHT - 14, badge_text)

        # Marcas de corte
        if crop_marks:
            draw_crop_marks(c, page_w, page_h, margin_x, margin_y, cols, rows, CARD_WIDTH, CARD_HEIGHT)

        c.showPage()

        # ----------------- REVERSO ESPEJADO (CARA B) -----------------
        if back_image_path and os.path.exists(back_image_path):
            for i in range(len(page_batch)):
                col = i % cols
                row = i // cols
                # Espejado horizontal para que coincida exactamente al imprimir a doble cara
                col_mirrored = (cols - 1) - col
                x = margin_x + col_mirrored * CARD_WIDTH
                y = page_h - margin_y - (row + 1) * CARD_HEIGHT

                try:
                    c.drawImage(back_image_path, x, y, width=CARD_WIDTH, height=CARD_HEIGHT, preserveAspectRatio=False)
                except Exception as e:
                    print(f"Error dibujando reverso: {e}")

            if crop_marks:
                draw_crop_marks(c, page_w, page_h, margin_x, margin_y, cols, rows, CARD_WIDTH, CARD_HEIGHT)

            c.showPage()

    c.save()
    return output_path

def generate_repeat_tcg_sheet(card_image_path, copies, output_path, page_size='LETTER', back_image_path=None, crop_marks=True, border_size=0):
    """Genera N copias de una misma carta / tarjeta NFC en pliego PDF."""
    card_list = [card_image_path] * copies
    return generate_tcg_sheet(card_list, output_path, page_size, back_image_path, crop_marks, border_size)

def draw_crop_marks(c, page_w, page_h, margin_x, margin_y, cols, rows, card_w, card_h):
    """Dibuja líneas guía de corte finas para guillotina / tijeras."""
    c.setStrokeColor(HexColor('#9ca3af'))
    c.setLineWidth(0.5)
    extension = 15

    # Líneas horizontales
    for r in range(rows + 1):
        y = page_h - margin_y - r * card_h
        c.line(margin_x - extension, y, page_w - margin_x + extension, y)

    # Líneas verticales
    for col in range(cols + 1):
        x = margin_x + col * card_w
        c.line(x, margin_y - extension, x, page_h - margin_y + extension)
