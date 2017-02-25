from django.conf import settings
from django import forms
from django.forms import ModelForm, widgets

from django.contrib.auth.models import User
from isubscribe.models import ScheduledOccurrence, ScheduledEvent, Contact, Rule
from asyncio.log import logger

import re


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
    
    slack_uid = forms.CharField(widget = forms.TextInput(attrs={'readonly':'readonly'}), required=False)
    
    class Meta:
        model = Contact
        fields = ['slack_uid', 'email', 'phone_number']



class RuleForm(ModelForm):
        
    class Meta:
        model = Rule
        fields = ['id', 'name', 'regex_string', 'status', 'owner']
        
    
    def __init__(self, *args, **kwargs):
        
        if 'user' in kwargs:
            self.user = kwargs.pop('user', None)  
                    
        super(RuleForm, self).__init__(*args, **kwargs)
        
        self.fields['owner'].queryset = User.objects.filter(id=self.user.id)
