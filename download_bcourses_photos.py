#!/usr/bin/env python

# Instructions: pass --help to see instructions.

import argparse
import errno
import json
import mimetypes
import os
import re
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

def find_cookies_in_cookies_txt(for_domain, content):
	matches = []
	for match in re.finditer("^\\s*([^#\\t\\r\\n]+).*\\s+([^#\\t\\r\\n]*[\\S])\\s+([^#\\t\\r\\n]*[\\S])\\s*$", content, re.MULTILINE):
		domain = match.group(1)
		if for_domain == domain or ("." + for_domain).endswith("." + domain.lstrip(".")):
			matches.append(match.group(2) + "=" + match.group(3))
	return matches

ROSTER_FIELDS = ['id', 'first_name', 'last_name', 'student_id', 'email', 'login_id', 'photo', 'section_ccns', 'enroll_status', 'grade_option', 'units', 'sections']  # Not set in stone: the server may add/remove fields as it wishes...

def main(program, *args):
	program_name = os.path.basename(program)
	argparser = argparse.ArgumentParser(
		prog=program_name,
		usage=None,
		description=None,
		epilog="""FORMAT fields:
%s

INSTRUCTIONS:

1. Put all your students' emails into a text file (one email per line), let's call this "Student-Emails.txt".
2. Go to the roster page on CalCentral.
3. [Chrome] Copy your '_calcentral_session' cookie's Content from the following page:
	chrome://settings/cookies/detail?search=cookie&site=junction.berkeley.edu
	and replace XXXXX with it in the next step (below).
3. [Any browser] Press F12 to open the debugging tools, go to the Network tab, and then navigate to the course roster.
	Find a GET request to junction.berkeley.edu and copy its "Cookie" field from the "Headers" tab (NOT the "Cookies" tab).
	You need the cookie string beginning with "_calcentral_session".
	(I used the "Cookie" field in the request headers, but you can also try the "Set-Cookie" field in the response headers.)
4. Call this script and pass it all the above information as follows:
	python "%s" "_calcentral_session=XXXXX" < "Student-Emails.txt"
""" % ("  " + ", ".join(ROSTER_FIELDS), program_name),
		parents=[],
		formatter_class=argparse.RawTextHelpFormatter,
		add_help=True)
	server = "junction.berkeley.edu"
	server_with_protocol = "https://" + server
	cookie_name = '_calcentral_session'
	argparser.add_argument('--format', required=False, help="the photo file name format string (default: \"%%(default)s\")\n(example: \"%s\")" % ('{id} - {first_name} {last_name} - {student_id} - {email}',), default="{id}")
	argparser.add_argument('--file', required=False, action='store_true', help="indicates cookie parameter is a file name rather than the cookie string itself")
	argparser.add_argument('bcourses_cookie', help="bCourses cookie string (default) or cookie file (if --file is specified)\r\ncontaining the %s cookie for %s" % (repr(cookie_name), server))
	argparser.add_argument('emails', metavar='emails.txt', nargs='?', type=argparse.FileType('r'), default=sys.stdin, help="name of text file containing student emails, 1 per line (default: stdin)")

	if 'COLUMNS' not in os.environ:
		os.environ['COLUMNS'] = str(128)
	parsed_args = argparser.parse_args(args)
	format_string = parsed_args.format
	bcourses_cookie = parsed_args.bcourses_cookie
	emails = parsed_args.emails
	if parsed_args.file:
		with open(bcourses_cookie, 'r') as f:
			bcourses_cookie = "; ".join(find_cookies_in_cookies_txt(server, f.read()))
	else:
		if ";" not in bcourses_cookie and " " not in bcourses_cookie and "=" not in bcourses_cookie[:48]:
			bcourses_cookie = cookie_name + "=" + bcourses_cookie
			sys.stderr.write("WARNING: Cookie string doesn't appear to include %s; assuming you forgot to include it...\n" % (repr(cookie_name + "="),))

	nthreads = os.getenv('OMP_NUM_THREADS', None)
	if not nthreads: nthreads = 16
	nthreads = max(int(nthreads), 1)

	sys.stderr.writelines(["Downloading course info..."]); sys.stderr.flush()
	course_info = read_http_response_as_json(urlopen(server_with_protocol + "/api/academics/rosters/canvas/embedded", cookie=bcourses_cookie))
	canvas_course = course_info.get('canvas_course')
	if canvas_course is None:
		msg = "failed to retrieve course information; please verify the %s cookie is correctly specified here: %s" % (repr(cookie_name), repr(bcourses_cookie))
		raise ValueError(msg)
	course_id = canvas_course['id']
	course_name = canvas_course['name']
	course_students = course_info['students']
	sys.stderr.writelines([" %s: %s\n" % (course_id, course_name)]); sys.stderr.flush()
	roster = dict(map(lambda student: (student['email'], student), course_students))
	q = Queue()
	threads = list(map(lambda i: threading.Thread(target=fetcher, args=(q,)), range(nthreads)))
	for t in threads: t.setDaemon(True); t.start()
	sys.stderr.writelines(["Reading student emails..."]); sys.stderr.flush()
	lines = None
	if not emails.isatty():
		lines = emails.readlines()
	sys.stderr.writelines(["\n"]); sys.stderr.flush()
	if lines is None:
		sys.stderr.write("No emails specified; downloading entire roster...\n"); sys.stderr.flush()
		lines = sorted(roster.keys())
	for line in lines:
		found = roster.get(line.strip())
		if found is not None and "photo" in found:
			path = os.path.join("%s - %s" % ((list(map(lambda section: section['name'], found['sections'])) + [course_name])[0], course_id), format_string.format(**found))
			sys.stdout.write("> " + path + "\n"); sys.stdout.flush()
			q.put((server_with_protocol + found['photo'], bcourses_cookie, path))
		else:
			sys.stderr.write("? " + line.strip() + "\n"); sys.stderr.flush()
	for t in threads: q.put(None)
	for t in threads: t.join()

if __name__ == '__main__':
	import sys
	raise SystemExit(main(*sys.argv))
