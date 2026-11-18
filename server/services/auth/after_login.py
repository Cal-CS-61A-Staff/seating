from flask import flash, request, session

from server.cross_origin import is_cross_origin

NOT_DONE = "Your sign-in has expired, so that wasn't done. Sign in and try again."


def remember_page_for_after_login():
    """
    Sends the user back to this page once they've signed in, if it's a page. The sign-in comes back
    with a GET, so a post (e.g. pressing Delete once the sign-in has expired) can't be redone that
    way, and would end on a 405 for a POST-only url: it lands on the home page instead, saying it
    wasn't done.
    """
    if request.method == 'GET':
        # including links from other sites, e.g. Canvas
        session['after_login'] = request.url
    elif request.method in ('HEAD', 'OPTIONS'):
        return
    elif is_cross_origin():
        # the URL converters call this before the cross-origin check refuses the post: leave the
        # session as it is, so another site can't change where a sign-in goes or what it says
        return
    else:
        # not a page from some earlier signed-out visit either
        session.pop('after_login', None)
        # a page's fetch() (the email page's preview and batches) never shows a flash, so it would
        # only pile up for a later page
        navigated = request.headers.get('Sec-Fetch-Mode', 'navigate') == 'navigate'
        if navigated and NOT_DONE not in [message for _, message in session.get('_flashes', [])]:
            flash(NOT_DONE, 'warning')
