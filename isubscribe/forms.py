from django.conf import settings
from django import forms
from django.forms import ModelForm, widgets

from django.contrib.auth.models import User
from isubscribe.models import ScheduledOccurrence, ScheduledEvent, Contact, Rule
from asyncio.log import logger


import logging
logger = logging.getLogger('isubscribe.forms')



class ScheduledEventForm(ModelForm):
    
    id = forms.CharField(widget=forms.HiddenInput())
    #id = forms.CharField()
    delete = forms.BooleanField(initial=False, required=False)
    #start = forms.DateTimeField(widget=forms.DateTimeInput())
    #end = forms.DateTimeField(widget=forms.DateTimeInput())
    #repeat_until = forms.DateField(widget=forms.DateInput())
    
    class Meta:
        model = ScheduledOccurrence
        exclude = ['repeat_until']

    
    def __init__(self, *args, **kwargs):
        
        if 'user' in kwargs:
            self.user = kwargs.pop('user')
        
        if 'editable' in kwargs:
            self.editable = kwargs.pop('editable')
        else:
            self.editable = True      
            
        super(ScheduledEventForm, self).__init__(*args, **kwargs)
        
        self.fields['id'].widget.attrs['readonly'] = True
        self.fields['id'].widget.attrs['disabled'] = False
        
        if (self.editable == False):            
            self.fields['start'].widget.attrs['readonly'] = True
            self.fields['start'].widget.attrs['disabled'] = True
            self.fields['end'].widget.attrs['readonly'] = True
            self.fields['end'].widget.attrs['disabled'] = True
            self.fields['repeat'].widget.attrs['readonly'] = True
            self.fields['repeat'].widget.attrs['disabled'] = True
            #self.fields['repeat_until'].widget.attrs['readonly'] = True
            #self.fields['repeat_until'].widget.attrs['disabled'] = True
            self.fields['event'].widget.attrs['readonly'] = True
            self.fields['event'].widget.attrs['disabled'] = True            
            self.fields['delete'].widget.attrs['readonly'] = True
            self.fields['delete'].widget.attrs['disabled'] = True
        else:   
            self.fields['event'].queryset = ScheduledEvent.objects.filter(members__in=[self.user.id])
            
            
        if self.user.is_staff and self.editable == True:
            self.fields['event'].widget.attrs['readonly'] = False
            self.fields['event'].widget.attrs['disabled'] = False
            self.fields['delete'].widget.attrs['readonly'] = False
            self.fields['delete'].widget.attrs['disabled'] = False
            
            
    def save(self, commit=True):
        if self.cleaned_data['delete']:
            return self.instance.delete()
        return super(ScheduledEventForm, self).save()
    
    
    
class ContactForm(ModelForm):
    
    id = forms.CharField(widget=forms.HiddenInput())
    user = forms.CharField(widget=forms.HiddenInput())
    alert_active = forms.BooleanField(widget=forms.HiddenInput())
    
    class Meta:
        model = Contact
        #fields = ['first_name', 'last_name', 'email']
        #exclude = ['is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'date_joined', 'username', 'password']
        exclude = []

    
    def __init__(self, *args, **kwargs):
        
        if 'user' in kwargs:
            self.user = kwargs.pop('user')  
            
        if 'update' in kwargs:
            self.update = kwargs.pop('update')
        else:
            self.update = False                  
            
        super(ContactForm, self).__init__(*args, **kwargs)
        
        self.fields['user'].queryset = User.objects.filter(id=self.user.id)
        
        self.fields['id'].widget.attrs['readonly'] = True
        self.fields['id'].widget.attrs['disabled'] = False        
        self.fields['user'].widget.attrs['readonly'] = True
        self.fields['user'].widget.attrs['disabled'] = False
        self.fields['slack_uid'].widget.attrs['readonly'] = True
        self.fields['slack_uid'].widget.attrs['disabled'] = True
        
        if (self.update == True):
            self.fields['id'].widget.attrs['disabled'] = False     
            self.fields['user'].widget.attrs['disabled'] = False
            self.fields['slack_uid'].widget.attrs['disabled'] = False
            
           
    def save(self, commit=True):
        user_obj = User.objects.get(id=self.user.id)
        user_obj.contact.email = self.data['email']
        user_obj.contact.phone_number = self.data['phone_number']
        user_obj.contact.save()
        return super(ContactForm, self)



class RuleForm(ModelForm):
    
    #owner = forms.CharField(widget=forms.HiddenInput())
    
    class Meta:
        model = Rule
        fields = ['id', 'name', 'regex_string', 'status', 'owner']
        
    
    def __init__(self, *args, **kwargs):
        
        if 'user' in kwargs:
            self.user = kwargs.pop('user', None)  
                    
        super(RuleForm, self).__init__(*args, **kwargs)
        
        self.fields['owner'].queryset = User.objects.filter(id=self.user.id)
   
    '''
    def save(self, commit=True):
        rule_obj = Rule(owner=self.user)
        rule_obj.name = self.data['name']
        rule_obj.regex_string = self.data['regex_string']        
        rule_obj.status = self.data['status']
        rule_obj.save()
        return super(RuleForm, self)
    '''