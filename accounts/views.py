from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from .serializer import UserSerializer

# Create your views here.

@api_view(['POST']) 
def register(request):
    user = UserSerializer(data=request.data)
    
    if user.is_valid():
        user.save()

        userRetrieved = User.objects.get(username=request.data["username"])
        userRetrieved.set_password(user.data["password"])

        userRetrieved.save()

        return Response(user.data, status=HTTP_201_CREATED)
