from django.core.management.base import BaseCommand, CommandError
from channels import Channel, Group, channel_layers
import json
from builtins import str


class Command(BaseCommand):
    
    help = 'Send text announcement on notifications channel (events view)'
    
    def add_arguments(self, parser):
    
        parser.add_argument(
                '-m',
                '--message',
                dest='message',
                required=True,
                help='announcement message text',
                metavar = "MESSAGE"
            )
    
    def handle(self, *args, **options):
        
        Group("announcement").send({
            "text": json.dumps({'announce':True,
                                'message': options['message']
                    })
        })
        
        self.stdout.write('announcement done\n')
    