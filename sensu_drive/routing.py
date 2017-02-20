from django.conf import settings
from django.urls import reverse

from channels.routing import route
from .consumers import *


channel_routing = [
    route('websocket.connect', websocket_connect_events, path=reverse('events')),
    route('websocket.keepalive', websocket_keepalive_events, path=reverse('events')),
    route('websocket.disconnect', websocket_disconnect_events, path=reverse('events')),
    route('websocket.connect', websocket_connect_entities, path=reverse('entities')),
    route('websocket.keepalive', websocket_keepalive_entities, path=reverse('entities')),
    route('websocket.disconnect', websocket_disconnect_entities, path=reverse('entities')),
    route('websocket.connect', websocket_connect_onduty, path=reverse('onduty')),
    route('websocket.keepalive', websocket_keepalive_onduty, path=reverse('onduty')),
    route('websocket.disconnect', websocket_disconnect_onduty, path=reverse('onduty')),
    route('background-update-trends', update_trends),
    route('background-build-rules', build_rules),
    route('background-update-clients', update_clients),
    route('background-update-checks', update_checks),
    route('background-update-entities', update_entities),
    route('background-update-events', update_events),
    route('background-build-entity-rules', build_entity_rules),
    route('background-build-user-rules', build_user_rules),
    route('background-alert', alert),    
    route('background-notify-history', notifier_hisotry),
    route('background-ack', ack),
    route('background-slack-detect', slack_detect),
    route('background-slack-nag', slack_nag),
    route('background-register-user', user_register_job),
    route('background-onduty', onduty_handler)
]