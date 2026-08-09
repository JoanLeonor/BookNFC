



la carpeta static/ es la que almacena físicamente todos los archivos multimedia, documentos subidos y archivos temporales de tu servidor BookNFC.

Específicamente, dentro de la carpeta static/ la estructura se divide así:

📁 static/uploads/: Guarda los archivos originales de cómics, mangas, libros o documentos que subes (por ejemplo, doc_3c6d150e.cbr, doc_abc12345.pdf).

📁 static/covers/: Guarda las imágenes de las portadas (por ejemplo, cover_3c6d150e.jpg).

📁 static/cache/: Guarda temporalmente las páginas ya descomprimidas/extraídas de los cómics .cbr o .cbz para que el navegador las pueda mostrar en la tira vertical.

Todo lo demás (como las rutas, contraseñas y la lista de obras) son solo referencias de texto que viven en books.json, config.json y la lógica de app.py.