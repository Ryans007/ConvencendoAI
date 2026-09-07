from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.serializers import LogoutSerializer, RegisterSerializer, TokenPairSerializer


class RegisterView(generics.CreateAPIView):
    """Cria uma conta nova com usuário e senha, e autentica na hora.

    Não exige um login separado depois: a resposta já traz o par de tokens (acesso e
    renovação), pronto para autenticar os próximos pedidos. A senha é validada pelas
    mesmas regras já aplicadas a contas criadas pelo admin (comprimento mínimo, não
    inteiramente numérica, não parecida com o nome de usuário, não uma senha comum).
    """

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        examples=[
            OpenApiExample(
                "Registro válido",
                value={"username": "aluno_novo", "password": "SenhaForte123!"},
                request_only=True,
            ),
            OpenApiExample(
                "Conta criada",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIi...",
                    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCI...",
                },
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Nome de usuário já existe",
                value={"username": ["Um usuário com este nome de usuário já existe."]},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Senha reprovada na validação",
                value={"password": ["Esta senha é muito comum."]},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses={
            201: TokenPairSerializer,
            400: OpenApiResponse(
                description="Nome de usuário já em uso, ou senha reprovada na validação. O corpo "
                "traz o campo problemático como chave, com a lista de motivos."
            ),
        },
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """Bloqueia o token de renovação do próprio aluno, encerrando a sessão sob pedido.

    Depois de bloqueado, aquele token de renovação nunca mais emite um novo token de
    acesso — nem antes de expirar sozinho. O token deve pertencer a quem está fazendo o
    pedido: um token de outro aluno, mesmo que válido, é recusado.
    """

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
