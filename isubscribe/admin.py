from django.contrib import admin

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Contact, Subscribe, ScheduledEvent, ScheduledOccurrence, EventMembers, Rule

# Define an inline admin descriptor for Contact model
# which acts a bit like a singleton
class ContactInline(admin.StackedInline):
    model = Contact
    can_delete = False
    verbose_name_plural = 'contact'

# Define a new User admin
class UserAdmin(BaseUserAdmin):
    inlines = (ContactInline, )
    

class EventMembersInline(admin.TabularInline):
    model = EventMembers
    extra = 1

class ScheduledEventAdmin(admin.ModelAdmin):
    inlines = (EventMembersInline,)    


class EventMemberAdmin(admin.ModelAdmin) :
    pass

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Subscribe)
admin.site.register(Rule)

admin.site.register(ScheduledEvent, ScheduledEventAdmin)
admin.site.register(EventMembers, EventMemberAdmin)
admin.site.register(ScheduledOccurrence)

