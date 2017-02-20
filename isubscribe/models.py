from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from eventtools.models import BaseEvent, BaseOccurrence
from multiselectfield import MultiSelectField



class Contact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    alert_active = models.BooleanField(default=True)
    phone_regex = RegexValidator(regex='^\d{9,15}$', message="Phone number must contain numbers only: '999999999'. Up to 15 digits allowed.", code='invalid_phonenumber')
    phone_number = models.CharField(validators=[phone_regex], blank=True, max_length=15) # validators should be a list
    email = models.EmailField(max_length=70, null=True, blank=True, unique=True)
    slack_uid = models.CharField(max_length=70, null=True, blank=True)
    
    def __str__(self):
        return "%s" % (self.pk)


  
class Subscribe(models.Model):
    entity = models.CharField(max_length=256, blank=False, null=False)
    STATUS_CHOICES = (
        (0, 'okay'),
        (1, 'warning'),
        (2, 'critical'),
    )
    status = models.IntegerField(
        choices=STATUS_CHOICES        
    )
    friends = models.ManyToManyField(User)
    
    def __str__(self):
        return "entity: [%s] status: [%s]" % (self.entity, self.status)
    

class Rule(models.Model):
    owner = models.ForeignKey(User)
    name = models.CharField(max_length=256, blank=False, null=False)
    regex_string = models.CharField(blank=False, null=False, max_length=512)
    STATUS_CHOICES = (
        (1, 'warning'),
        (2, 'critical'),
    )
    status = MultiSelectField(
        max_length=3,
        choices=STATUS_CHOICES,
        blank=False,
        null=False
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return "owner: %s name: %s status: %s" % (self.owner, self.name, self.status)
 

class ScheduledEvent(BaseEvent):
    EVENT_CHOICES = (
        (0, 'On Duty'),
        (1, 'Do Not Disturb')
    )
    event = models.IntegerField(choices=EVENT_CHOICES)
    description = models.CharField(max_length=128, null=True, blank=True)
    members = models.ManyToManyField(
        User,
        related_name = 'members',
        through = 'EventMembers',      
    )
    
    
    class Meta:        
        ordering = ['event',]
        verbose_name = ("Scheduled Event")
        verbose_name_plural = ("Scheduled Events")
        
    def members_list(self):
        return [scev.member for scev in EventMembers.objects.filter(event=self).order_by('order')]

    def __str__(self):
        return self.description



class EventMembers(models.Model):
    member = models.ForeignKey(User)
    event = models.ForeignKey(ScheduledEvent)       
    order = models.IntegerField()

    class Meta:
        verbose_name = ("Event Member")
        verbose_name_plural = ("Event Member")
        ordering = ['order',]

    def __unicode__(self):
        return self.member.first_name + " " + self.member.last_name + " is a member of " + self.event.name + (" in position %d" % self.order)



class ScheduledOccurrence(BaseOccurrence):
    event = models.ForeignKey(ScheduledEvent)
    
    class Meta:
        verbose_name = ("Scheduled Occurrence")
        verbose_name_plural = ("Scheduled Occurrences")

    def __str__(self):
        return str(self.start) + " " + self.event.description
