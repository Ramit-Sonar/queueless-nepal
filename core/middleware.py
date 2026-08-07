from django.utils.cache import add_never_cache_headers


class NoCacheForAuthenticatedUsersMiddleware:
    """Stop browsers from caching (or back-forward-caching) any page rendered
    for a logged-in user, so that clicking "back" after logout can't replay a
    stale authenticated page instead of requiring a fresh login."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
