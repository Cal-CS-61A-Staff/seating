#!/usr/bin/env python

# Refer to main() for usage.

import csv
import errno
import mimetypes
import os
import queue
import re
import sys
import threading
import urllib3, urllib3.util.ssl_

def fetcher(pool, q):
	mime_type_ranks = ['.jpg', '.png', '.tif', '.bmp']
	while 1:
		task = q.get()
		if task is None: break
		(url, cookie, path) = task
		response = None
		try: response = pool.request('GET', url, headers={'connection': 'keep-alive', 'accept-encoding': 'gzip, deflate, br', 'accept': 'image/webp,image/apng,image/*,*/*;q=0.8', 'cookie': cookie})
		except Exception as ex:
			sys.stderr.write(repr(ex)); sys.stderr.flush()
		if response and response.status == 200:
			data = response.data
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

def main(program, bcourses_roster_csv, bcourses_cookie):
	# 1. You may need the following:  python -m pip install urllib3[secure]
	# 2. Put all your students' emails into a text file (one email per line), let's call this "Student-Emails.txt".
	# 3. Now press F12 to open the debugging tools, go to the Network tab, and then navigate to the course roster.
	# 4. Find any GET request for a profile photo and copy one of its "Cookie" fields. The request URL should be "junction.berkeley.edu/...", and the cookie should begin with "_calcentral_session".
	#    (I used the "Cookie" field in the request headers, but you can also try the "Set-Cookie" field in the response headers.)
	# 5. Also download the course roster locally as a CSV; there should be an export button. Make sure it has a name like "course_1234567_rosters.csv", where 1234567 should be the course ID you see in the URL bar.
	# 6. Call this script and pass it all the above information in the following order (notice that "Student-Emails.txt" is PIPED in):
	#    python "this-script.py" "course_1234567_rosters.csv" "_calcentral_session=ABCDEFGHIJK" < "Student-Emails.txt"
	course_id = re.search("_([0-9]+)_", bcourses_roster_csv, re.IGNORECASE).group(1)
	roster = {}
	column_indices = {}
	with open(bcourses_roster_csv, 'r') as f:
		for r, row in enumerate(csv.reader(f, delimiter=',')):
			if r == 0:
				for c, cell in enumerate(row):
					column_indices[cell] = c
			else:
				roster[row[column_indices['Email Address']]] = row
	nthreads = os.getenv('OMP_NUM_THREADS', None)
	if not nthreads: nthreads = 16
	nthreads = max(int(nthreads), 1)
	ssl_context = urllib3.util.ssl_.create_urllib3_context()
	ssl_context.load_default_certs()
	pool = urllib3.HTTPSConnectionPool("junction.berkeley.edu", maxsize=nthreads, ssl_context=ssl_context)
	q = queue.Queue()
	threads = list(map(lambda i: threading.Thread(target=fetcher, args=(pool, q)), range(nthreads)))
	for t in threads: t.setDaemon(True); t.start()
	lines = list(sys.stdin.readlines())
	if not lines:
		sys.stderr.write("No emails specified; downloading entire roster...\n"); sys.stderr.flush()
		lines[:] = sorted(roster.keys())
	for line in lines:
		found = roster.get(line.strip())
		if found is not None:
			name = found[column_indices['Name']]
			name_split = name.split(", ", 2)
			name = " ".join(name_split[-1:] + name_split[:-1])
			path = os.path.join(found[column_indices['Sections']] + " - " + course_id, name)
			sys.stdout.write("> " + path + "\n"); sys.stdout.flush()
			q.put(("/canvas/%s/photo/%s" % (course_id, found[column_indices['User ID']]), bcourses_cookie, path))
		else:
			sys.stderr.write("? " + line.strip() + "\n"); sys.stderr.flush()
	for t in threads: q.put(None)
	for t in threads: t.join()

if __name__ == '__main__':
	import sys
	raise SystemExit(main(*sys.argv))
