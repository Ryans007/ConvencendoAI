from django import forms
from django.contrib.auth import get_user_model


class InviteForm(forms.ModelForm):
    """Cria um acesso: o super-admin informa só o nome de usuário e o e-mail.

    A senha não é digitada, quem a gera é o sistema. O e-mail é obrigatório e guardado em
    minúsculas, para a regra de e-mail único, que o banco aplica sem diferenciar caixa,
    barrar o mesmo endereço escrito de outro jeito antes de chegar ao banco.
    """

    email = forms.EmailField(label="E-mail", help_text="O e-mail da pessoa; não se repete.")

    class Meta:
        model = get_user_model()
        fields = ["username", "email"]

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()
