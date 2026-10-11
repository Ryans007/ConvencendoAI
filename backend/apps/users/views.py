from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.users.serializers import (
    ChangePasswordSerializer,
    CurrentUserSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    TokenPairSerializer,
)
from apps.users.services.password_change import change_password


class LoginView(TokenObtainPairView):
    """Troca usuário e senha por um par de tokens e diz se a troca de senha é obrigatória.

    Quem entra com a senha temporária recebe os tokens normalmente, mas, até trocá-la, só a
    troca de senha e o logout respondem; as outras rotas devolvem 403 `password_change_required`.
    """

    serializer_class = LoginSerializer

    @extend_schema(
        responses={
            200: LoginResponseSerializer,
            401: OpenApiResponse(description="Usuário ou senha incorretos, ou acesso desativado."),
        },
        examples=[
            OpenApiExample(
                "Entrou com a senha temporária",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIi...",
                    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCI...",
                    "must_change_password": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class CurrentUserView(APIView):
    """Devolve quem está autenticado, para o frontend mostrar o nome de usuário no menu.

    Passa pela permissão padrão, então quem ainda não trocou a senha temporária recebe o
    403 de troca obrigatória, como em qualquer outra rota protegida.
    """

    @extend_schema(
        responses={200: CurrentUserSerializer},
        examples=[
            OpenApiExample("Aluno autenticado", value={"username": "maria"}, response_only=True),
        ],
    )
    def get(self, request: Request) -> Response:
        return Response(CurrentUserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Troca a senha do próprio aluno e devolve um par de tokens novo.

    Funciona mesmo com a troca obrigatória pendente, porque é o único caminho para
    resolvê-la. Os tokens emitidos antes da troca deixam de valer.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: TokenPairSerializer,
            400: OpenApiResponse(
                description="Senha atual errada, senha nova igual à atual ou reprovada na "
                "validação. O corpo traz o campo problemático como chave, com os motivos."
            ),
        },
        examples=[
            OpenApiExample(
                "Troca da senha temporária",
                value={"current_password": "Kx7mPq2Wd9Zt", "new_password": "MinhaSenhaNova#2026"},
                request_only=True,
            ),
            OpenApiExample(
                "Senha nova igual à atual",
                value={"new_password": ["A senha nova não pode ser igual à atual."]},
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        refresh = change_password(request.user, serializer.validated_data["new_password"])
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class LogoutView(APIView):
    """Bloqueia o token de renovação do próprio aluno, encerrando a sessão sob pedido.

    Depois de bloqueado, aquele token de renovação nunca mais emite um novo token de
    acesso — nem antes de expirar sozinho. O token deve pertencer a quem está fazendo o
    pedido: um token de outro aluno, mesmo que válido, é recusado. Funciona com a troca de
    senha pendente, para o aluno poder sair sem trocar.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        examples=[
            OpenApiExample(
                "Token a bloquear",
                value={
                    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCI..."
                },
                request_only=True,
            ),
            OpenApiExample(
                "Campo ausente",
                value={"detail": "Campo 'refresh' é obrigatório."},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Token inválido ou de outro aluno",
                value={"detail": "Token de renovação inválido."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses={
            205: OpenApiResponse(description="Token bloqueado com sucesso. Sem corpo de resposta."),
            400: OpenApiResponse(
                description="Campo 'refresh' ausente, token inválido, ou token que não pertence "
                "ao aluno autenticado."
            ),
        },
    )
    def post(self, request: Request) -> Response:
        raw_token = request.data.get("refresh")
        if not raw_token:
            return Response(
                {"detail": "Campo 'refresh' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(raw_token)
        except TokenError:
            return Response(
                {"detail": "Token de renovação inválido."}, status=status.HTTP_400_BAD_REQUEST
            )

        if str(token.payload.get("user_id")) != str(request.user.id):
            return Response(
                {"detail": "Token de renovação inválido."}, status=status.HTTP_400_BAD_REQUEST
            )

        token.blacklist()
        return Response(status=status.HTTP_205_RESET_CONTENT)
