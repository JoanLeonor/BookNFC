import os
import json
import uuid
import tempfile
import shutil
import random
import string
import glob
import subprocess
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash

app = Flask(__name__)
app.secret_key = 'booknfc_secret_key_musi_card'

# Rutas de almacenamiento
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
COVER_FOLDER = os.path.join(BASE_DIR, 'static/covers')
CACHE_FOLDER = os.path.join(BASE_DIR, 'static/cache')
DB_FILE = os.path.join(BASE_DIR, 'books.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['COVER_FOLDER'] = COVER_FOLDER
app.config['CACHE_FOLDER'] = CACHE_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVER_FOLDER, exist_ok=True)
os.makedirs(CACHE_FOLDER, exist_ok=True)

# ----------------- FUNCIONES AUXILIARES -----------------

def generate_nfc_key():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"NFC-{chars}"

def get_disk_status():
    total, used, free = shutil.disk_usage(BASE_DIR)
    gb = 1024 * 1024 * 1024
    return {
        'total': round(total / gb, 2),
        'used': round(used / gb, 2),
        'free': round(free / gb, 2),
        'percent_used': round((used / total) * 100, 1)
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

def extract_cbr_pages(book_id, filepath):
    """ Extrae un archivo CBR/RAR a la carpeta de caché y mapea las imágenes incluso dentro de subcarpetas """
    target_dir = os.path.join(CACHE_FOLDER, book_id)
    
    if not os.path.exists(target_dir) or not os.listdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        try:
            res = subprocess.run(["unar", "-o", target_dir, "-f", filepath], capture_output=True)
            if res.returncode != 0:
                subprocess.run(["7z", "x", "-y", f"-o{target_dir}", filepath], check=True)
        except Exception as e:
            print("Error extrayendo CBR:", e)

    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')
    images = []
    
    if os.path.exists(target_dir):
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.endswith(valid_exts):
                    full_p = os.path.join(root, f)
                    if os.path.getsize(full_p) > 0:
                        # Extrae la ruta relativa interna (ejemplo: doc_3c6d150e/CRLN-003.jpg)
                        rel_p = os.path.relpath(full_p, target_dir).replace('\\', '/')
                        images.append(rel_p)

    images.sort()
    
    # Genera las URLs soportando la subcarpeta interna
    urls = [f"/cache_file/{book_id}/{filename}" for filename in images]
    return urls

# ----------------- RUTAS PÚBLICAS Y LECTOR WEB -----------------

@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/nfc/<nfc_key>')
def nfc_reader(nfc_key):
    books = load_books()
    book = next((b for b in books if b.get('nfc_key', '').upper() == nfc_key.upper()), None)
    if book:
        return render_template('book.html', book=book)
    return render_template('not_found.html', nfc_key=nfc_key), 404

@app.route('/read/<book_id>')
def web_reader(book_id):
    books = load_books()
    book = next((b for b in books if b.get('id') == book_id), None)
    if book:
        filename = book.get('file', '')
        file_ext = os.path.splitext(filename)[1].replace('.', '').strip().lower()
        
        cbr_images = []
        if file_ext == 'cbr':
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            cbr_images = extract_cbr_pages(book_id, filepath)

        return render_template('reader.html', book=book, file_ext=file_ext, cbr_images=cbr_images)
    flash("Obra no encontrada", "error")
    return redirect(url_for('gallery'))

@app.route('/gallery')
def gallery():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    books = load_books()
    return render_template('gallery.html', books=books)

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/cache_file/<book_id>/<path:filename>')
def serve_cache_file(book_id, filename):
    """ Servir imágenes descomprimidas soportando subcarpetas anidadas (<path:filename>) """
    cache_dir = os.path.join(app.config['CACHE_FOLDER'], book_id)
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
    disk = get_disk_status()
    random_nfc = generate_nfc_key()
    
    return render_template('admin.html', books=books, config=config, disk=disk, random_nfc=random_nfc)

@app.route('/admin/batch')
def batch_upload_view():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))
    return render_template('batch_upload.html')

@app.route('/admin/batch-upload', methods=['POST'])
def batch_upload_process():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))

    titles = request.form.getlist('title[]')
    nfc_keys = request.form.getlist('nfc_key[]')
    synopses = request.form.getlist('synopsis[]')
    covers = request.files.getlist('cover[]')
    files = request.files.getlist('file[]')

    books = load_books()
    added_count = 0

    for i in range(len(titles)):
        title = titles[i].strip() if i < len(titles) else ''
        nfc_key = nfc_keys[i].strip().upper() if i < len(nfc_keys) and nfc_keys[i].strip() else generate_nfc_key()
        synopsis = synopses[i].strip() if i < len(synopses) and synopses[i].strip() else "Sin sinopsis disponible."
        cover_file = covers[i] if i < len(covers) else None
        book_file = files[i] if i < len(files) else None

        if title and cover_file and book_file:
            unique_id = str(uuid.uuid4())[:8]
            ext_cover = os.path.splitext(cover_file.filename)[1]
            ext_file = os.path.splitext(book_file.filename)[1]

            cover_filename = f"cover_{unique_id}{ext_cover}"
            book_filename = f"doc_{unique_id}{ext_file}"

            cover_file.save(os.path.join(app.config['COVER_FOLDER'], cover_filename))
            book_file.save(os.path.join(app.config['UPLOAD_FOLDER'], book_filename))

            books.append({
                'id': unique_id,
                'title': title,
                'nfc_key': nfc_key,
                'synopsis': synopsis,
                'cover': cover_filename,
                'file': book_filename
            })
            added_count += 1

    if added_count > 0:
        save_books(books)
        flash(f"¡Se han registrado {added_count} obras exitosamente!", "success")
    else:
        flash("No se pudo registrar ninguna obra. Verifica los archivos.", "error")

    return redirect(url_for('admin'))

@app.route('/admin/upload', methods=['POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('admin'))

    title = request.form.get('title')
    nfc_key = request.form.get('nfc_key', '').strip().upper()
    if not nfc_key:
        nfc_key = generate_nfc_key()

    synopsis = request.form.get('synopsis', '').strip()
    cover_file = request.files.get('cover')
    book_file = request.files.get('file')

    if title and cover_file and book_file:
        unique_id = str(uuid.uuid4())[:8]
        ext_cover = os.path.splitext(cover_file.filename)[1]
        ext_file = os.path.splitext(book_file.filename)[1]

        cover_filename = f"cover_{unique_id}{ext_cover}"
        book_filename = f"doc_{unique_id}{ext_file}"

        cover_file.save(os.path.join(app.config['COVER_FOLDER'], cover_filename))
        book_file.save(os.path.join(app.config['UPLOAD_FOLDER'], book_filename))

        books = load_books()
        books.append({
            'id': unique_id,
            'title': title,
            'nfc_key': nfc_key,
            'synopsis': synopsis if synopsis else "Sin sinopsis disponible.",
            'cover': cover_filename,
            'file': book_filename
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
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], book_to_delete['file'])
            cache_dir = os.path.join(app.config['CACHE_FOLDER'], book_id)

            if os.path.exists(cover_path): os.remove(cover_path)
            if os.path.exists(file_path): os.remove(file_path)
            if os.path.exists(cache_dir): shutil.rmtree(cache_dir, ignore_errors=True)
        except Exception:
            pass

        books = [b for b in books if b.get('id') != book_id]
        save_books(books)
        flash("Obra eliminada y espacio liberado", "success")
        
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='[IP_ADDRESS]', port=5000, debug=True)