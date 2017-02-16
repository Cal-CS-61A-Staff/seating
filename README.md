## First Time Deployment

	dokku apps:create seating
	dokku mysql:create seating
	dokku mysql:link seating seating
	# Set DNS record
	dokku domains:add seating seating.cs61a.org
	# Change OK OAuth to support the domain

	dokku config:set seating <ENVIRONMENT VARIABLES>

	git remote add dokku dokku@app.cs61a.org:seating
	git push dokku master

	dokku run seating flask initdb
	dokku letsencrypt seating

In addition, add the following to `/home/dokku/seating/nginx.conf`:
```
proxy_buffer_size   128k;
proxy_buffers   4 256k;
proxy_busy_buffers_size   256k;
```

## Environment variables

```
FLASK_APP=server/__init__.py
SECRET_KEY
DATABASE_URL
OK_CLIENT_ID
OK_CLIENT_SECRET
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
```
