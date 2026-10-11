from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class LoginSerializer(TokenObtainPairSerializer):
    """Login por usuário e senha: devolve o par de tokens e se a troca de senha é obrigatória.

    A resposta já diz se o aluno entrou com a senha temporária, para o frontend levá-lo
    direto à tela de troca sem uma chamada a mais.
    """

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        data["must_change_password"] = self.user.must_change_password
        return data


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


class LoginResponseSerializer(TokenPairSerializer):
    """Resposta do login: o par de tokens e a indicação da troca obrigatória."""

    must_change_password = serializers.BooleanField(
        help_text=(
            "Verdadeiro quando o aluno entrou com a senha temporária: até trocá-la, todas as "
            "rotas, menos a troca de senha e o logout, respondem 403 `password_change_required`."
        )
    )


class CurrentUserSerializer(serializers.Serializer):
    """Quem está autenticado: o nome de usuário que o menu do frontend mostra."""

    username = serializers.CharField(help_text="O nome de usuário do aluno autenticado.")


class LogoutSerializer(serializers.Serializer):
    """Corpo esperado pelo logout: o token de renovação a bloquear."""

    refresh = serializers.CharField(
        help_text="O token de renovação do próprio aluno, o mesmo devolvido no login."
    )


class ChangePasswordSerializer(serializers.Serializer):
    """Corpo da troca de senha: a senha atual e a nova.

    A senha atual prova que quem pede é o dono da conta, mesmo com um token roubado. A nova
    passa pelas regras de validação já configuradas e não pode repetir a atual, o que
    obrigaria a trocar a senha temporária por ela mesma.
    """

    current_password = serializers.CharField(
        write_only=True, help_text="A senha atual; no primeiro acesso, a senha temporária."
    )
    new_password = serializers.CharField(
        write_only=True,
        help_text=(
            "Ao menos 8 caracteres; não pode ser inteiramente numérica, nem uma senha comum "
            "demais, nem parecida com o nome de usuário, nem igual à atual."
        ),
    )

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("A senha atual não confere.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, self.context["request"].user)
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": ["A senha nova não pode ser igual à atual."]}
            )
        return attrs
