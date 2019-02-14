#!/usr/bin/env python

# Refer to main() for usage.

import errno
import json
import mimetypes
import os
import sys
import threading

try: from queue import Queue  # Python 3
except ImportError: from Queue import Queue  # Python 2

try: import urllib.request as urllib2  # Python 3
except ImportError: import urllib2  # Python 2

def urlopen(url, *args, **kwargs):
	cookie = kwargs.pop('cookie', None)
	opener = urllib2.build_opener()
	if cookie is not None: opener.addheaders.append(('Cookie', cookie))
	return opener.open(url, *args, **kwargs)

def get_content_charset(headers):
	try: get_param = headers.get_param  # Python 3
	except AttributeError: get_param = headers.getparam  # Python 2
	return get_param("charset") or 'utf-8'

def read_http_response_as_json(response):
	return json.load(response, encoding=get_content_charset(response.headers))

def fetcher(q):
	mime_type_ranks = ['.jpg', '.png', '.tif', '.bmp']
	while 1:
		task = q.get()
		if task is None: break
		(url, cookie, path) = task
		response = None
		try: response = urlopen(url, cookie=cookie)
		except Exception as ex:
			sys.stderr.write(repr(ex)); sys.stderr.flush()
		if response and response.getcode() == 200:
			data = response.read()
			ext = "".join(sorted(mimetypes.guess_all_extensions(response.headers['Content-Type']), key=lambda ext: mime_type_ranks.index(ext.lower()) if ext.lower() in mime_type_ranks else len(mime_type_ranks))[:1])
			if len(data) > 0:
				path_with_ext = path + ext
				if not os.path.exists(path_with_ext):
					path_parent = os.path.dirname(path_with_ext)
					try:
						os.makedirs(path_parent)
					except OSError as ex: 
						if not (ex.errno == errno.EEXIST and os.path.isdir(path_parent)):
							raise
					with open(path_with_ext, 'w+b') as f:
						f.write(data)
						f.close()
			sys.stdout.write("< " + path_with_ext + "\n"); sys.stdout.flush()
		else:
			sys.stderr.write("! " + path_with_ext + "\n"); sys.stderr.flush()
		q.task_done()

def main(program, bcourses_cookie):
	# 1. Put all your students' emails into a text file (one email per line), let's call this "Student-Emails.txt".
	# 2. Now press F12 to open the debugging tools, go to the Network tab, and then navigate to the course roster.
	# 3. Find a GET request to junction.berkeley.edu and copy its "Cookie" field from the "Headers" tab (NOT the "Cookies" tab). You need the cookie string beginning with "_calcentral_session".
	#    (I used the "Cookie" field in the request headers, but you can also try the "Set-Cookie" field in the response headers.)
	# 4. Call this script and pass it all the above information in the following order (notice that "Student-Emails.txt" is PIPED in):
	#    python "this-script.py" "_calcentral_session=ABCDEFGHIJK" < "Student-Emails.txt"
	nthreads = os.getenv('OMP_NUM_THREADS', None)
	if not nthreads: nthreads = 16
	nthreads = max(int(nthreads), 1)
	sys.stderr.writelines(["Downloading course info..."]); sys.stderr.flush()
	server = "https://junction.berkeley.edu"
	course_info = read_http_response_as_json(urlopen(server + "/api/academics/rosters/canvas/embedded", cookie=bcourses_cookie))
	course_id = course_info['canvas_course']['id']
	course_name = course_info['canvas_course']['name']
	course_students = course_info['students']
	sys.stderr.writelines([" %s: %s\n" % (course_id, course_name)]); sys.stderr.flush()
	roster = dict(map(lambda student: (student['email'], student), course_students))
	q = Queue()
	threads = list(map(lambda i: threading.Thread(target=fetcher, args=(q,)), range(nthreads)))
	for t in threads: t.setDaemon(True); t.start()
	sys.stderr.writelines(["Reading student emails..."]); sys.stderr.flush()
	lines = list(sys.stdin.readlines())
	sys.stderr.writelines(["\n"]); sys.stderr.flush()
	if not lines:
		sys.stderr.write("No emails specified; downloading entire roster...\n"); sys.stderr.flush()
		lines[:] = sorted(roster.keys())
	for line in lines:
		found = roster.get(line.strip())
		if found is not None:
			path = os.path.join("%s - %s" % ((list(map(lambda section: section['name'], found['sections'])) + [course_name])[0], course_id), found['first_name'] + " " + found['last_name'])
			sys.stdout.write("> " + path + "\n"); sys.stdout.flush()
			q.put((server + found['photo'], bcourses_cookie, path))
		else:
			sys.stderr.write("? " + line.strip() + "\n"); sys.stderr.flush()
	for t in threads: q.put(None)
	for t in threads: t.join()

if __name__ == '__main__':
	import sys
	raise SystemExit(main(*sys.argv))
