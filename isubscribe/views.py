from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.core.cache import cache

from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.contrib.auth import authenticate, login

from django.contrib.auth.password_validation import validate_password, ValidationError

from django.core.urlresolvers import reverse_lazy
from django.urls import reverse

from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.http import urlencode

from functools import wraps
import urllib3, base64, json, re, datetime, random, string
from distutils.command.check import check
from collections import OrderedDict
from twilio import twiml

from channels import Channel, Group

from isubscribe.models import Subscribe, Contact, ScheduledEvent, EventMembers, ScheduledOccurrence
from isubscribe.notify import Notify
from isubscribe.tasks import sensu_event_resolve, sensu_client_delete, sensu_result_delete, y_predict, y_sum_by_time
from isubscribe.forms import ScheduledEventForm, ContactForm

import logging
from re import search
logger = logging.getLogger(__name__)

import redis
import pickle
import codecs

redis_pool = redis.ConnectionPool(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, max_connections=settings.REDIS_POOL_MAX, password=settings.REDIS_PASSWORD)
r = redis.Redis(connection_pool=redis_pool)
http = urllib3.PoolManager(maxsize=10)


def ajax_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated():
            return view_func(request, *args, **kwargs)
        url = reverse('login')
        next={'next': request.META.get('HTTP_REFERER')}
        return HttpResponse(json.dumps({ 'not_authenticated': True, 'login_url': u'%s?%s' % (url, urlencode(next)) }), 'application/json')
    return wrapper



@login_required(login_url=reverse_lazy('login'))
def index(request):
    return HttpResponseRedirect(reverse_lazy('events'))



