from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse_lazy
from django.db.models.fields import Empty

import urllib3, base64, json, random, string, re, datetime
import codecs
import redis
import pickle
import numpy as np
import pandas as pd


from channels import Channel, Group
from slacker import Slacker

from isubscribe.models import Subscribe, Contact
from isubscribe.notify import register_email
from isubscribe.notify import Notify
from isubscribe.escalator import escalator as Escalator



http = urllib3.PoolManager(maxsize=10)
slack = Slacker(settings.SLACK_BOT_TOKEN)

redis_pool = redis.ConnectionPool(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, max_connections=settings.REDIS_POOL_MAX, password=settings.REDIS_PASSWORD)
r = redis.Redis(connection_pool=redis_pool)


import logging
logger = logging.getLogger(__name__)




def passwd_generator(size=25):
    chars=string.ascii_uppercase + string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for x in range(size,size+size))



def y_predict(x_arr, y_arr, x_future):
    x_np = np.array(x_arr)
    y_np = np.array(y_arr)

    A = np.vstack([x_np, np.ones(len(x_np))]).T
    m, c = np.linalg.lstsq(A, y_np)[0]
    
    x_arr.append(x_future)
    x_future_arr_np = np.array(x_arr)

    y_future_arr = m*x_future_arr_np + c

    return y_future_arr[-1]


def y_sum_by_time(x_arr, y_arr, top=None):
    df = pd.DataFrame({'Timestamp': pd.to_datetime(x_arr, unit='s'), 'Status': y_arr})
    df['Date'] = df['Timestamp'].apply(lambda x: "%d/%d/%d" % (x.day, x.month, x.year))
    df['Hour'] = df['Timestamp'].apply(lambda x: "%d" % (x.hour))
    df['Weekday'] = df['Timestamp'].apply(lambda x: "%s" % (x.weekday_name))
    
    times = ['Hour', 'Weekday', 'Date']
    
    result = {}
    
    for groupby in times:
        
        df_group = df.groupby(groupby, as_index=False).agg({'Status': np.sum})
        
        if top != None and top > 0:
            #df_group = df_group.nlargest(top, 'Status').sort(['Status', 'Hour'],ascending=False)
            idx = df_group.nlargest(top, 'Status') > 0
        else:
            idx = df_group['Status'].max() == df_group['Status']
                
        result[groupby] = {k: g['Status'].replace(np.nan, 'None').tolist() for k,g in df_group[idx].groupby(groupby)}
            
    return result



def trends_build():
        
    data = []            

    for word in r.keys(pattern='history_entity_*'):
        x = []
        y = []
        
        name = word.decode('utf-8')
        entity = re.sub(r'^history_entity_', '', name)
        
        if 'entity_' + entity not in cache.keys("entity_*"):
            continue
                
        
        try:
            i = 0
            for history_data in r.lrange(name, 0, -1):
                                
                obj = pickle.loads(history_data)
                
                if 'history' not in obj or 'timestamp' not in obj:
                    continue
                
                x.append(obj['timestamp'])
                y.append(int(obj['status']))
                
                ts = obj['timestamp']                
                for status in obj['history']:
                    ts = ts + 60               
                    x.append(ts)
                    y.append(int(status))

                
            NOW = datetime.datetime.now().timestamp()        
        
            x_len = len(x)
            y_len = len(y)
        
            if x_len >= 500 or settings.DEBUG == True:
                
                ts = x[0]
                status = y[0]
                                            
                if ts < (NOW - 86400*10) and settings.DEBUG == False:
                    continue            
                elif ts < (NOW - 86400*7) and status == 0 and settings.DEBUG == False:
                    continue
                else:                
                    x.append(NOW)
                    y.append(status)                
                                        
                    
                    trend_top3 = y_sum_by_time(x, y, top=3)
                    score = y_predict(x, y, NOW + 86400)                    
                    
                    if score < 0.5:
                        predict = 0
                    elif score >= 0.5 and score < 1.5:
                        predict = 1                        
                    elif score >= 1.5 and score < 2.5:
                        predict = 2
                    else:
                        predict = 3
                    
                    if predict > 0 or settings.DEBUG == True:
                        confident = "{0:.0f}".format(100 - (abs(score - predict) * 100))
                        data.append({'entity': entity, 
                                     'trend_score': score, 
                                     'last_event_age_days': "{0:.2f}".format((NOW - ts)/86400),
                                     'last_event_timestamp': ts,
                                     'last_event_status': status,
                                     'trend_status': predict, 
                                     'confident_percent': confident,
                                     'trend_top3': trend_top3
                                     })

        except:
            logger.error('failed %s' % name)
            pass
          
    cache.set('trends_all', data, timeout=settings.CACHE_TRENDS_TTL + 300)
                
    return



