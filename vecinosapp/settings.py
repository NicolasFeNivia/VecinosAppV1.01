import os
from pathlib import Path

from django.contrib.messages import constants as messages

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-vecinosapp-clave-solo-para-practicar'

DEBUG = True

ALLOWED_HOSTS = []


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'incidencias',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'vecinosapp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'incidencias.context_processors.rol',
            ],
        },
    },
]

WSGI_APPLICATION = 'vecinosapp.wsgi.application'


# Por defecto usa SQLite (sirve para M1). Desde M2 se necesita PostgreSQL:
# define la variable de entorno DB_ENGINE=postgres (ver docker-compose.yml).
if os.environ.get('DB_ENGINE', 'sqlite') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'vecinosapp'),
            'USER': os.environ.get('DB_USER', 'vecinos'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'vecinos'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'incidencia_lista'
LOGOUT_REDIRECT_URL = 'login'

MESSAGE_TAGS = {messages.ERROR: 'danger'}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'vecinosapp@ejemplo.com'


# =====================================================================
# M4 (API) y M5 (eventos y asincronía): bloque añadido, no modifica lo anterior
# =====================================================================
from datetime import timedelta  # noqa: E402

INSTALLED_APPS += [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'eventos',
    'api',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'api.excepciones.manejador',
    'DEFAULT_THROTTLE_CLASSES': [
        'api.throttles.ThrottleUsuario',
        'api.throttles.ThrottleEdificio',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'usuario': '120/min',    # por usuario (o por IP si es anónimo)
        'edificio': '600/min',   # compartido por todos los usuarios de un edificio
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,        # cada refresh entrega un refresh nuevo...
    'BLACKLIST_AFTER_ROTATION': True,     # ...y el anterior deja de servir
    'UPDATE_LAST_LOGIN': False,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'VecinosApp API',
    'DESCRIPTION': (
        'API versionada de incidencias. Autenticación JWT (`/api/v1/auth/token/`). '
        'Los POST aceptan la cabecera `Idempotency-Key`; los GET devuelven `ETag`. '
        'Los webhooks se firman con HMAC-SHA256 (cabecera `X-Vecinos-Signature`).'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Celery + Redis (M5). CELERY_EAGER=1 ejecuta las tareas en el mismo proceso (sin Redis).
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_ALWAYS_EAGER = os.environ.get('CELERY_EAGER', '0') == '1'
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# =====================================================================
# M6 (tiempo real y panel): bloque añadido, no modifica lo anterior
# =====================================================================
INSTALLED_APPS.insert(0, 'daphne')   # primero: hace que runserver sirva ASGI (WebSockets)
INSTALLED_APPS += ['channels', 'tiempo_real']

ASGI_APPLICATION = 'tiempo_real.asgi.application'

# Desarrollo: capa en memoria (un solo proceso). Producción: define CHANNEL_REDIS_URL.
if os.environ.get('CHANNEL_REDIS_URL'):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [os.environ['CHANNEL_REDIS_URL']]},
        }
    }
else:
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
