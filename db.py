import os
import json
import logging
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger("tapbox.db")

# Configuración por defecto de PostgreSQL
DEFAULT_DB_CONFIG = {
    "host": os.environ.get("TAPBOX_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("TAPBOX_DB_PORT", "5433")),
    "dbname": os.environ.get("TAPBOX_DB_NAME", "tapbox_db"),
    "user": os.environ.get("TAPBOX_DB_USER", "tapbox_user"),
    "password": os.environ.get("TAPBOX_DB_PASSWORD", "tapbox_password")
}

_connection_pool = None

def get_db_config():
    """Carga configuración de base de datos desde config.json o variables de entorno."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_file = os.path.join(base_dir, 'config.json')
    cfg = DEFAULT_DB_CONFIG.copy()
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'db' in data and isinstance(data['db'], dict):
                    cfg.update(data['db'])
        except Exception as e:
            logger.warning(f"Error leyendo config.json para DB: {e}")
    return cfg

def init_pool(db_config=None, minconn=1, maxconn=15):
    """Inicializa el pool de conexiones a PostgreSQL."""
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool
    
    cfg = db_config or get_db_config()
    try:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn,
            maxconn,
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 5433)),
            dbname=cfg.get("dbname", "tapbox_db"),
            user=cfg.get("user", "tapbox_user"),
            password=cfg.get("password", "tapbox_password"),
            connect_timeout=10
        )
        logger.info(f"Pool de conexiones PostgreSQL inicializado ({cfg['host']}:{cfg['port']}/{cfg['dbname']})")
        return _connection_pool
    except Exception as e:
        logger.error(f"Error inicializando pool de PostgreSQL: {e}")
        # Intentar conectar con host remoto si 127.0.0.1 falla (útil para desarrollo local en Windows)
        if cfg.get("host") == "127.0.0.1":
            try:
                cfg_remote = cfg.copy()
                cfg_remote["host"] = "192.168.0.238"
                cfg_remote["port"] = int(cfg_remote.get("port", 5433))
                _connection_pool = pool.ThreadedConnectionPool(
                    minconn, maxconn, **cfg_remote, connect_timeout=10
                )
                logger.info(f"Conectado a PostgreSQL remoto en 192.168.0.238")
                return _connection_pool
            except Exception as e2:
                logger.error(f"Error conectando a PostgreSQL remoto: {e2}")
        raise e

@contextmanager
def get_db_connection():
    """Context manager para obtener y devolver una conexión del pool."""
    global _connection_pool
    if _connection_pool is None:
        init_pool()
    conn = _connection_pool.getconn()
    try:
        yield conn
    finally:
        _connection_pool.putconn(conn)

@contextmanager
def get_db_cursor(commit=False):
    """Context manager para obtener un cursor con RealDictCursor."""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

def init_db(db_config=None):
    """Crea las tablas e índices necesarios en PostgreSQL."""
    global _connection_pool
    if db_config:
        _connection_pool = None
        init_pool(db_config)
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS works (
        id VARCHAR(32) PRIMARY KEY,
        title VARCHAR(512) NOT NULL,
        type VARCHAR(64) NOT NULL,
        author VARCHAR(512) DEFAULT '',
        saga VARCHAR(512) DEFAULT '',
        category VARCHAR(512) DEFAULT '',
        genres VARCHAR(512) DEFAULT '',
        nfc_key VARCHAR(128) DEFAULT '',
        synopsis TEXT DEFAULT '',
        "desc" TEXT DEFAULT '',
        cover VARCHAR(512) DEFAULT '',
        file JSONB NOT NULL DEFAULT '""'::jsonb,
        storage VARCHAR(128) DEFAULT '',
        date_added VARCHAR(64) DEFAULT '',
        show_in_gallery BOOLEAN DEFAULT TRUE,
        is_saga_cover BOOLEAN DEFAULT FALSE,
        saga_random_cover BOOLEAN DEFAULT FALSE,
        extra_data JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_works_type ON works(type);
    CREATE INDEX IF NOT EXISTS idx_works_nfc_key ON works(nfc_key);
    CREATE INDEX IF NOT EXISTS idx_works_saga ON works(saga);
    CREATE INDEX IF NOT EXISTS idx_works_title ON works(title);
    CREATE INDEX IF NOT EXISTS idx_works_show_gallery ON works(show_in_gallery);
    """
    with get_db_cursor(commit=True) as cur:
        cur.execute(create_table_sql)
    logger.info("Esquema relacional de TapBox verificado/creado exitosamente.")

def row_to_dict(row):
    """Convierte una fila de PostgreSQL al diccionario exacto esperado por TapBox."""
    if not row:
        return None
    d = dict(row)
    
    # Extraer campos no expuestos o timestamp interno
    d.pop('created_at', None)
    d.pop('updated_at', None)
    extra = d.pop('extra_data', None) or {}
    
    # Asegurar que file sea string o list según corresponda
    file_val = d.get('file')
    if isinstance(file_val, str) and (file_val.startswith('[') or file_val.startswith('"')):
        try:
            file_val = json.loads(file_val)
        except Exception:
            pass
    d['file'] = file_val
    
    # Si existen campos adicionales en extra_data, combinarlos
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in d:
                d[k] = v
                
    return d

def dict_to_row_params(item):
    """Prepara los parámetros de inserción/actualización desde un diccionario de obra."""
    known_fields = {
        'id', 'title', 'type', 'author', 'saga', 'category', 'genres',
        'nfc_key', 'synopsis', 'desc', 'cover', 'file', 'storage',
        'date_added', 'show_in_gallery', 'is_saga_cover', 'saga_random_cover'
    }
    
    work_id = str(item.get('id', '')).strip()
    title = str(item.get('title', '')).strip()
    work_type = str(item.get('type', 'book')).strip()
    author = str(item.get('author', '')).strip()
    saga = str(item.get('saga', '')).strip()
    category = str(item.get('category', '')).strip()
    genres = str(item.get('genres', '')).strip()
    nfc_key = str(item.get('nfc_key', '')).strip()
    synopsis = str(item.get('synopsis', '')).strip()
    desc = str(item.get('desc', '')).strip()
    cover = str(item.get('cover', '')).strip()
    file_val = item.get('file', '')
    storage = str(item.get('storage', '')).strip()
    date_added = str(item.get('date_added', '')).strip()
    show_in_gallery = bool(item.get('show_in_gallery', True))
    is_saga_cover = bool(item.get('is_saga_cover', False))
    saga_random_cover = bool(item.get('saga_random_cover', False))
    
    extra_data = {k: v for k, v in item.items() if k not in known_fields}
    
    return (
        work_id, title, work_type, author, saga, category, genres,
        nfc_key, synopsis, desc, cover, Json(file_val), storage,
        date_added, show_in_gallery, is_saga_cover, saga_random_cover,
        Json(extra_data)
    )

def get_all_works(work_type=None):
    """Obtiene todas las obras del catálogo (reemplazo de load_books)."""
    sql = "SELECT * FROM works"
    params = []
    if work_type:
        sql += " WHERE type = %s"
        params.append(work_type)
    sql += " ORDER BY id ASC"
    
    with get_db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [row_to_dict(r) for r in rows]

def get_work_by_id(work_id):
    """Obtiene una obra individual por su ID único."""
    sql = "SELECT * FROM works WHERE id = %s LIMIT 1"
    with get_db_cursor() as cur:
        cur.execute(sql, (work_id,))
        row = cur.fetchone()
        return row_to_dict(row)

def get_work_by_nfc(nfc_key):
    """Obtiene una obra por su llave NFC."""
    sql = "SELECT * FROM works WHERE nfc_key = %s LIMIT 1"
    with get_db_cursor() as cur:
        cur.execute(sql, (nfc_key,))
        row = cur.fetchone()
        return row_to_dict(row)

def upsert_work(item):
    """Inserta o actualiza una obra de forma atómica en PostgreSQL."""
    params = dict_to_row_params(item)
    sql = """
    INSERT INTO works (
        id, title, type, author, saga, category, genres,
        nfc_key, synopsis, "desc", cover, file, storage,
        date_added, show_in_gallery, is_saga_cover, saga_random_cover,
        extra_data, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, CURRENT_TIMESTAMP
    )
    ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        type = EXCLUDED.type,
        author = EXCLUDED.author,
        saga = EXCLUDED.saga,
        category = EXCLUDED.category,
        genres = EXCLUDED.genres,
        nfc_key = EXCLUDED.nfc_key,
        synopsis = EXCLUDED.synopsis,
        "desc" = EXCLUDED."desc",
        cover = EXCLUDED.cover,
        file = EXCLUDED.file,
        storage = EXCLUDED.storage,
        date_added = EXCLUDED.date_added,
        show_in_gallery = EXCLUDED.show_in_gallery,
        is_saga_cover = EXCLUDED.is_saga_cover,
        saga_random_cover = EXCLUDED.saga_random_cover,
        extra_data = EXCLUDED.extra_data,
        updated_at = CURRENT_TIMESTAMP;
    """
    with get_db_cursor(commit=True) as cur:
        cur.execute(sql, params)

def delete_work(work_id):
    """Elimina una obra por ID."""
    sql = "DELETE FROM works WHERE id = %s"
    with get_db_cursor(commit=True) as cur:
        cur.execute(sql, (work_id,))

def save_all_works(works_list):
    """
    Guarda una lista completa de obras en PostgreSQL (reemplazo de save_books).
    Utiliza una transacción atómica para sincronizar el estado completo.
    """
    if not works_list:
        return
        
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Obtener IDs actuales para saber cuáles eliminar si ya no existen en la lista
            cur.execute("SELECT id FROM works")
            existing_ids = {row[0] for row in cur.fetchall()}
            new_ids = {str(item.get('id', '')).strip() for item in works_list if item.get('id')}
            
            to_delete = existing_ids - new_ids
            if to_delete:
                cur.execute("DELETE FROM works WHERE id = ANY(%s)", (list(to_delete),))
            
            # Upsert de cada obra
            upsert_sql = """
            INSERT INTO works (
                id, title, type, author, saga, category, genres,
                nfc_key, synopsis, "desc", cover, file, storage,
                date_added, show_in_gallery, is_saga_cover, saga_random_cover,
                extra_data, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, CURRENT_TIMESTAMP
            )
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                type = EXCLUDED.type,
                author = EXCLUDED.author,
                saga = EXCLUDED.saga,
                category = EXCLUDED.category,
                genres = EXCLUDED.genres,
                nfc_key = EXCLUDED.nfc_key,
                synopsis = EXCLUDED.synopsis,
                "desc" = EXCLUDED."desc",
                cover = EXCLUDED.cover,
                file = EXCLUDED.file,
                storage = EXCLUDED.storage,
                date_added = EXCLUDED.date_added,
                show_in_gallery = EXCLUDED.show_in_gallery,
                is_saga_cover = EXCLUDED.is_saga_cover,
                saga_random_cover = EXCLUDED.saga_random_cover,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP;
            """
            for item in works_list:
                if not item or not item.get('id'):
                    continue
                params = dict_to_row_params(item)
                cur.execute(upsert_sql, params)
        conn.commit()

def count_works():
    """Retorna el conteo total de obras registradas."""
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM works")
        row = cur.fetchone()
        return row['count'] if row else 0
