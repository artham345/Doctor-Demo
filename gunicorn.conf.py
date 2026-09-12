import os
bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = 2
timeout = 60
# Do not log paths containing private cancellation tokens or patient search terms.
accesslog = None
errorlog = '-'
capture_output = False
