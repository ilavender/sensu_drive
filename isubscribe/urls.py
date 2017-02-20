from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^settings$', views.user_settings, name='user_settings'),
    url(r'^entities$', views.entities, name='entities'),
    url(r'^events$', views.events, name='events'),
    url(r'^clients$', views.clients, name='clients'),
    url(r'^subscriptions$', views.subscriptions, name='subscriptions'),
    url(r'^whois$', views.whois, name='whois'),
    url(r'^test$', views.test, name='test'),
    url(r'^api/subscribe-toggle', views.subscribe_toggle, name='subscribe_toggle'),    
    url(r'^api/silent-toggle', views.silent_toggle, name='silent_toggle'),
    url(r'^api/alert', views.alert, name='alert'),
    url(r'^api/twilio-say', views.twilio_say, name='twilio_say'),    
    url(r'^api/twilio-status', views.twilio_status, name='twilio_status'),
    url(r'^api/rules', views.ack, name='rules'),
    url(r'^api/ack', views.ack, name='ack'),
    url(r'^api/redo-check', views.redoCheck, name='redoCheck'),
    url(r'^api/resolve', views.resolve, name='resolve'),    
    url(r'^api/check-result', views.check_result, name='check_result'),
    url(r'^api/rmclient', views.rmClient, name='rmclient'),
    url(r'^api/rmresult', views.rmResult, name='rmresult'),
    url(r'^api/entity-history', views.entity_history, name='entity_history'),    
    url(r'^api/entity-notify-history', views.entity_notify_history, name='entity_notify_history'),
    url(r'^api/check-config', views.check_config, name='check_config'),
    url(r'^api/trends', views.trends, name='trends'),
    url(r'^register$', views.register_activate, name='register_activate'),
    url(r'^on-duty$', views.onduty, name='onduty'),
]
