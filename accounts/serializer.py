from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken


class StrictInputFieldsMixin:
    """Reject unknown and read-only input fields across accounts endpoints."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            allowed_fields = {
                name for name, field in self.fields.items() if not field.read_only
            }
            unexpected_fields = set(data) - allowed_fields
            if unexpected_fields:
                raise serializers.ValidationError({
                    name: [_("This field is not allowed.")]
                    for name in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "first_name", "last_name")
        read_only_fields = fields


class RegisterSerializer(StrictInputFieldsMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "password")
        read_only_fields = ("id",)

    def validate(self, attrs):
        user = get_user_model()(username=attrs["username"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return attrs

    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data)


class LoginSerializer(StrictInputFieldsMixin, TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Match registration: whitespace is part of the user's password.
        self.fields["password"].trim_whitespace = False


class RefreshSerializer(StrictInputFieldsMixin, TokenRefreshSerializer):
    def validate(self, attrs):
        # SimpleJWT 5.5.1 does not check password changes in its refresh serializer.
        # Validate the refresh first, then reuse its official user/revocation check.
        refresh = self.token_class(attrs["refresh"])
        JWTAuthentication().get_user(refresh)
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist as error:
            # Handle deletion between get_user() and the base serializer's lookup.
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], "no_active_account"
            ) from error


class LogoutSerializer(StrictInputFieldsMixin, serializers.Serializer):
    refresh = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError as error:
            raise InvalidToken(str(error)) from error

        user = self.context["request"].user
        user_id = getattr(user, jwt_settings.USER_ID_FIELD)
        if str(token.get(jwt_settings.USER_ID_CLAIM)) != str(user_id):
            raise PermissionDenied(_("The refresh token does not belong to this user."))
        return token

    def create(self, validated_data):
        blacklisted_token, _ = validated_data["refresh"].blacklist()
        return blacklisted_token


class ChangePasswordSerializer(StrictInputFieldsMixin, serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.instance
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({
                "current_password": _("The current password is incorrect."),
            })
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({
                "new_password_confirm": _("The new passwords do not match."),
            })
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError({
                "new_password": _("The new password must differ from the current password."),
            })
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error
        return attrs

    def update(self, instance, validated_data):
        instance.set_password(validated_data["new_password"])
        instance.save(update_fields=["password"])
        return instance
