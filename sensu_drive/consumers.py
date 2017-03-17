from django.conf import settings
from django.core.cache import cache

from channels import Channel, Group
from channels.sessions import channel_session, enforce_ordering
from channels.auth import http_session_user, channel_session_user, channel_session_user_from_http
from channels.handler import AsgiHandler, AsgiRequest

from isubscribe.tasks import alert_rules, sensu_entity_list, sensu_event_list, slack_user_detect, slack_user_nag, user_register, alert_handler, ack_handler, sensu_client_list, alert_history, sensu_check_list, notify_history, trends_build, user_rules
from isubscribe.models import Subscribe
from isubscribe.views import entities
from isubscribe.notify import Notify

import json, datetime, re

import logging
logger = logging.getLogger('isubscribe.consumers')



# Listens on http.request (example - not in use)
@channel_session
def http_consumer(message):
    #channel_session_user = True
    #http_user = True
    # Decode the request from message format to a Request object
    django_request = AsgiRequest(message)
    # Run view
    django_response = entities(django_request)
    # Encode the response into message format
    for chunk in AsgiHandler.encode_response(django_response):
        message.reply_channel.send(chunk)        

        

def user_register_job(message):
    logger.info('slack_user_detect begin')
    user_register(message)
    logger.info('slack_user_detect completed')



def slack_detect(message):
    logger.info('slack_user_detect begin')
    slack_user_detect()
    logger.info('slack_user_detect completed')

    

def slack_nag(message):
    logger.info('slack_user_nagg begin')
    slack_user_nag(message)
    logger.info('slack_user_nagg completed')
    
            

def build_rules(message):
    logger.info('alert_rules begin')
    alert_rules()
    logger.info('alert_rules completed')



def update_entities(message):
    logger.info('sensu_entity_list begin')
    sensu_entity_list()
    logger.info('sensu_entity_list completed')
    


def update_events(message):
    logger.info('sensu_event_list begin')
    sensu_event_list()
    logger.info('sensu_event_list completed')
    


def update_clients(message):
    logger.info('update_clients begin')
    sensu_client_list()
    logger.info('update_clients completed')


def update_checks(message):
    logger.info('update_checks begin')
    sensu_check_list()
    logger.info('update_checks completed')


def update_trends(message):
    logger.info('update_trends begin')
    trends_build()
    logger.info('update_trends completed')

#@enforce_ordering(slight=True)
def escalator(message):
    logger.debug('escalator message = %s', message)
    
    
    
#@enforce_ordering(slight=True) 
def build_entity_rules(message):
    logger.info('building_entity_rules begin: %s' % message['entity'])
    entity_status_friends = {}
    
    for obj in Subscribe.objects.filter(entity=message['entity']).all():        
        if obj.status not in entity_status_friends:
            entity_status_friends[obj.status] = []        
        for user in obj.friends.all():
            entity_status_friends[obj.status].append(user.pk)
            
    cache.set('rule_' + obj.entity, entity_status_friends, timeout=None)
    logger.info('build_entity_rules completed: %s' % message['entity'])



def build_user_rules(message):
    logger.info('building_user_rules begin user_id: %s' % message['user_id'])
    user_rules(message)
    logger.info('building_user_rules completed user_id: %s' % message['user_id'])

#@enforce_ordering(slight=True)
def notifier_hisotry(message):
    logger.info('notifier_hisotry consumer: %s' % message['entity'])
    notify_history(message)
    


#@enforce_ordering(slight=True)
def alert(message):
    
    try:
        logger.info('alert consumer - entity: %s status: %s output: %s occurrences: %s' % (message['entity'], message['status'], message['output'], message['occurrences']))
    except:
        pass
    
    silenced = False
    silent_by = ''
    silent_comment = ''
    acked = False
    ack_by = ''
    ack_comment = ''    
    
    if int(message['status']) != 0 and 'ack_' + message['entity'] in cache.keys("ack_*"):
        ack = cache.get('ack_' + message['entity'])
        ack_by = ack['user_name']
        ack_comment = ack['ack_comment']
        acked = True
        
    if 'silent_' + message['entity'] in cache.keys("silent_*"):    
        silent = cache.get('silent_' + message['entity'])
        silent_by = silent['user_name']
        silent_comment = silent['silent_comment']
        silenced = True    
    
        
    Group("notifications").send({
        "text": json.dumps({
            "timestamp": message['timestamp'],
            "entity": message['entity'],
            "status": message['status'],
            "output": message['output'],
            "ack": acked,
            "ack_by": ack_by,
            "ack_comment": ack_comment,
            "silent": silenced,
            "silent_by": silent_by,
            "silent_comment": silent_comment
        })
    })
    
    if int(message['status']) == 0:
        cache.delete("event_" + message['entity'])
        if 'ack_' + message['entity'] in cache.keys("ack_*"):                
            cache.delete('ack_' + message['entity'])
    else:
        client_name, check_name = message['entity'].split(':')
        event_data = {
            'timestamp': int(message['timestamp']),
            'client': {
                'name': client_name              
            },
            'check': {
                'name': check_name,
                'status': int(message['status']),
                'output': message['output']
            },
        }
        cache.set("event_" + message['entity'], event_data, timeout=None)
    
    alert_history(message)
    
    if silenced == False and acked == False:
        logger.debug('alert consumer -  sending to alert_handler - entity: %s status: %s output: %s' % (message['entity'], message['status'], message['output']))
        alert_handler(message)
    else:
        logger.info('alert consumer - skipping handler for acknowledged entity: %s status: %s output: %s occurrences: %s' % (message['entity'], message['status'], message['output'], message['occurrences']))
        


