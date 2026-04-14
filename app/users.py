"""Configuración y utilidades relacionadas con usuarios de la API."""
# Módulo estándar para generar identificadores únicos (por ejemplo, IDs de usuario)
import uuid
# Proporciona el tipo Optional para indicar que un valor puede ser None
from typing import Optional

# Importa herramientas de FastAPI para inyección de dependencias y acceso a la petición HTTP
from fastapi import Depends, Request
# Clases principales de fastapi-users para gestionar usuarios con IDs UUID
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (AuthenticationBackend, 
                                          BearerTransport, JWTStrategy) # Para autenticación con JWT
from fastapi_users.db import SQLAlchemyUserDatabase  # Para integrar con SQLAlchemy
from app.db import User, get_user_db  # Modelo de usuario y función para obtener la base de datos de usuarios


SECRET = "SECRET_KEY"  # Clave secreta para firmar los tokens JWT (en producción, usar una más segura y almacenarla de forma segura)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]): 
   reset_password_token_secret = SECRET  # Clave para generar tokens de restablecimiento de contraseña
   verification_token_secret = SECRET  # Clave para generar tokens de verificación de email


async def on_after_register(user: User, request: Optional[Request] = None):
    """Función que se ejecuta después de que un usuario se registra exitosamente."""
    print(f"Usuario registrado: {user.id}")  # Imprime el ID del usuario registrado

async def on_after_forgot_password(user: User, token: str, request: Optional[Request] = None):
    """Función que se ejecuta después de que un usuario solicita restablecer su contraseña."""
    print(f"Usuario {user.id} solicitó restablecer su contraseña. Token: {token}")  # Imprime el ID del usuario y el token generado
    
async def on_after_request_verify(user: User, token: str, request: Optional[Request] = None):
    """Función que se ejecuta después de que un usuario solicita verificar su email."""
    print(f"Usuario {user.id} solicitó verificar su email. Token: {token}")  # Imprime el ID del usuario y el token generado    

async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Función para obtener una instancia de UserManager con la base de datos de usuarios."""
    yield UserManager(user_db)  # Devuelve una instancia de UserManager con la base de datos inyectada  \
        
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")  # Configura el transporte para autenticación con JWT

def get_jwt_strategy() -> JWTStrategy:
    """Función para configurar la estrategia de autenticación JWT."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)  # Configura el JWT con la clave secreta y duración de 1 hora  

auth_backend = AuthenticationBackend(
    name="jwt",  # Nombre del backend de autenticación
    transport=bearer_transport,
    get_strategy=get_jwt_strategy
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])  # Crea una instancia de FastAPIUsers con el UserManager y el backend de autenticación configurados     

current_active_users = fastapi_users.current_user(active=True)  # Dependencia para obtener el usuario actual activo (autenticado)