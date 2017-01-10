from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from channels import Channel, channel_layers

import schedule
from time import sleep
import signal


import logging
logger = logging.getLogger('isubscribe')


def signal_term_handler(signal, frame):
    logger.info("%s - process exit signal %s" % (__name__, signal))
    exit(0)


signal.signal(signal.SIGTERM, signal_term_handler)
signal.signal(signal.SIGTSTP, signal_term_handler)


def job_update_entities():
    logger.info("%s - schedule running job job_update_entities" % (__name__))
    Channel('background-update-entities').send({'comment': 'from jobs schedule'})
    return



def job_update_clients():
    logger.info("%s - schedule running job job_update_clients" % (__name__))
    Channel('background-update-clients').send({'comment': 'from jobs schedule'})
    return


def job_update_events():
    logger.info("%s - schedule running job job_update_events" % (__name__))
    Channel('background-update-events').send({'comment': 'from jobs schedule'})
    return


def job_update_checks():
    logger.info("%s - schedule running job job_update_checks" % (__name__))
    Channel('background-update-checks').send({'comment': 'from jobs schedule'})
    return

def job_update_trends():
    logger.info("%s - schedule running job job_update_trends" % (__name__))
    Channel('background-update-trends').send({'comment': 'from management command'})
    return


class Command(BaseCommand):
    
    help = 'jobs loop executer and sleeper'
    
    def handle(self, *args, **kwargs):

        logger.info("%s - starting jobs schedule" % (__name__))
            
        try:
            '''            
            schedule.every().hour.do(job_update_entities)
            schedule.every().hour.do(job_update_clients)
            schedule.every().hour.do(job_update_checks)
            schedule.every().hour.do(job_update_trends)
            #schedule.every(10).minutes.do(job_update_events)
            '''
            
            schedule.every(settings.CACHE_ENTITY_TTL).seconds.do(job_update_entities)
            schedule.every(settings.CACHE_CLIENT_TTL).seconds.do(job_update_clients)
            schedule.every(settings.CACHE_TRENDS_TTL).seconds.do(job_update_trends)
            
            
            while True:
                schedule.run_pending()
                sleep(1)

        except KeyboardInterrupt:
            logger.info("%s - user signal exit!" % (__name__))
            exit(0)

    