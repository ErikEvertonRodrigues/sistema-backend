from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED, HTTP_200_OK
from rest_framework.authtoken.models import Token
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
    

@api_view(['POST'])
def login(request):
    user = User.objects.get(username=request.data['username'])

    if user.check_password(request.data['password']):
        token = Token.objects.create(user=user)
        return Response({"message": "Login success", "token": token.key}, status=HTTP_200_OK)
