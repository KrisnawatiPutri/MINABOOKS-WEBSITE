from .models import BusinessProfile


def business(request):
    if not request.user.is_authenticated:
        return {}
    return {'business': BusinessProfile.current()}