@login_required(login_url=reverse_lazy('login'))
def entities(request):

    '''            
    for Test in r.scan_iter(match=':1:entity_*'):
        print('************************************' + Test.decode('utf-8'))
    '''    
     
    logger.debug('entities view triggered by %s' % request.user.username)
    
    if request.method == 'POST' and 'search' in request.POST and request.POST['search'] != '':
        
        logger.debug('entities view search by user %s search: %s' % (request.user.username, request.POST['search']))
        
        data = {}
        mimetype = 'application/json'
        
        Group("entities-private-%s" % request.user.id).send({
            "text": json.dumps({'flush_signal':True})
        })
    
                     
        #for word in cache.keys("entity_*%s*" % request.POST['search']):
        for word in r.scan_iter(match=':1:entity_*'):
            #if request.POST['search'].lower() in word.decode('utf-8').lower():
            if re.search(request.POST['search'].lower(), word.decode('utf-8'), re.IGNORECASE):
                #entity = re.sub(r'^entity_', '', word)            
                entity = re.sub(r'^:1:entity_', '', word.decode('utf-8'))
                status_1 = False       
                status_2 = False 
                try:
                    rule = cache.get('rule_' + entity)            
                    if '1' in rule and request.user.id in rule['1']:
                        status_1 = True            
                    if '2' in rule and request.user.id in rule['2']:
                        status_2 = True            
                except:
                    pass
                if 'silent_' + entity in cache.keys("silent_*"):                
                    silent = True
                else:
                    silent = False
                    
                result = { 'entity': entity, 'status_1': status_1, 'status_2': status_2, 'silent': silent }
                
                Group("entities-private-%s" % request.user.id).send({
                    "text": json.dumps(result)
                })
                
                #logger.debug("entities view search: %s result: %s" % (request.POST['search'], json.dumps(result)))
            
        data['search'] = request.POST['search']        
        data['status'] = 0
        data['timestamp'] = datetime.datetime.now().timestamp()
            
        return HttpResponse(json.dumps(data), mimetype)
        
    
    data = {}
    profile_form = ContactForm(instance=Contact.objects.get(user=request.user.id), user=request.user)
      
    return render(request, 'isubscribe/entities.html', {'DATA':data, 'profile_form': profile_form})




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def subscribe_toggle(request):

    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '' and 'status' in request.POST and request.POST['status'] != '':

        data['entity'] = request.POST['entity']
        data['status'] = request.POST['status']
        
        if Subscribe.objects.filter(entity=request.POST['entity'], status=int(request.POST['status'])).count() > 0:
            # change existing object
            obj = Subscribe.objects.get(entity=request.POST['entity'], status=int(request.POST['status']))
            if request.user.pk not in obj.friends.values_list('pk', flat=True).all():
                obj.friends.add(request.user.pk)
                data['result'] = "subscription added"
                logger.debug('%s subscribed to %s' % (request.user.username, request.POST['entity']))
            else:
                obj.friends.remove(request.user.pk)
                data['result'] = "subscription removed"
                logger.debug('%s unsubscribed from %s' % (request.user.username, request.POST['entity']))
        else:
            # create new object
            obj = Subscribe(entity=request.POST['entity'], status=int(request.POST['status']))
            obj.save()
            obj.friends.add(request.user.pk)
            data['result'] = "subscription added"
            logger.debug('%s subscribed to new entity %s' % (request.user.username, request.POST['entity']))
        
        Channel('background-build-entity-rules').send({'entity': request.POST['entity']})    
    
    return HttpResponse(json.dumps(data), mimetype)




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def silent_toggle(request):

    mimetype = 'application/json'
    data = {}
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':
        data['entity'] = request.POST['entity']
        data['status'] = request.POST['status']
        data['result'] = 'okay'
        if 'silent_comment' in request.POST:          
            data['silent_comment'] = 'silenced by ' + request.user.username + ': ' + request.POST['silent_comment']
        else:
            data['silent_comment'] = ''                    
        
        if 'ack_' + data['entity'] in cache.keys("ack_*"):
                ack = cache.get('ack_' + data['entity'])
                ack_by = ack['user_name']
                ack_comment = ack['ack_comment']
                acked = True
        else:
            acked = False
            ack_by = ''
            ack_comment = ''
        
        if 'silent_' + data['entity'] in cache.keys("silent_*"):
            cache.delete('silent_' + data['entity'])
            silent_return = False 
            silent_data = {
                    'user_id': request.user.pk, 
                    'user_name': request.user.username,
                    "timestamp": datetime.datetime.now().timestamp(),
                    "entity": data['entity'],
                    "status": data['status'],
                    "output": data['silent_comment'],
                    "silent": False,
                    "silent_by": request.user.username,
                    "silent_comment": data['silent_comment'],
                    "ack": acked,
                    "ack_by": ack_by,
                    "ack_comment": ack_comment
                }           
        else:
            silent_data = {
                    'user_id': request.user.pk, 
                    'user_name': request.user.username,
                    "timestamp": datetime.datetime.now().timestamp(),
                    "entity": data['entity'],
                    "status": data['status'],
                    "output": data['silent_comment'],
                    "silent": True,
                    "silent_by": request.user.username,
                    "silent_comment": data['silent_comment'],
                    "ack": acked,
                    "ack_by": ack_by,
                    "ack_comment": ack_comment
                }
            cache.set('silent_' + data['entity'], silent_data, timeout=(3600 * 24 * 365))
            silent_return = True
            data['silent_info'] = silent_data
        
        data['silent'] = silent_return    

        Group("notifications").send({"text": json.dumps(silent_data)})  
    
    return HttpResponse(json.dumps(data), mimetype)



@login_required(login_url=reverse_lazy('login'))
def events(request):        

    data = {}
    
    if 'event' in request.GET and request.GET['event'] != '':
        logger.debug('event details view triggered by %s for event: %s' % (request.user.username, request.GET['event']))
        try:        
            data = cache.get('event_' + request.GET['event'])
        except:
            raise
        return render(request, 'isubscribe/generic.html', {'DATA':data['check']})
    
    logger.debug('events view triggered by %s' % request.user.username)
    
    for word in cache.keys("event_*"):
        entity = re.sub(r'^event_', '', word)        
        try:
            data[entity] = {}
            event_data = cache.get('event_' + entity)
            data[entity]['entity_element_id'] = re.sub(r':|\.', '_', entity)
            data[entity]['entity'] = entity
            data[entity]['status'] = event_data['check']['status']
            data[entity]['output'] = json.dumps(event_data['check']['output'], ensure_ascii=False)
            data[entity]['timestamp'] = event_data['timestamp']
            
            if 'ack_' + entity in cache.keys("ack_*"):    
                data[entity]['ack'] = True
                ack = cache.get('ack_' + entity)                
                data[entity]['ack_by'] = ack['user_name']
                data[entity]['ack_comment'] = ack['ack_comment']
            else:
                data[entity]['ack'] = False
            
            if 'silent_' + entity in cache.keys("silent_*"):    
                data[entity]['silent'] = True
                silent = cache.get('silent_' + entity)                
                data[entity]['silent_by'] = silent['user_name']
                data[entity]['silent_comment'] = silent['silent_comment']
            else:
                data[entity]['silent'] = False
                
        except:
            raise
        
    profile_form = ContactForm(instance=Contact.objects.get(user=request.user.id), user=request.user)
    
    
    return render(request, 'isubscribe/events.html', {'DATA':OrderedDict(sorted(data.items(), key=lambda x: x[1]['timestamp'], reverse=True)), 'profile_form': profile_form})