def sensu_event_resolve(message):
    
    API_URL = settings.SENSU_API_URL + '/resolve'
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        client_name, check_name = message['entity'].split(':')
        post_params = {"client": client_name, "check": check_name}
        request = http.request('POST', API_URL, body=json.dumps(post_params), headers=headers)   
        response = request.status
                
        if response == 202:
            #reader = codecs.getreader('utf-8')
            #data = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
    
    except:
        logger.error("sensu_event_resolve failed resolving entity: %s" % message['entity'])
        raise
        

def sensu_client_delete(message):
    
    API_URL = settings.SENSU_API_URL + '/clients/' + message['client']
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        request = http.request('DELETE', API_URL, headers=headers)   
        response = request.status
                
        if response == 202:
            request.release_conn()
            return True
        else:
            logger.error("sensu_client_delete api request failed: %s" % str(response))
            return False
    except:
        logger.error("sensu_client_delete failed deleting client: %s" % message['client'])
        raise



def sensu_result_delete(message):
    
    API_URL = settings.SENSU_API_URL + '/results/' + message['client'] + '/' + message['check']
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        request = http.request('DELETE', API_URL, headers=headers)   
        response = request.status
                
        if response == 204:
            request.release_conn()
            return True
        else:
            logger.error("sensu_result_delete api request failed: %s" % str(response))
            return False
    except:
        logger.error("sensu_result_delete failed deleting client: %s check: %s" % (message['client'], message['check']))
        raise



def sensu_client_list():
    
    API_URL = settings.SENSU_API_URL + '/clients'
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        
        request = http.request('GET', API_URL, None, headers, preload_content=False)        
        response = request.status
                
        if response == 200:
            reader = codecs.getreader('utf-8')
            data = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
            
    except:
        logger.error("sensu_client_list failed")
        raise
    
    subscriptions = []
    
    [ r.delete(subscription) for subscription in r.keys("subscription_*") ]
    #[ cache.delete(client) for client in cache.keys("client_*") ]
    
    for object in data:
        
        cache.set('client_' + object['name'], object, timeout=settings.CACHE_CLIENT_TTL + 300)
        
        if 'subscriptions' in object:            
            subscriptions.extend(object['subscriptions'])
            
            for subscription in object['subscriptions']:                
                logger.debug("sensu_client_list update subscription_%s adding %s" % (subscription, object['name']))
                r.rpush('subscription_' + subscription, object['name'])
            
    cache.set('subscriptions', list(set(subscriptions)), timeout=settings.CACHE_CLIENT_TTL + 300)
        


        
def sensu_check_list():
    
    API_URL = settings.SENSU_API_URL + '/checks'
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        
        request = http.request('GET', API_URL, None, headers, preload_content=False)        
        response = request.status
                
        if response == 200:
            reader = codecs.getreader('utf-8')
            data = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
            
    except:
        logger.error("sensu_check_list failed")
        raise
    
    for object in data:
        logger.debug("sensu_check_list update check: %s" % object['name'])     
        cache.set('check_' + object['name'], object, timeout=settings.CACHE_CHECK_TTL + 300)
                

                
                
def sensu_entity_list():
    
    API_URL = settings.SENSU_API_URL + '/results'
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        
        request = http.request('GET', API_URL, None, headers, preload_content=False)        
        response = request.status 
               
        if response == 200:
            reader = codecs.getreader('utf-8')
            data = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
            
    except:
        logger.error("sensu_entity_list failed")
        raise
    
    subscribers = []
    
    for object in data:
        
        client = object['client']
        check = object['check']['name']
        entity = client + ':' + check
        
        logger.debug("sensu_entity_list insert entity %s" % entity)
                
        cache.set('entity_' + client + ':' + check, object['check'], timeout=settings.CACHE_ENTITY_TTL + 300)
        cache.set('check_' + check, object['check'], timeout=settings.CACHE_CHECK_TTL + 300)
        
        if 'subscribers' in object['check']:
            subscribers.extend(object['check']['subscribers'])
    
    cache.set('subscribers', list(set(subscribers)), timeout=settings.CACHE_ENTITY_TTL + 300)
        