#@enforce_ordering(slight=True)
def onduty_handler(message):
    
    notifier = Notify(message)
    
    if int(message['status']) >= settings.ON_DUTY_STATUS_LEVEL:
        notifier.notify_onduty()
        
    elif int(message['status']) == 0:
        if 'history' in message:
            message['history'].pop()          
            for i in range(len(message['history']), 0, -1):
                if int(message['history'][i-1]) == 0:
                    break
                if int(message['history'][i-1]) >= settings.ON_DUTY_STATUS_LEVEL:
                    notifier.notify_onduty()
 


#@enforce_ordering(slight=True)
def ack(message):
    logger.info('ack begin')
    ack_handler(message)
    logger.info('ack completed')
   
 
    
# Connected to websocket.connect and websocket.keepalive
@channel_session_user_from_http
def websocket_connect_events(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    message.channel_session['username'] = message.user.username    
    #message.http_session.set_expiry(3600)

    logger.debug('websocket_connect_events. user: %s path: %s' % (message.user, message.content['path']))    
    Group("notifications").add(message.reply_channel)
    Group("announcement").add(message.reply_channel)
    message.reply_channel.send({"accept": True})



# Connected to websocket.keepalive
@channel_session_user
def websocket_keepalive_events(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_keepalive_events. message = %s', message)
    Group("notifications").add(message.reply_channel)
    Group("announcement").add(message.reply_channel)



# Connected to websocket.disconnect
@channel_session_user
def websocket_disconnect_events(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_disconnect_events. message = %s', message.user)
    Group("notifications").discard(message.reply_channel)
    Group("announcement").discard(message.reply_channel)
    
    
    
# Connected to websocket.connect and websocket.keepalive
@channel_session_user_from_http
def websocket_connect_entities(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_connect_entities. user = %s', message.user)
    Group("entities-private-%s" % message.user.id).add(message.reply_channel)
    Group("announcement").add(message.reply_channel)
    message.reply_channel.send({"accept": True})
    
    

# Connected to websocket.keepalive
@channel_session_user
def websocket_keepalive_entities(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_keepalive_entities. message = %s', message.user)
    Group("entities-private-%s" % message.user.id).add(message.reply_channel)
    Group("announcement").add(message.reply_channel)



# Connected to websocket.disconnect
@channel_session_user
def websocket_disconnect_entities(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_events. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_disconnect_entities. message = %s', message.user)
    Group("entities-private-%s" % message.user.id).discard(message.reply_channel)
    Group("announcement").discard(message.reply_channel)



# Connected to websocket.connect and websocket.keepalive
@channel_session_user_from_http
def websocket_connect_onduty(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_connect_onduty. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_connect_events. user = %s', message.user)
    Group("on-duty").add(message.reply_channel)
    Group("announcement").add(message.reply_channel)
    message.reply_channel.send({"accept": True})

# Connected to websocket.keepalive
@channel_session_user
def websocket_keepalive_onduty(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_keepalive_onduty. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_keepalive_events. message = %s', message)
    Group("on-duty").add(message.reply_channel)
    Group("announcement").add(message.reply_channel)


# Connected to websocket.disconnect
@channel_session_user
def websocket_disconnect_onduty(message):
    
    if not message.user.is_authenticated():
        logger.error('websocket_disconnect_onduty. user = %s is NOT authenticated', message.user)
        return
    
    logger.debug('websocket_disconnect_events. message = %s', message.user)
    Group("on-duty").discard(message.reply_channel)
    Group("announcement").discard(message.reply_channel)
    
    