@login_required(login_url=reverse_lazy('login'))
def clients(request):        

    data = {}
    
    for word in cache.keys("client_*"):
        client = re.sub(r'^client_', '', word)
        try:
            
            client_data = cache.get(word)
            data[client] = client_data 
            
        except:
            raise
    
    profile_form = ContactForm(instance=Contact.objects.get(user=request.user.id), user=request.user)
    
    return render(request, 'isubscribe/clients.html', {'DATA':data, 'profile_form': profile_form})



@login_required(login_url=reverse_lazy('login'))
def subscriptions(request):        

    data = {}
    
    for word in r.keys("subscription_*"):
        subscription = re.sub(r'^subscription_', '', str(word.decode('utf-8')))
        try:
            
            subscription_data = r.lrange(word, 0, -1)
            data[subscription] = subscription_data 
            
        except:
            raise
    
    profile_form = ContactForm(instance=Contact.objects.get(user=request.user.id), user=request.user)   
    
    return render(request, 'isubscribe/subscriptions.html', {'DATA':data, 'profile_form': profile_form})




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def ack(request):

    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '' and 'ack_interval' in request.POST and request.POST['ack_interval'] != '':
        
        data['entity'] = request.POST['entity']
        data['ack_interval'] = request.POST['ack_interval']
        data['status'] = request.POST['status']
        data['timestamp'] = datetime.datetime.now().timestamp()
        data['ack_by'] = request.user.username
        data['ack'] = True
        data['output'] = "acknowledged by %s for %s hours" % (request.user.username, request.POST['ack_interval'])
        
        if 'ack_comment' in request.POST:          
            data['ack_comment'] = 'acknowledged by ' + request.user.username + ': ' + request.POST['ack_comment']
        
        ack_data = { 'user_id': request.user.pk, 
                    'user_name': request.user.username, 
                    'timestamp': datetime.datetime.now().timestamp(), 
                    'ack_interval': request.POST['ack_interval'],
                    'ack_comment': data['ack_comment']
                    }        
        
        logger.debug('ack %s' % json.dumps(ack_data))
        cache.set("ack_" + request.POST['entity'], ack_data, timeout=(float(data['ack_interval']) * 3600))                
        
        Channel('background-ack').send(data)
    
    return HttpResponse(json.dumps(data), mimetype)




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def resolve(request):

    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':
        data['entity'] = request.POST['entity']        
        data['status'] = 0
        data['timestamp'] = datetime.datetime.now().timestamp()        
        data['output'] = "resolve request by %s" % (request.user.username)
        data['result'] = 'okay'
        
        sensu_event_resolve(data)
        Channel('background-alert').send(dict(data))
        
    
    return HttpResponse(json.dumps(data), mimetype)



#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def rmClient(request):

    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'client' in request.POST and request.POST['client'] != '':
        data['client'] = request.POST['client']        
        data['status'] = 0
        data['timestamp'] = datetime.datetime.now().timestamp()
        
        if sensu_client_delete(data):
            data['result'] = 'okay'
        else:        
            data['result'] = 'failed deleting ' + data['client']
    
    return HttpResponse(json.dumps(data), mimetype)


