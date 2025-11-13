# settings.py
from pathlib import Path
import os
from dotenv import load_dotenv
import django_plotly_dash
import dash_bootstrap_components

load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY') # Esto ya está perfecto

# SECURITY WARNING: don't run with debug turned on in production!
# <-- CAMBIO AQUÍ: Hacemos DEBUG dinámico
# En local, .env no tendrá 'DEBUG', así que será 'True'. En AWS, la pondremos en 'False'.
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# <-- CAMBIO AQUÍ: Hacemos ALLOWED_HOSTS dinámico
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
# Añadimos el host de Elastic Beanstalk si existe
if 'EB_HOST' in os.environ:
    ALLOWED_HOSTS.append(os.environ.get('EB_HOST'))


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'Analyzer.apps.AnalyzerConfig',
    'django_plotly_dash',
    'dash_bootstrap_components',
    'storages',  # <-- CAMBIO AQUÍ: Añadimos django-storages para S3
]

# settings.py

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    #'django.middleware.clickjacking.XFrameOptionsMiddleware', # Lo dejamos como lo tenías
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django_plotly_dash.middleware.ExternalRedirectionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'cardiac_analyzer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'cardiac_analyzer.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# <-- CAMBIO AQUÍ: Lógica condicional para la Base de Datos
DB_HOST = os.environ.get('DB_HOST')

if DB_HOST:
    # --- Configuración de PRODUCCIÓN (AWS RDS) ---
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASS'),
            'HOST': DB_HOST,
            'PORT': '5432',
        }
    }
else:
    # --- Configuración LOCAL (Desarrollo) ---
    # Esto es lo que ya tenías
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/
# ... (Sin cambios aquí) ...
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I1N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

# <-- CAMBIO AQUÍ: Lógica condicional para Estáticos (S3 vs Local)
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')

if AWS_STORAGE_BUCKET_NAME:
    # --- Configuración de PRODUCCIÓN (AWS S3) ---
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1') # Pon tu región
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False # Seguridad

    # Para archivos estáticos (CSS, JS)
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    # Para archivos de media (los CSVs que subas)
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    # Mantenemos tus configuraciones originales
    STATICFILES_DIRS = [ BASE_DIR / 'static' ]
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    STATICFILES_FINDERS = [
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder', 
    ]

else:
    # --- Configuración LOCAL (Desarrollo) ---
    # Esto es lo que ya tenías
    STATICFILES_DIRS = [ BASE_DIR / 'static' ]
    STATIC_URL = 'static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'

    STATICFILES_FINDERS = [
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder', 
    ]
    
    # Añadimos Media para local
    MEDIA_URL = 'media/'
    MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Mantenemos tus settings de Plotly
PLOTLY_DASH = {
    "serve_locally": False, 
    "view_name": "django_plotly_dash:app-view",
}
# Mantenemos tu límite de subida
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024