def sensu_event_list():
    
    logger.debug('sensu_event_list task')
    API_URL = settings.SENSU_API_URL + '/events'
    userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
    headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Authorization' : 'Basic %s' %  userAndPass }
            
    try:
        
        request = http.request('GET', API_URL, None, headers, preload_content=False)        
        response = request.status
                
        if response == 200:
            reader = codecs.getreader('utf-8')
            data = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
        
    except:
        logger.error("sensu_event_list failed")
        raise
    
    [cache.delete(event) for event in cache.keys("event_*")]
        
    Group("notifications").send({
        "text": json.dumps({'clean_signal':True})
    })
    
    for object in data:
        
        if 'handle' in object['check'] and object['check']['handle'] == False:
            continue
         
        if 'occurrences' in object['check']:
            alert_occurrences = object['check']['occurrences']
        else:
            # not sure what to decide     
            alert_occurrences = settings.ARBITRARY_EVENTS_MIN_OCCURRENCES
            #continue
            
            
        if object['check']['status'] > 0 and object['occurrences'] >= alert_occurrences and object['silenced'] == False:
            
            logger.debug('sensu_event_list task found event for entity: %s' % object['client']['name'] + ':' + object['check']['name'])
            entity = object['client']['name'] + ':' + object['check']['name']
            cache.set('event_' + entity, object, timeout=None)
            silenced = False
            silent_by = ''
            silent_comment = ''
            acked = False
            ack_by = ''
            ack_comment = ''            
            
            if 'ack_' + entity in cache.keys("ack_*"):
                ack = cache.get('ack_' + entity)
                ack_by = ack['user_name']
                ack_comment = ack['ack_comment']
                acked = True
                
            if 'silent_' + entity in cache.keys("silent_*"):
                silent = cache.get('silent_' + entity)
                silent_by = silent['user_name']
                silent_comment = silent['silent_comment']
                silenced = True
                
            Group("notifications").send({
                "text": json.dumps({
                    "timestamp": object['timestamp'],
                    "entity": entity,
                    "status": int(object['check']['status']),
                    "output": object['check']['output'],
                    "ack": acked,
                    "ack_by": ack_by,
                    "ack_comment": ack_comment,
                    "silent": silenced,
                    "silent_by": silent_by,
                    "silent_comment": silent_comment
                    
                })
            })
        




def alert_rules():
    
    ents = {}
    
    try:
    
        for obj in Subscribe.objects.all():
        
            entity_status_friends = {}
            
            if obj.entity not in ents:
                ents[obj.entity] = {}
            if obj.status not in ents[obj.entity]:
                ents[obj.entity][obj.status] = []        
            for user in obj.friends.all():
                ents[obj.entity][obj.status].append(user.pk)
    except:
        logger.error("alert_rules failed")
        raise
    
    for entity in ents:
        
        logger.debug("alert_rules build rule for entity: %s" % entity)
        cache.set('rule_' + entity, ents[entity], timeout=None)
        


def alert_history(message):    
    logger.debug("alert_history append alert for entity: %s" % message['entity'])
    try:
        entity_history_cache_key = 'history_entity_' + message['entity'] 
        r.lpush(entity_history_cache_key, pickle.dumps(dict(message)))
    except:
        logger.error("alert_history failedmessage: %s" % json.dumps(message))
        raise



def notify_history(message):    
    logger.debug("notify_history append alert for entity: %s" % message['entity'])
    
    try:
        history_cache_key = 'notifyhistory_entity_' + message['entity'] 
        r.lpush(history_cache_key, pickle.dumps(dict(message)))
    except:
        logger.error("notify_history failed message: %s" % json.dumps(message))
        raise
    