#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def rmResult(request):

    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':        
        data['client'], data['check'] = request.POST['entity'].split(':')       
        data['status'] = 0
        data['timestamp'] = datetime.datetime.now().timestamp()
        
        if sensu_result_delete(data):
            data['result'] = 'okay'
        else:        
            data['result'] = 'failed deleting result using sensu api for: ' + request.POST['entity']
    
    return HttpResponse(json.dumps(data), mimetype)



@login_required(login_url=reverse_lazy('login'))
def redoCheck(request):

    mimetype = 'application/json'   
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':        
        
        client_name, check_name = request.POST['entity'].split(':')
        
        API_URL = settings.SENSU_API_URL + '/request'
        userAndPass = base64.b64encode(str.encode("%s:%s" % (settings.SENSU_API_USER, settings.SENSU_API_PASSWORD))).decode("ascii")
        headers = { 'X_REQUESTED_WITH' :'XMLHttpRequest',
                   'Accept': 'application/json, text/javascript, */*; q=0.01',
                   'Authorization' : 'Basic %s' %  userAndPass }
                
        try:
            
            client_name, check_name = request.POST['entity'].split(':')
            post_params = {"check": check_name}
            
            request = http.request('POST', API_URL, body=json.dumps(post_params), headers=headers)   
            response = request.status
                    
            if response == 202:
                data['result'] = 'accepted'
            elif response == 404:
                data['result'] = 'check not found'
            else:
                data['result'] = 'error'
            
            request.release_conn()
        
        except:
            logger.error("redoCheck failed request check_name: %s" % check_name)
            raise
        
    
    
    return HttpResponse(json.dumps(data), mimetype)


@csrf_exempt
def alert(request):
    
    if 'api_token' not in request.POST or request.POST['api_token'] != settings.API_TOKEN:
        return HttpResponse('Unauthorized', status=401)
    
    mimetype = 'application/json'
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '' and 'status' in request.POST and request.POST['status'] != '':

        data['entity'] = request.POST['entity']
        data['status'] = int(request.POST['status'])
        data['timestamp'] = datetime.datetime.now().timestamp()

        if 'output' in request.POST:
            data['output'] = request.POST['output'].rstrip('\n')
        
        if 'history' in request.POST:          
            data['history'] = request.POST.getlist('history')
        
        if 'occurrences' in request.POST:          
            data['occurrences'] = request.POST['occurrences']
        
        data['result-text'] = "got it!"
        data['result-code'] = 0
        
        Channel('background-alert').send(data)    
        logger.debug('alert triggered entity: %s status: %s' % (request.POST['entity'], str(request.POST['status'])))
    
    return HttpResponse(json.dumps(data), mimetype)




def register_activate(request):
        
    if 'key' not in request.GET or request.GET['key'] == '':
        return HttpResponse('Unauthorized', status=401)
    
    data = {}
    data['username'] = request.GET['username']
    data['key'] = request.GET['key']
    data['errors'] = ''
    
    if 'email' in request.POST and request.POST['key'] != '' and request.POST['password'] == request.POST['password_repeat']:
        
        try:
            
            validate_password(request.POST['password'])            
            # check for key against current user password
            logger.debug("validating registration key for user %s" % request.POST['username'])
            
            try:
                u = User.objects.get(username=request.POST['username'])
                if u.contact.email == request.POST['email']:
                    if u.check_password(request.POST['key']):
                        #user activate
                        logger.debug("activating user %s" % request.POST['username'])
                        u.set_password(request.POST['password'])
                        u.is_active = True
                        u.save()
                        login(request, u)
                        return HttpResponseRedirect(reverse_lazy('entities'))
            except:
                data['errors'] = 'An exception flew by!'
                
        except ValidationError as err:
            logger.debug("validating registration new password for user %s FAILED - %s" % (request.POST['username'], err))
            data['errors'] = err
    
    return render(request, 'registration/activate.html', {'DATA':data})




@csrf_exempt
def twilio_say(request):
    
    if 'api_token' not in request.GET or request.GET['api_token'] != settings.TWILIO_CALLBACK_API_TOKEN:
        return HttpResponse('Unauthorized', status=401)
    
    try:
        if 'CallStatus' in request.POST:
            for k in request.POST:
                logger.debug("***twilio_say got CallStatus in request: %s" % k)
    except:
        pass
    
    if 'msg' in request.GET and request.GET['msg'] != '':
        
        logger.debug("twilio_say building xml for twilio API message: [%s]" % request.GET['msg'])
        r = twiml.Response()
        r.say(request.GET['msg'], voice='alice')
        r.hangup()
        return HttpResponse(r, content_type='text/xml')
    
    return HttpResponse('Unauthorized', status=401)



