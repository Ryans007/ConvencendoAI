from apps.llm.key_box import open_sealed, seal

_SECRET = "gsk_SEGREDO-DA-CHAVE-123456"


def test_a_sealed_key_opens_back_to_the_same_value():
    assert open_sealed(seal(_SECRET)) == _SECRET


def test_the_sealed_token_does_not_contain_the_plain_key():
    token = seal(_SECRET)

    assert _SECRET not in token
    assert "SEGREDO" not in token


def test_a_token_sealed_with_another_secret_key_opens_as_empty(settings):
    settings.SECRET_KEY = "uma-chave-secreta"
    token = seal(_SECRET)

    settings.SECRET_KEY = "outra-chave-secreta"

    assert open_sealed(token) == ""


def test_garbage_opens_as_empty():
    assert open_sealed("isto-nao-e-um-token") == ""


def test_empty_stays_empty():
    assert seal("") == ""
    assert open_sealed("") == ""
