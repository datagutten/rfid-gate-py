accesslog = "/dev/stdout"
errorlog = "/dev/stderr"
workers = 1
bind = '0.0.0.0:80'
wsgi_app = 'feig.http_api:app'
secure_scheme_headers = {'X-FORWARDED-PROTOCOL': 'ssl', 'X-FORWARDED-PROTO': 'https', 'X-FORWARDED-SSL': 'on'}
