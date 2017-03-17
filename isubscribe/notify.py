from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django.template import Context
from django.contrib.auth.models import User
from django.urls import reverse_lazy

from channels import Channel

from isubscribe.models import Contact, ScheduledEvent, ScheduledOccurrence

from twilio.rest import TwilioRestClient

import urllib, datetime, json

import logging
logger = logging.getLogger(__name__)

from slacker import Slacker

slack = Slacker(settings.SLACK_BOT_TOKEN)



def register_email(message):
    
    register_email_plaintext = get_template('registration/email_register.txt')
    register_email_htmly     = get_template('registration/email_register.html')
    
    send_to = message['register_user_email']
    username = message['register_user_name']
    registration_link = message['registration_link']
    subject, from_email, to = message['subject'], message['from_email'], message['to_email']
    text_content = register_email_plaintext.render({ 'username': username, 'registration_link': registration_link })
    html_content = register_email_htmly.render(d)
    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    
 


class Notify:
    
    def __init__(self, message):
        
        self.entity = message['entity']
        self.status = int(message['status'])
        self.output = message['output']
              
        if int(message['status']) == 0:
            self.color = '#36a64f'
            self.twilio_msg_prefix = 'recovery notification.'
            self.twilio_msg_postfix = 'is okay!'
        elif int(message['status']) == 1:
            self.color = '#FFA500'
            self.twilio_msg_prefix = 'this is a warning!'
            self.twilio_msg_postfix = 'is in status warning!'
        elif int(message['status']) == 2:
            self.color = '#C74350'
            self.twilio_msg_prefix = 'bad news, this is a critical notification!'
            self.twilio_msg_postfix = 'is in status critical!'
        else:
            self.color = ''
            self.twilio_msg_prefix = 'unknown notification.'
            self.twilio_msg_postfix = 'is in status unknown!'
        
        slack_alert_template     = get_template('isubscribe/slack_alert.txt')
        self.slack_msg_content_fallback = slack_alert_template.render({ 'entity': self.entity, 'status': self.status, 'output':self.output })
        
        
        
        self.slack_attachments = [{
                    "fallback": self.slack_msg_content_fallback,
                    "title": self.entity,
                    "title_link": "%s%s" % (settings.REGISTRATION_URL_PREFIX, reverse_lazy('events')),
                    "text": self.output,
                    "color": self.color,
                    "author_name": settings.SLACK_BOT_NAME,
                    "author_link": "%s%s" % (settings.REGISTRATION_URL_PREFIX, reverse_lazy('events')),
                    "author_icon": settings.SLACK_BOT_ICON,
        }]
               
        twilio_msg_formated = self.twilio_msg_prefix + ' ' + self.entity + ' ' + self.twilio_msg_postfix
        self.twilio_params = { 'msg' : twilio_msg_formated,
                               'api_token' : settings.TWILIO_CALLBACK_API_TOKEN,
                               'entity': self.entity, 
                               'status': self.status 
                            }
        
        self.twilio_client = TwilioRestClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        self.slack_delivery_to = []
        self.twilio_delivery_to = []



    def get_contact(self, user_pk):
        
        if 'contact_' + str(user_pk) in cache.keys("contact_*"):
            contact = cache.get('contact_' + str(user_pk))
        else:
            try:
                user = User.objects.get(id=user_pk, is_active = True)
            except:
                logger.error('notify get_contact failed finding user id: %s' % (user_pk))
                pass                                        
            if not hasattr(user, 'contact') or user.contact.slack_uid in [None, '']:
                logger.error('notify get_contact no contact found for user id: %s' % (user_pk))
                return {}
            else:
                
                if user.contact.slack_uid not in [None, '']:
                    slack_uid = user.contact.slack_uid
                else:                    
                    slack_uid = None
                    
                if user.contact.phone_number not in [None, '']:
                    phone_number = user.contact.phone_number
                else:
                    phone_number = None
                    
                contact = { 'slack_uid': slack_uid, 'phone_number': phone_number, 'username': user.username }
                cache.set('contact_' + str(user_pk), contact, timeout=(float(1) * 3600))
                
        return contact
    


    def onduty_members(self):
        
        OnDuty = []
        if 'OnDuty' in cache.keys('OnDuty'):
            OnDuty = cache.get('OnDuty')      
        else:
            try:
                event_start, event_end, instance = ScheduledOccurrence.objects.filter(event__in=ScheduledEvent.objects.filter(event=0)).next_occurrence()    
                NOW = datetime.datetime.now(datetime.timezone.utc).timestamp()
                if NOW >= event_start.timestamp() and NOW <= event_end.timestamp():
                    for user in instance.event.members_list():
                        OnDuty.append(user.pk)
                    logger.debug('onduty_members found: %s' % OnDuty)
                    #cache.set('OnDuty', OnDuty, timeout=event_end.timestamp())
                    cache.set('OnDuty', OnDuty, timeout=settings.ON_DUTY_CACHE_MEMBERS)
                else:
                    logger.debug('onduty_members can not find onduty_members')
            except:
                logger.error('onduty_members failed finding onduty_members')
                pass
            
        return OnDuty

    
    
    def user_dnd(self, user_pk):
        
        if 'DnD_' + str(user_pk) in cache.keys("DnD_*"):
            #DnD = cache.get('DnD_' + str(user_pk))
            DnD = True        
        else:
            DnD = False
            try:
                event_start, event_end, instance = ScheduledOccurrence.objects.filter(event__in=ScheduledEvent.objects.filter(event=1, members__in=[user_pk])).next_occurrence()    
                NOW = datetime.datetime.now(datetime.timezone.utc).timestamp()
                if NOW >= event_start.timestamp() and NOW <= event_end.timestamp():
                    DnD = True
                    cache.set('DnD_' + str(user_pk), DnD, timeout=event_end.timestamp())
            except:
                pass
            
        return DnD



    def notify_onduty(self, twilio_retry=False, member_id=None, ack=False):
        
        if 'onduty_disable_alerts' in cache.keys("onduty_disable_*"):
            if cache.get('onduty_disable_alerts'):
                logger.warning('notify_onduty - onduty alerts are disabled')
                return
        
        if twilio_retry:
            logger.debug('notify_onduty - this is a twilio_retry for member_id: %s' % member_id)
            members = self.onduty_members()
            self.twilio_params['members'] = members
            index = 0
            for member in members:
                if member == member_id:
                    if index > 0:
                        previous_member = members[index - 1]
                    if index < (len(members) - 1):
                        next_member = members[index + 1]
                    else:
                        next_member = members[0]
                elif index == (len(members) - 1):
                    next_member = members[0]
                index = index + 1
            logger.debug('######### notify_onduty do notify_twilio_call for next member id: %s' % next_member)                    
            self.twilio_params['member_id'] = next_member
            self.notify_twilio_call(next_member, dnd_ignore=True, on_duty=True, onduty_retry=True)
        else:            
            members = self.onduty_members()
            logger.debug('notify_onduty - this is a normal call for notify_twilio_call members: %s' % members)
            self.twilio_params['members'] = members
            if len(members) > 0 and self.status >= settings.ON_DUTY_STATUS_LEVEL and ack == False:
                self.twilio_params['member_id'] = members[0]
                logger.debug('######### notify_onduty do notify_twilio_call for user id: %s' % members[0])
                self.notify_twilio_call(members[0], dnd_ignore=True, on_duty=True)
        
            for user_pk in members:
                logger.debug('********* notify_onduty do notify_slack for user id: %s' % user_pk)
                self.notify_slack(user_pk, dnd_ignore=True)
                
            


    def notify_slack(self, user_pk, dnd_ignore=False):        
        
        if dnd_ignore == False and self.user_dnd(user_pk):
            logger.debug('notify_slack user id: %s is in DnD' % (user_pk))
            return
        
        if user_pk in self.slack_delivery_to:
            logger.debug('notify_slack already sent this message to user id: %s' % (user_pk))
            return
        
        try:
                                    
            contact = self.get_contact(user_pk)
                    
            if 'slack_uid' not in contact or contact['slack_uid'] in [None, '']:
                    logger.warning('notify_slack no slack_uid found in contact for user id: %s' % (user_pk))
                    return
            
            logger.debug('notify_slack sending message to slack_uid %s message: %s' % (contact['slack_uid'], self.slack_msg_content_fallback))            
            slack.chat.post_message(contact['slack_uid'], '', attachments=self.slack_attachments, as_user=False, username=settings.SLACK_BOT_NAME, icon_url=settings.SLACK_BOT_ICON)
            self.slack_delivery_to.append(user_pk)
            
            Channel('background-notify-history').send({
                'entity': self.entity,
                'status': self.status,
                'output': self.output,
                'timestamp': datetime.datetime.now().timestamp(),
                'user': contact['username'],
                'user_id': user_pk,
                'contact': contact['slack_uid'],
                'transport': 'notify_slack'
            })
            
        except:
            
            logger.error("notify_slack can not send message to user id: %s" % user_pk)
            pass



    def notify_twilio_call(self, user_pk, dnd_ignore=False, on_duty=False, onduty_retry=False):
        
        if dnd_ignore == False and self.user_dnd(user_pk):
            logger.debug('notify_twilio_call user id: %s is in DnD' % (user_pk))
            return
        
        if user_pk in self.twilio_delivery_to:
            logger.debug('notify_twilio_call already called user id: %s with this message' % (user_pk))
            return
        
        throttling_user = 'twillio_throttling_' + str(user_pk)
        throttling_key = 'twillio_throttling_' + str(user_pk) + '_' + self.entity
                
        if throttling_user in cache.keys("twillio_throttling_*") and onduty_retry == False:
               throttling_user_int = cache.get(throttling_user)
               if throttling_user_int >= settings.THROTTLING_TWILIO_USER_COUNT:
                   logger.warning('notify_twilio_call throttling prevent call user id: %s' % (user_pk))
                   return
        else:
            throttling_user_int = 0
           
        if throttling_key in cache.keys("twillio_throttling_*") and onduty_retry == False:
               logger.warning('notify_twilio_call throttling prevent call entity: %s user id: %s' % (self.entity, user_pk))
               return
               
        try:
            
            contact = self.get_contact(user_pk)
                    
            if 'phone_number' not in contact or contact['phone_number'] in [None, '']:
                    logger.warning('notify_twilio_call no phone_number found in contact for user id: %s' % (user_pk))
                    return
            
            
            logger.debug('notify_twilio_call calling number %s for user id:  %s' % (contact['phone_number'], user_pk))                             
            
            call = self.twilio_client.calls.create(to=contact['phone_number'], 
                                                   from_=settings.TWILIO_FROM_NUMBER, 
                                                   url="%s%s?%s" % ( settings.TWILIO_CALLBACK_URL_PREFIX, reverse_lazy('twilio_say'), urllib.parse.urlencode(self.twilio_params) ),
                                                   status_callback="%s%s?%s" % ( settings.TWILIO_CALLBACK_URL_PREFIX, reverse_lazy('twilio_status'), urllib.parse.urlencode(self.twilio_params) ),
                                                   status_callback_method="POST",
                                                   status_callback_events=["no-answer", "busy", "failed"],
                                                   timeout=28
                                                )        
            logger.info('notify_twilio_call request call to: %s twilio call id: %s' % (contact['phone_number'], call.sid))            
            
            cache.set(throttling_user, throttling_user_int + 1, timeout=settings.THROTTLING_TWILIO_USER_TTL)
            cache.set(throttling_key, call.sid, timeout=settings.THROTTLING_TWILIO_USER_ENTITY_TTL)
                        
            self.twilio_delivery_to.append(user_pk)
            
            Channel('background-notify-history').send({
                'entity': self.entity,
                'status': self.status,
                'output': self.output,
                'timestamp': datetime.datetime.now().timestamp(),
                'user': contact['username'],
                'user_id': user_pk,
                'contact': contact['phone_number'],
                'transport': 'notify_twilio_call'
            })
                
        except:
            
            logger.error('notify_twilio_call user id: %s entity: %s status: %s' % (user_pk, self.entity, self.status))
            pass