def alert_handler(message):    
    
    logger.debug("alert_handler handling alert for entity: %s" % message['entity'])
    notifier = Notify(message)
    
    #Channel('background-onduty').send(dict(message))
    if int(message['status']) >= settings.ON_DUTY_STATUS_LEVEL:
        notifier.notify_onduty()
        
    elif int(message['status']) == 0:
        if 'history' in message:
            ev_history = list(message['history'])
            ev_history.pop()          
            for i in range(len(ev_history), 0, -1):
                if int(ev_history[i-1]) == 0:
                    break
                if int(ev_history[i-1]) >= settings.ON_DUTY_STATUS_LEVEL:
                    notifier.notify_onduty()
                    break   
                                        
    
    if 'rule_' + message['entity'] in cache:
        
        logger.debug("alert_handler found rule for entity: %s" % message['entity'])
        
        rule = cache.get('rule_' + message['entity'])
        
        if int(message['status']) == 0:
            
            history_notify = []
            
            if 'history' in message:                
                # looking for users that might have got previous alerts, the same people should get recovery
                recovery = False
                message['history'].pop()                
                for i in range(len(message['history']), 0, -1):
                    last_status = message['history'][i-1]
                    if int(last_status) == 0:
                        break
                    recovery = True           
                    if str(last_status) in rule:
                        for user_pk in rule[str(last_status)]:
                            if user_pk not in history_notify: 
                                history_notify.append(user_pk)
                if recovery:
                    logger.debug("alert_handler RECOVERY entity: %s status: %s" % (message['entity'], str(message['status'])))                
            else:
                # not sure this is required at all but fallback if no history exist
                if '1' in rule:
                    for user_pk in rule['1']:
                            if user_pk not in history_notify: 
                                history_notify.append(user_pk)
                if '2' in rule:
                    for user_pk in rule['2']:
                            if user_pk not in history_notify:
                                history_notify.append(user_pk)
                                
            for user_pk in history_notify:
                logger.debug("alert_handler notify_slack user: %s entity: %s status: %s" % (str(user_pk), message['entity'], str(message['status'])))
                notifier.notify_slack(user_pk)
                  
            return
        
        elif str(message['status']) in rule:
                
                logger.debug("alert_handler ALERT entity: %s status: %s" % (message['entity'], str(message['status'])))
                esc = Escalator(message)
                esc_required = esc.check()
                
                for user_pk in rule[str(message['status'])]:
                    logger.debug("alert_handler notify_slack user: %s entity: %s status: %s" % (str(user_pk), message['entity'], str(message['status'])))
                    notifier.notify_slack(user_pk)                    
                    
                    if esc_required and len(notifier.onduty_members()) == 0:
                        logger.debug('############## alert_handler escalation need to be done')
                        notifier.notify_twilio_call(user_pk)
                        
                return




def ack_handler(message):
    
    message['output'] = message['output'] + '\ncomment: ' + message['ack_comment']
    
    ack_data = {
                    "timestamp": message['timestamp'],
                    "entity": message['entity'],
                    "status": message['status'],
                    "output": message['output'],
                    "ack": True,
                    "ack_by": message['ack_by'],
                    "ack_comment": message['ack_comment']
                }
    

    Group("notifications").send({"text": json.dumps(ack_data)})
    
    notifier = Notify(message)
    notifier.notify_onduty(ack=True)
    
    if 'rule_' + message['entity'] in cache:
                
        logger.debug("ack_handler found rule for entity: %s" % message['entity'])
        rule = cache.get('rule_' + message['entity'])        
        
        if message['ack']:
            logger.debug("ack_handler ACK entity: %s status: %s" % (message['entity'], str(message['status'])))
            # looking for users that might have got previous alerts, the same people should get recovery
            history_notify = []         
            
            if str(message['status']) in rule:
                
                for user_pk in rule[str(message['status'])]:                    
                    if user_pk not in history_notify:                         
                        history_notify.append(user_pk)
                        
            for user_pk in history_notify:
                logger.debug("ack_handler notify_slack user: %s entity: %s status: %s" % (str(user_pk), message['entity'], str(message['status'])))                
                notifier.notify_slack(user_pk)
                
            return        