@csrf_exempt
def twilio_status(request):
    
    logger.debug('***twilio_status triggered ')
    
    if 'api_token' not in request.GET or request.GET['api_token'] != settings.TWILIO_CALLBACK_API_TOKEN:
        return HttpResponse('Unauthorized', status=401)
    
    try:
        for k in request.POST:
            logger.debug("***twilio_status POST in request. %s: %s" % (k, request.POST[k]))
        for k in request.GET:
            logger.debug("***twilio_status GET in request. %s: %s" % (k, request.GET[k]))
    except:
        pass
    
    try:
        if request.POST['CallStatus'] != 'completed':
            notifier = Notify({
                'entity': request.GET['entity'],
                'status': request.GET['status'],
                'output': 'twilio on duty retry'
            })
            notifier.notify_onduty(twilio_retry=True, member_id=int(request.GET['member_id']))
            logger.debug("***twilio_status sent twilio_retry after failed calling %s" % (request.GET['member_id']))
    except:
        logger.error('***twilio_status failed handling notify_onduty twilio_retry')
        raise
    
        
    
    return HttpResponse('I will handle it from here', status=200)



@login_required(login_url=reverse_lazy('login'))
def user_settings(request):        
    
    logger.debug('settings view triggered by %s' % (request.user.username))
    
    form = ContactForm(request.POST, instance=Contact.objects.get(user=request.user.id), user=request.user, update=True)
    #form = ContactForm(request.POST, user=request.user, update=True)
    if form.is_valid:
        try:
            form.save()
            return HttpResponse('Done', status=200)
        except:        
            return HttpResponse(json.dumps(form.errors), status=409)
    else:
        return HttpResponse(json.dumps(form.errors), status=409)

    
    
    return render(request, 'isubscribe/user_settings.html', {'DATA':data, 'form': form})
    


