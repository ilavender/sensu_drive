from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.db.models.fields import Empty

import urllib3, base64, json, random, string
import codecs
import redis

from channels import Channel, Group
from slacker import Slacker

from isubscribe.models import Subscribe, Contact
from isubscribe.notify import register_email, Notify


http = urllib3.PoolManager(maxsize=10)
slack = Slacker(settings.SLACK_BOT_TOKEN)

redis_pool = redis.ConnectionPool(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, max_connections=settings.REDIS_POOL_MAX, password=settings.REDIS_PASSWORD)
r = redis.Redis(connection_pool=redis_pool)


import logging
logger = logging.getLogger('isubscribe')



class escalator:
    
    def __init__(self, message):
        
        self.entity = message['entity']
        self.history = message['history']
        self.status = int(message['status'])
        self.occurrences = int(message['occurrences'])
    
    
    def check(self):
        
        logger.debug("escalator check entity: %s" % self.entity)
        
        if 'ack_' + self.entity in cache.keys("ack_*") or self.status == 0:
            return False
        
        if self.occurrences > 20 and self.occurrences > len(self.history) and self.status == 2:
            return True
        
        if len(self.history) > 1: 
                # remove current status from history
                self.history.pop()
                
                if len(self.history) < 2:
                    return False
                
                problem_history = []  
                              
                for i in range(len(self.history), 0, -1):                    
                    last_status = int(self.history[i-1])
                    if int(last_status) == 0:
                        break                    
                    problem_history.append(last_status)
                                
                if self.status == 2 and len(problem_history) >= 2 and len(set(problem_history)) == 1 :
                    return True
                
                if int(self.status) == 2 and len(problem_history) > 10 :
                    return True

        
        return False

        