from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class RegisterSerializer(serializers.ModelSerializer):
    """Dados de registro: usuário e senha, validada pelas mesmas regras do admin.

    A conta é criada e autenticada na mesma chamada — a resposta já traz o par de
    tokens (acesso e renovação), sem exigir uma chamada de login separada em seguida.
    """

    password = serializers.CharField(
        write_only=True,
        help_text=(
            "Ao menos 8 caracteres; não pode ser inteiramente numérica, nem uma senha "
            "comum demais, nem parecida com o nome de usuário."
        ),
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "password"]

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data: dict):
        return get_user_model().objects.create_user(**validated_data)


class TokenPairSerializer(serializers.Serializer):
    """Par de tokens emitido ao autenticar: acesso e renovação."""

    access = serializers.CharField(
        help_text="Token de acesso — exigido em todo pedido protegido. Válido por 30 minutos."
    )
    refresh = serializers.CharField(
        help_text=(
            "Token de renovação — troca por um novo par em `/api/auth/token/refresh/`, sem "
            "senha. Válido por 7 dias, mas só pode ser usado uma vez: cada renovação invalida "
            "o token de renovação anterior."
        )
    )


class LogoutSerializer(serializers.Serializer):
    """Corpo esperado pelo logout: o token de renovação a bloquear."""

    refresh = serializers.CharField(
        help_text="O token de renovação do próprio aluno, o mesmo devolvido no login ou registro."
    )