@login_required(login_url=reverse_lazy('login'))
def onduty(request):
    
    if 'action' in request.GET and request.GET['action'] == 'onduty_agenda':

        data = []
        
        FROM = datetime.datetime.strptime(request.GET['start'], "%Y-%m-%d")
        TO = datetime.datetime.strptime(request.GET['end'], "%Y-%m-%d")
        
        for event_start, event_end, instance in ScheduledOccurrence.objects.filter(event__in=ScheduledEvent.objects.filter(event=0)).all_occurrences(from_date=FROM, to_date=TO):

            description = []
            for member in instance.event.members_list():
                if not hasattr(member, 'contact') or member.contact.phone_number in [None, '']:                    
                    description.append(member.username)
                else:
                    description.append(member.username + ': ' + member.contact.phone_number)
                    
            if request.user in instance.event.members_list():
                event_privileges = True
            else:
                event_privileges = False
            
            data.append({
                         'id': instance.id,
                         'title': instance.event.description,
                         'description': description,
                         'start': event_start,
                         'end': event_end,                         
                         'repeat': instance.repeat,
                         'repeat_until': instance.repeat_until,
                         'instance_start': instance.start,
                         'instance_end': instance.end,
                         'source': reverse_lazy('onduty'),
                         'event_id': instance.event.id,
                         'privileges': event_privileges            
            })
                            
            
        for event_start, event_end, instance in ScheduledOccurrence.objects.filter(event__in=ScheduledEvent.objects.filter(event=1, members__in=[request.user.id])).all_occurrences(from_date=FROM, to_date=TO):

            description = []
            for member in instance.event.members_list():
                if not hasattr(member, 'contact') or member.contact.phone_number in [None, '']:                    
                    description.append(member.username)
                else:
                    description.append(member.username + ': ' + member.contact.phone_number)
            
            data.append({
                         'id': instance.id,
                         'title': instance.event.description,
                         'description': description,
                         'start': event_start,
                         'end': event_end,                         
                         'repeat': instance.repeat,
                         'repeat_until': instance.repeat_until,
                         'instance_start': instance.start,
                         'instance_end': instance.end,
                         'source': reverse_lazy('onduty'),
                         'event_id': instance.event.id,
                         'privileges': True
            })                      
                      
        return JsonResponse(data, safe=False)
    
    
    
    
    elif 'action' in request.POST and (request.POST['action'] == 'onduty_disable_alerts' or request.POST['action'] == 'onduty_enable_alerts'):
        if request.POST['action'] == 'onduty_disable_alerts':
            logger.debug('onduty view disable onduty alerts triggered by %s' % (request.user.username))
            cache.set('onduty_disable_alerts', True, timeout=None)
            action_value = True
        elif request.POST['action'] == 'onduty_enable_alerts':
            logger.debug('onduty view enable onduty alerts triggered by %s' % (request.user.username))
            cache.set('onduty_disable_alerts', False, timeout=None)
            action_value = False
        
        Group("on-duty").send({
        "text": json.dumps({
                "action_type": "onduty_toggle_alerts",
                "action_value": action_value,
                "action_by": request.user.username            
            })
        })
            
        return HttpResponse(request.POST['action'])
    
    # no good! DnD objects should be created when creating user
    if len(ScheduledEvent.objects.filter(event=1, members__in=[request.user.id])) < 1:
            logger.info('onduty view creating DnD object for user: %s' % (request.user.username))
            e = ScheduledEvent(event=1, description='DnD - ' + request.user.username)
            e.save()
            m = EventMembers(order=0, event_id=e.id, member_id=request.user.id)
            m.save()
    
    
    if 'onduty_disable_alerts' in cache.keys("onduty_disable_*"):
        onduty_disable_alerts = cache.get('onduty_disable_alerts')
    else:
        onduty_disable_alerts = False

    # check form       
    if 'id' in request.POST:
        
        if request.POST['id'] == 'new':
            form = ScheduledEventForm(request.POST, user=request.user, editable=True)
        else:
            event_instance = ScheduledOccurrence.objects.get(id=request.POST['id'])
            form = ScheduledEventForm(request.POST, user=request.user, editable=True, instance=event_instance)
            
        if form.is_valid():
            logger.debug('update ScheduledOccurrence')
            form.save()
        else:
            logger.debug('********************* ' + json.dumps(form.errors))
            
    
    profile_form = ContactForm(instance=Contact.objects.get(user=request.user.id), user=request.user)        
    
    return render(request, 'isubscribe/cal.html', {'onduty_disable_alerts': onduty_disable_alerts, 'form_view': ScheduledEventForm(user=request.user, editable=False), 'form_edit': ScheduledEventForm(user=request.user, editable=True), 'profile_form': profile_form})




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def entity_history(request):            
        
    data = []
    mimetype = 'application/json'   
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':
        
        entity = request.POST['entity']
        logger.debug("view entity_history user: %s entity: %s" % (request.user.username, entity))
    
        for history_data in r.lrange('history_entity_' + entity, 0, 100):
            data.append(pickle.loads(history_data))
    
    return HttpResponse(json.dumps(data), mimetype)



#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def entity_notify_history(request):            
        
    data = []
    mimetype = 'application/json'   
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':
        
        entity = request.POST['entity']
        logger.debug("view entity_notify_history user: %s entity: %s" % (request.user.username, entity))
    
        for history_data in r.lrange('notifyhistory_entity_' + entity, 0, 100):
            data.append(pickle.loads(history_data))
    
    return HttpResponse(json.dumps(data), mimetype)




#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def check_config(request):        
        
    mimetype = 'application/json'   
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':        
        client_name, check_name = request.POST['entity'].split(':')
        #check_name = 'check_gw_tomcat_errors_1h'
        data = cache.get('check_' + check_name)
    
    
    return HttpResponse(json.dumps(data), mimetype)



#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def check_result(request):        
    
    mimetype = 'application/json'   
    data = {}
    
    if request.method == 'POST' and 'entity' in request.POST and request.POST['entity'] != '':        
        
        client_name, check_name = request.POST['entity'].split(':')
        
        API_URL = settings.SENSU_API_URL + '/results/' + client_name + '/' + check_name
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
                logger.error('check_result response: %s' % str(response))
                
        except:
            logger.error("check_result failed")
            raise
        
    
    
    return HttpResponse(json.dumps(data), mimetype)