def slack_user_detect():
    
    logger.debug('slack_user_detect task start')
    response = slack.users.list()
    
    for team_uesr in response.body['members']:
        
        if team_uesr['deleted'] == False and team_uesr['name'] != 'slackbot' and 'profile' in team_uesr and 'email' in team_uesr['profile']:
            
            slack_user_id = team_uesr['id']
            slack_user_name = team_uesr['name']
            slack_user_email = team_uesr['profile']['email']
            DETECT = False
            DETECTED_EMAIL = None
            DETECTED_UPK = None
            
            if User.objects.filter(username=slack_user_name).exists():
                obj = User.objects.get(username=slack_user_name)
                DETECTED_UPK = obj.pk                
                DETECT = True
            
            if User.objects.filter(email=slack_user_email).exists():
                obj = User.objects.get(email=slack_user_email)
                DETECTED_UPK = obj.pk
                DETECTED_EMAIL = obj.email
                DETECT = True
            
            if Contact.objects.filter(email=slack_user_email).exists():                
                obj = Contact.objects.get(email=slack_user_email)
                DETECTED_UPK = obj.user.pk
                DETECTED_EMAIL = obj.email
                DETECT = True
            
            if DETECT:
                
                user_obj = User.objects.get(pk=DETECTED_UPK)
                slack_nag = False
                
                if not hasattr(user_obj, 'contact'):
                    logger.debug('slack_user_detect adding slack user id %s to user id: %s' % (slack_user_id, DETECTED_UPK))
                    user_obj.contact = Contact(email = slack_user_email, slack_uid = slack_user_id)
                    user_obj.contact.save()
                    slack_nag = True
                elif user_obj.contact.slack_uid in [None, '']:
                    logger.debug('slack_user_detect update slack user id %s to user id: %s' % (slack_user_id, DETECTED_UPK))
                    user_obj.contact.slack_uid = slack_user_id
                    user_obj.contact.save()
                    slack_nag = True
                    
                if slack_nag == True:
                    # send slack to user
                    data = { 'slack_user_id': slack_user_id, 'slack_user_name': slack_user_name, 'slack_user_email': slack_user_email, 
                         'detection':{ 'email': DETECTED_EMAIL,
                                       'user_pk': DETECTED_UPK
                        }
                    }
                    
                    logger.debug('slack_user_detect scheduling background-slack-nag slack user id %s user id: %s' % (slack_user_id, DETECTED_UPK))              
                    Channel('background-slack-nag').send(data)
            else:                
                # send new user to register job
                
                logger.debug('slack_user_detect scheduling background-register-user slack user id %s slack email: %s' % (slack_user_id, slack_user_email))
                data = { 'register_user_name': slack_user_name, 'register_user_email': slack_user_email, 'slack_user_id': slack_user_id}       
                Channel('background-register-user').send(data)
                
    logger.debug('slack_user_detect task end')




def slack_user_nag(message):
    
    if settings.DEBUG == True: return
    
    logger.debug('slack_user_nag task start - message: %s' % message)
    user_obj = User.objects.get(pk=message['detection']['user_pk'])
    MESSAGE = "Hello %s! we've detected you are using our team's slack. if you would like to receive alerts to your slack; enable it in your alert settings. (visit %s)" % (message['slack_user_name'], settings.REGISTRATION_URL_PREFIX)
    slack.chat.post_message(message['slack_user_id'], MESSAGE, as_user=False, username=settings.SLACK_BOT_NAME, icon_url=settings.SLACK_BOT_ICON)
    logger.debug('slack_user_nag task end - message: %s' % message)



   
def user_register(message):
    
    if settings.DEBUG == True: return
    
    logger.debug('user_register task start - email: %s' % message['register_user_email'])
    user = User.objects.create_user(message['register_user_name'], message['register_user_email'], is_active = False)
    message['register_password'] = passwd_generator(size=25)
    user.set_password(message['register_password'])
    user.save()    
    
    if 'slack_user_id' in message:
        user.contact = Contact(email = message['register_user_email'], slack_uid = message['slack_user_id'])
        user.contact.save()     
        registration_link = "%s%s?username=%s&key=%s" % (settings.REGISTRATION_URL_PREFIX, reverse_lazy('register_activate'), message['register_user_name'], message['register_password'])
        SLACK_MESSAGE = "Hello %s! we've detected you are using our team's slack. please take a minute to activate you account in the following <%s|LINK>.\n (please use same email address you used to sign-up with Slack)" % (message['register_user_name'], registration_link)
        logger.debug('user_register sending slack activation message to slack_uid %s' % message['slack_user_id'])
        slack.chat.post_message(message['slack_user_id'], SLACK_MESSAGE, as_user=False, username=settings.SLACK_BOT_NAME, icon_url=settings.SLACK_BOT_ICON)
        message['registration_link'] = registration_link
    else:      
        register_email(message)
    
    logger.debug('user_register task end - email: %s' % message['register_user_email'])
    
    

