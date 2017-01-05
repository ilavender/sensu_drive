"""
Django settings for sensu_drive project.

Generated by 'django-admin startproject' using Django 1.10.2.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.10/ref/settings/
"""

import os
from django.conf.global_settings import LOGIN_URL

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.10/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'x7r4th^e=s%a)#^r)f5&a_g=t7psux2o37chc=04n3qh=0m_s!'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'isubscribe',
    'channels'
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

ROOT_URLCONF = 'sensu_drive.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sensu_drive.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'sensudrive',
        'USER': 'sensudrive',
        'PASSWORD': 'sensudrive',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/6",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SERIALIZER": "django_redis.serializers.json.JSONSerializer"
        }
    }
}


SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 2592000
#

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "asgi_redis.RedisChannelLayer",
        "CONFIG": {
            #"hosts": ["redis://:password@127.0.0.1:6379/7"],
            "hosts": ["redis://127.0.0.1:6379/7"],
            "symmetric_encryption_keys": [SECRET_KEY],
        },
        "ROUTING": "sensu_drive.routing.channel_routing",
    },
}

# Internationalization
# https://docs.djangoproject.com/en/1.10/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = '/static/'


########################################

STATIC_ROOT = BASE_DIR + '/static_collected'

ALLOWED_HOSTS = ['*']

LOGGING = {
  'version': 1,
  'disable_existing_loggers': False,
  'formatters': {
        'standard': {
            'format' : "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt' : "%d/%b/%Y %H:%M:%S"
        },
    },
  'handlers': {
    'file': {
        'level': 'DEBUG',
        'class': 'logging.FileHandler',
        'filename': BASE_DIR + '/sensu_drive.log',
        'formatter': 'standard'
    },
    'console':{
        'level':'DEBUG',
        'class':'logging.StreamHandler',
        'formatter': 'standard'
    },
  },
  'loggers': {
    'django': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
        'propagate': True,
    },
    'django.template': {
        'handlers': ['console'],
        'level': 'INFO',
        'propagate': False,
    },
    'django.db.backends': {
        'handlers': ['console'],
        'level': 'INFO',
        'propagate': False,
    },
    'isubscribe': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
        'propagate': True,
    },
  },
}

EVENT_DATE_FORMAT = "%d-%m-%Y %H:%M"
API_TOKEN = 'blabla_secret_key'


CACHE_ENTITY_TTL = 3600
CACHE_CLIENT_TTL = 7200
CACHE_CHECK_TTL = 7200
CACHE_TRENDS_TTL = 3600


REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 6
REDIS_POOL_MAX = 10
REDIS_PASSWORD = 'secret'


SENSU_API_URL = 'http://your-server-ip:4567'
SENSU_API_USER = 'username'
SENSU_API_PASSWORD = 'password'

SLACK_BOT_TOKEN = 'secret token from slack'
SLACK_BOT_NAME = 'iSubscribe'
SLACK_BOT_ICON = 'http://mlb-d1-p.mlstatic.com/yoda-star-wars-178311-MLB20539702237_012016-M.jpg'

REGISTRATION_URL_PREFIX = 'https://server.domain.com'

TWILIO_ACCOUNT_SID = "sid string"
TWILIO_AUTH_TOKEN = "token string"
TWILIO_FROM_NUMBER = "numbers only"
TWILIO_CALLBACK_API_TOKEN = 'secret for twilio twiml api'
TWILIO_CALLBACK_URL_PREFIX = 'https://server.domain.com'


ON_DUTY_STATUS_LEVEL = 2
ON_DUTY_CACHE_MEMBERS = 1800

THROTTLING_TWILIO_USER_COUNT = 2
THROTTLING_TWILIO_USER_TTL = 600
THROTTLING_TWILIO_USER_ENTITY_TTL = 3600


ARBITRARY_EVENTS_MIN_OCCURRENCES = 2

########################################

try:
    from sensu_drive.local_settings import *
except ImportError:
    pass

