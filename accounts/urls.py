from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializer import LoginSerializer, RefreshSerializer
from .views import change_password, current_user, logout, register

urlpatterns = [
    path('me/', current_user, name='current_user'),
    path('change-password/', change_password, name='change_password'),
    path('register/', register, name='register'),
    path('logout/', logout, name='logout'),
    path(
        'login/',
        TokenObtainPairView.as_view(serializer_class=LoginSerializer),
        name='login',
    ),
    path(
        'token/refresh/',
        TokenRefreshView.as_view(serializer_class=RefreshSerializer),
        name='token_refresh',
    ),
]
