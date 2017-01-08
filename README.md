[![Docker Automated buil](https://img.shields.io/docker/automated/jrottenberg/ffmpeg.svg)](https://hub.docker.com/r/sensudrive/sensu_drive/builds/)

Sensu Drive
===========

Sensu Drive offers easy way to subscribe for sensu events with integration to your team's slack.
<br>
<br>
along with the continuous delivery methodologies, while the demand of continuous delivery of monitoring in parallel to product delivery is covered by infrastructure as code such as puppet or chef configuring Sensu monitor.
"Sensu Drive" was conceptualized to allow developers to subscribe and unsubscribe to notifications for monitors they or others deployed and to allow Devops/NOC team to recieve notifications for checks that are defining services that they want to wake up at night for.
<br>
the concept suggest that Sensu will decide which event to alert for and "Sensu Drive" will decide who and when to notify.
<br>
<br>
 
- slack integration
  - create account for each user in slack team if not already exist
  - detect slack team members that already have an account
  - registration message/link will be sent to users slackbot
  - notifications to user slackbot

- "On Duty"
  - manage "On Duty" team schedule occurrences
  - manage occurrences members
  - manage members priority
  - issue slack notifications to "On Duty" members
  - issue twilio calls to "On Duty" members by weight until call answer by one of the members

- twilio voice alerts (phone call)
  - issue phone call for escalated events if user contact contain a phone number and no on duty occurence at the time of event
  - throttling prevent calling user for each entity more than once every T time (configurable)
  - throttling prevent calling a user more than X count in T time (configurable)
  - issue phone call to the "On Duty" team for all alerts (ON_DUTY_STATUS_LEVEL configurable)

- events view
  - list of events using websockets updates at real time
  - acknowledge action, sends comment to all entity's subscribers
  - silent
  - resolve, resolve check using Sensu API
  - display events history (last 100 events)
  - display notifications history for each event (last 100 notifications)
  - display events config (none standalone checks)
  - events are in format of client:check

- entities view
  - user can subscribe for warning, critical or both alerts for each entity
  - recovery will be sent only to subscribers that got an alert for that entity
  - display events history (last 100 events)
  - display notifications history for each entity (last 100 notifications)
  - display events config (none standalone checks)
  - delete check result from Sensu API
  - entities are in format of client:check

- clients view
  - list all clients and their metadata
  - delete client, decommission using Sensu API

- subscriptions view
  - list all subscriptions and their clients

- events escalator
  - while no "On Duty" and event was not acknowledged, if event status is critical and event histoy is critical twice or more (in a row)

- "DnD" do not disturb
  - manage "DnD" user schedule occurrences
  - "On Duty" notifications ignore "DnD"

<br>
<br>

# Requirements

python3
<br>
postgresql-9.5
<br>
redis-server
<br>
postgresql-server-dev-9.5 
<br>
python-dev
<br>
python3-dev
<br>
python3-cryptography
<br>
<br>
pip install -r requirements.txt
<br>
<br>
Slack team account (free) and token
<br>
you can use your test token but for real production deployment having a dedicated bot user is recommended.
<br>
https://api.slack.com/docs/oauth-test-tokens
<br>
https://api.slack.com/bot-users


# Install/Configure

- create database

- create file sensu_drive/local_settings.py, this next is only example. all settings in sensu_drive/settings.py can be changed in sensu_drive/local_settings.py
	```
	from django.conf import settings


	DEBUG = True

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
		"LOCATION": "redis://:redis_authentication_passwd@127.0.0.1:6379/6",
		"OPTIONS": {
		    "CLIENT_CLASS": "django_redis.client.DefaultClient",
		    "SERIALIZER": "django_redis.serializers.json.JSONSerializer"
		}
	    }
	}

	CHANNEL_LAYERS = {
	    "default": {
		"BACKEND": "asgi_redis.RedisChannelLayer",
		"CONFIG": {
		    "hosts": ["redis://:redis_authentication_passwd@127.0.0.1:6379/7"],
		    "symmetric_encryption_keys": [settings.SECRET_KEY],
		},
		"ROUTING": "sensu_drive.routing.channel_routing",
	    },
	}

	REDIS_PASSWORD = 'redis_authentication_passwd'

	SENSU_API_URL = 'https://server.domain.com'
	SENSU_API_USER = 'sensu-api-user'
	SENSU_API_PASSWORD = 'sensu-api-password'

	API_TOKEN = 'secret for isubscribe sensu handler'
	SLACK_BOT_TOKEN = 'your-slack-api-token'

	REGISTRATION_URL_PREFIX = 'http://127.0.0.1:8080'

	TWILIO_ACCOUNT_SID = "sid string"
	TWILIO_AUTH_TOKEN = "token string"
	TWILIO_FROM_NUMBER = "numbers only"
	TWILIO_CALLBACK_API_TOKEN = 'secret for twilio twiml api'

	```


- prepare database.
	```
	python manage.py migrate
	```


- create admin user.
	```
	python manage.py createsuperuser
	```

- collect static files.
	```
	python manage.py collectstatic --noinput
	```


- create file circus.ini, change env_path to your python3 virtualenv root.
	````
	[circus]
	check_delay = 5

	[watcher:webworker]
	cmd = daphne --fd $(circus.sockets.webapp) sensu_drive.asgi:channel_layer
	use_sockets = True
	numprocesses = 1
	copy_env = True
	virtualenv = $(circus.env.env_path)


	[watcher:runworker]
	cmd = python manage.py runworker
	numprocesses = 2
	copy_env = True
	virtualenv = $(circus.env.env_path)


	[watcher:runjobs]
	cmd = python manage.py jobs
	numprocesses = 1
	copy_env = True
	virtualenv = $(circus.env.env_path)


	[socket:webapp]
	host = 127.0.0.1
	port = 8080


	[env]
	env_path = /opt/sandbox3/
	````


# Running
- daemon (all in one)
	```
	circusd --daemon circus.ini
	```

- frontend
	```
	daphne sensu_drive.asgi:channel_layer --port 8080
	```

- worker
	```
	python manage.py runworker
	```


- scheduled jobs process
	```
	python manage.py jobs
	```

# Sensu Handler
- copy the file ext/isubscribe.rb to /usr/local/sbin/ or any other path on your sensu server(s) and make it executable, this will be used as the sensu handler.

- configure sensu handler like the following example:
	```
	{
	  "handlers": {
	    "isubscribe": {
	      "command": "/usr/local/sbin/isubscribe.rb",
	      "type": "pipe",
	      "severities": [
		"warning",
		"critical",
		"unknown",
		"ok"
	      ]
	    }
	  },
	  "isubscribe": {
	    "server_uri": "http://127.0.0.1:8080/isubscribe/api/alert",
	    "api_token": "secret for isubscribe sensu handler see local_settings"
	  }
	}
	```

- make sure handler /usr/local/sbin/isubscribe.rb is executable and reload sensu server.




# Usage

- sync with slack. this will create account for all users in slack team. unless DEBUG = True, registration message/link will be sent to their slackbot. make sure you set REGISTRATION_URL_PREFIX right in your local_settings before running slack detect.
	```
	python manage.py slack_detect
	```
- fetch all current events from sensu (should be excuted only once after every restart).
	```
	python manage.py update_events
	```
- fetch all current checks from sensu (part of scheduled job).
	```
	python manage.py update_checks
	```
- fetch all current clients from sensu (part of scheduled job).
	```
	python manage.py update_clients
	```
- fetch all current checks from sensu and build cached list of entities (part of scheduled job).
	```
	python manage.py update_entities
	```

# Reverse Proxy
- nginx
	```
	server {
	 listen 443 ssl;
	 server_name isubscribe.domain.com;
	 client_max_body_size 200M;

	 ssl on;
	 ssl_certificate /path_to_server_certificate.crt;
	 ssl_certificate_key /path_to_server_key.key;

	  ## static files (path should be changed)
	  location /static/ {
	    autoindex off;
	    alias /opt/sensudrive/static_collected/;
	  }

	  ## ui
	  location / {
	    proxy_pass http://127.0.0.1:8080;
	    proxy_http_version 1.1;
	    proxy_set_header Upgrade $http_upgrade;
	    proxy_set_header Connection "upgrade";
	    proxy_set_header Host $host;
	  }

	}
	```






# License

- The MIT License (MIT)
- Copyright (c) 2016 &#60;Itamar Lavender itamar.lavender@gmail.com&#62;
	```
	Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

	The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
	```
