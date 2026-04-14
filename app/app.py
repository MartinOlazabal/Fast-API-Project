# ============================================================================
# IMPORTS - Librerías y módulos necesarios para la aplicación
# ============================================================================
import os  # Para operaciones del sistema operativo
import shutil  # Para copiar archivos
import tempfile  # Para crear archivos temporales
import uuid  # Para manejar identificadores únicos (UUID)
import tempfile  # Para crear archivos temporales de forma segura
from users import auth_backend, current_active_users, fastapi_users  # Importar autenticación y gestión de usuarios

from contextlib import asynccontextmanager  # Para manager async de contexto
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import select  # Para queries SQL
from sqlalchemy.ext.asyncio import AsyncSession  # Para sesiones async con BD

from app.db import (Post, create_db_and_tables,  # Modelos y funciones BD
                    get_async_session)
from app.images import imagekit  # Cliente de ImageKit
from app.schemas import PostCreate, PostResponse  # Esquemas Pydantic


# Decorador que convierte esta función en un gestor de contexto asincrónico
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar la aplicación"""
    # Esperar a que se creen las tablas en la BD (se ejecuta UNA VEZ al iniciar)
    await create_db_and_tables()
    # Pausar aquí: el servidor comienza a funcionar desde este punto
    yield
    # Cuando se apague el servidor, continúa aquí (limpieza, si fuera necesaria)


# Crear la instancia de FastAPI y pasarle el gestor de ciclo de vida
app = FastAPI(lifespan=lifespan)



# Función auxiliar para clasificar tipos de archivo
def get_file_type(content_type: str) -> str:
    """Determina si el archivo es video o imagen basado en su content_type"""
    # Si el content_type comienza con 'video/', retorna 'video', si no retorna 'image'
    return "video" if content_type.startswith("video/") else "image"


# Función asincrónica que crea un Post en la BD
async def create_post(
    caption: str,              # Descripción del post
    upload_result,             # Resultado de ImageKit con URL y datos
    file_content_type,    # Tipo MIME (image/jpeg, video/mp4, etc)
    session: AsyncSession       # Sesión de la BD para guardar datos
) -> Post:                     # Retorna un objeto Post
    """Crea un nuevo Post en la base de datos"""
    # Crear un nuevo objeto Post con los datos recibidos
    post = Post(
        caption=caption,                              # Guardar la descripción
        url=upload_result.url,                        # URL pública de ImageKit
        file_type=get_file_type(file_content_type),  # Clasificar como image o video
        file_name=upload_result.name                  # Nombre generado por ImageKit
    )
    # Agregar el nuevo Post a la sesión de BD
    session.add(post)
    # Confirmar la transacción (guardar en la BD)
    await session.commit()
    # Refrescar el objeto para obtener el ID y timestamps automáticos
    await session.refresh(post)
    # Retornar el Post creado con todos sus datos
    return post


# Función que convierte un objeto Post a diccionario para la respuesta JSON
def post_to_dict(post: Post) -> dict:
    """Convierte un objeto Post a diccionario"""
    # Retornar un diccionario con todos los campos del Post
    return {
        "id": str(post.id),                    # Convertir ID a string
        "caption": post.caption,               # Descripción del post
        "url": post.url,                       # URL de la imagen/video
        "file_type": post.file_type,           # Tipo: 'image' o 'video'
        "file_name": post.file_name,           # Nombre del archivo
        "created_at": post.created_at.isoformat()  # Fecha en formato ISO
    }


# Endpoint POST para subir archivos
@app.post("/upload")
async def upload(
    file: UploadFile = File(...),                      # Archivo requerido
    caption: str = Form(""),          
    session: AsyncSession = Depends(get_async_session)  # Sesión BD inyectada
):
    """Carga un archivo (imagen o video) a ImageKit y lo guarda en la base de datos"""
    # Inicializar variable para guardar la ruta del archivo temporal
    temp_file_path = None
    try:
        temp_file_path = save_file_temporarily(file) 
        # Leer el archivo temporal
        with open(temp_file_path, "rb") as temp_file:
            file_bytes = temp_file.read()
        
        # Subir a ImageKit - NUEVA SINTAXIS
        # Subir a ImageKit - SEGÚN DOCUMENTACIÓN OFICIAL
        upload_result = imagekit.files.upload(
            file=file_bytes,               # Los bytes del archivo
            file_name=file.filename,       # Nombre del archivo
            folder="/posts",                # Opcional: organiza en carpetas
            tags=["backend-upload"],
            use_unique_file_name=True       # Reemplaza "use_unique_filename"
        )

        # El resultado ya contiene url, file_id, etc.
        print("Subida exitosa:", upload_result.url)
        
        # PASO 3: Guardar metadatos en la base de datos
        # Crear un nuevo Post con la URL de ImageKit
        post = await create_post(caption, upload_result, file.content_type, session)
        # Retornar el Post creado como respuesta JSON
        return post
        
    # Capturar excepciones HTTP y relanzarlas
    except HTTPException:
        raise
    # Capturar cualquier otro error y convertirlo a HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # PASO 4: LIMPIEZA - Se ejecuta SIEMPRE, incluso si hay error
    finally:
        # Eliminar el archivo temporal
        cleanup_temp_file(temp_file_path)
        # Cerrar el archivo subido por el cliente
        file.file.close()


# Función auxiliar que guarda archivos en la carpeta temporal del sistema
def save_file_temporarily(file: UploadFile) -> str:
    """Guarda un archivo en una ubicación temporal y retorna su ruta"""
    # Extraer la extensión del archivo (.jpg, .mp4, etc)
    file_extension = os.path.splitext(file.filename)[1]
    # Crear un archivo temporal con la misma extensión (delete=False = no auto-eliminar)
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        # Copiar el contenido del archivo subido al archivo temporal
        shutil.copyfileobj(file.file, temp_file)
        # Retornar la ruta absoluta del archivo temporal creado
        return temp_file.name


# Función auxiliar para eliminar archivos temporales de forma segura
def cleanup_temp_file(temp_file_path: str) -> None:
    """Elimina el archivo temporal si existe"""
    # Verificar que la ruta NO sea None (si existe una ruta) Y que el archivo exista
    if temp_file_path and os.path.exists(temp_file_path):
        # Eliminar el archivo (unlink = delete en Unix/Linux/Windows)
        os.unlink(temp_file_path)


# Endpoint GET para obtener el feed de posts
@app.get("/feed")
async def get_feed(
    session: AsyncSession = Depends(get_async_session)  # Sesión BD inyectada
):
    """Obtiene el feed de posts ordenados por fecha de creación (más recientes primero)"""
    # Ejecutar query: SELECT * FROM posts ORDER BY created_at DESC (más recientes primero)
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    # Extraer los objetos Post de los resultados (result.all() retorna tuplas)
    posts = [row[0] for row in result.all()]
    
    # Convertir cada Post a diccionario para poder serializar a JSON
    posts_data = [post_to_dict(post) for post in posts]
    # Retornar los posts en formato JSON con clave 'posts'
    return {"posts": posts_data}
   
    
@app.delete("/posts/{post_id}") 
async def delete_post(post_id: str, session: AsyncSession = Depends(get_async_session)):
    try:
        post_uuid = uuid.UUID(post_id)  # Convertir el ID de string a UUID
        result = await session.execute(select(Post).where(Post.id == post_uuid))
        post = result.scalars().first()  # Obtener el Post o None si no existe
        
        if not post:
            raise HTTPException(status_code=404, detail="Post no encontrado")
        
        await session.delete(post)  # Eliminar el Post de la sesión
        await session.commit()  # Confirmar la eliminación en la base de datos
        return {"success": True, "message": "Post eliminado exitosamente"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