@permission_required('is_staff', login_url=reverse_lazy('login'))
@login_required(login_url=reverse_lazy('login'))
def whois(request):

    mimetype = 'application/json'

    # Get channel_layer function
    from channels.asgi import get_channel_layer
    from channels.sessions import session_for_reply_channel
            
    # passing group_channel takes channel name
    #channel_layer = get_channel_layer()
    #data = channel_layer.group_channels('notifications')
    #data = channel_layer.global_statistics()
    #data = channel_layer.channel_statistics('notifications')
    #data = get_channel_layer().group_channels('notifications')    
    #data = Group("notifications").extensions
    #data = get_channel_layer().receive_twisted()
    
    #from channels import channel_layers
    #layer = channel_layers["default"]
    #print(layer.router.channels)    
    
    data = []
    
    
    from django.contrib.sessions.backends import cache as engine
    data = get_channel_layer().group_channels('notifications')
    
    active_users = []
    for C in data:        
        #Channel(C).send({"text": json.dumps({'clean_signal':True})})
        c_session = session_for_reply_channel(C)        
        session = engine.SessionStore(c_session._session_key)        
        
        #print(c_session._session['_auth_user_id'])
        #print(session.keys())
        #print(session.get('username', None), session.get_expiry_date())
        
        username = session.get('username', None)
        # this is the same
        # username = c_session.get('username', None)
        if username not in active_users and username != None:
            active_users.append(username)
    data = active_users
            
    
    return HttpResponse(json.dumps(data), mimetype)



@permission_required('is_staff', login_url=reverse_lazy('login'))
@login_required(login_url=reverse_lazy('login'))
def test(request):

    mimetype = 'application/json'
    data = []
    
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
            reponse = json.load(reader(request))
            request.release_conn()
        else:
            logger.error('response: %s' % str(response))
            
    except:
        logger.error("failed")
        raise    
    
    
    for object in reponse:
        
        if 'action' not in object or 'handle' not in object['check']:
            continue    
                
        client = object['client']['name']
        check = object['check']['name']
        status = int(object['check']['status'])
        output = object['check']['output']
        history = object['check']['history']
        occurrences = int(object['occurrences'])
        timestamp = object['timestamp']
        last_state_change = object['last_state_change']
        
        status_duration = timestamp - last_state_change        
        entity = client + ':' + check                                
        ABORT = False
        
        message = {'timestamp': timestamp, 'entity': entity, 'status': status, 'output': output, 'history': history, 'occurrences': occurrences }
        
        try:
            last_known = cache.get('last_known_' + entity)
        except:
            last_known = {'timestamp': 0}
            pass
        
        
        if last_known != None and last_known['timestamp'] == object['timestamp']:
            continue        
        
        if object['action'] == 'flapping' and object['check']['handle'] == True and object['check']['type'] == 'standard' and object['silenced'] == False:                                                                                       
            message['detect'] = 'flapping'
            
            
        elif object['action'] == 'create' and object['check']['handle'] == True and object['check']['type'] == 'standard' and object['silenced'] == False:            
            if status > 0 and occurrences < object['check']['occurrences']:                 
                message['detect'] = 'low_occurrences'
            else:
                continue
        
        
        cache.set('last_known_' + entity, message, timeout=object['check']['interval'])    
                
        if not ABORT:                                                                            
            r.lpush('attention_' + entity, pickle.dumps(message))
            
            data.append(message)
                                
                #cache.set('flap_' + entity, object, timeout=object['check']['interval'])
                #message['output'] = '(flapping %s) %s' % (object['check']['total_state_change'], message['output'])
                #Channel('background-alert').send(message) 
        
        
    return HttpResponse(json.dumps(data), mimetype)


#@login_required(login_url=reverse_lazy('login'))
@ajax_login_required
def trends(request):
    
    mimetype = 'application/json'

    try:
        data = cache.get('trends_all')
    except:
        data = []
        pass                    
        
    
    return HttpResponse(json.dumps(data), mimetype)

