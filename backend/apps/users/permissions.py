from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

PASSWORD_CHANGE_REQUIRED_CODE = "password_change_required"


class PasswordChangeNotRequired(BasePermission):
    """Recusa todo pedido de quem ainda não trocou a senha temporária.

    Entra em `DEFAULT_PERMISSION_CLASSES`, então vale para toda rota protegida sem que cada
    view precise lembrar dela. A resposta é um 403 com um código próprio no corpo, para o
    cliente levar o aluno à tela de troca em vez de mostrar um erro genérico. A troca de senha
    e o logout declaram as próprias permissões, sem esta, para continuarem funcionando.

    Um usuário anônimo passa por aqui sem ser tocado: quem o recusa, com 401, é a permissão
    de autenticação que vem junto.
    """

    message = "Defina uma senha nova antes de continuar."

    def has_permission(self, request: Request, view) -> bool:
        user = request.user
        if user and user.is_authenticated and user.must_change_password:
            raise PermissionDenied(
                {"detail": self.message, "code": PASSWORD_CHANGE_REQUIRED_CODE}
            )
        return True
