from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.llm.models import LLMModel, LLMProvider
from apps.progress.models import Attempt
from apps.usage.constants import UsagePurpose
from apps.usage.models import ModelUsage

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password="Xk9#mQ2vLp8Z"
    )


@pytest.fixture
def llm():
    provider = LLMProvider.objects.create(code="g", name="G", base_url="https://x/v1", api_key="k")
    return LLMModel.objects.create(provider=provider, model_id="gpt-oss", display_name="g")


def _usage(llm, user, purpose=UsagePurpose.PERSONA, cost="0.001", days_ago=0, **fields):
    row = ModelUsage.objects.create(
        user=user,
        username_at_time=user.username,
        purpose=purpose,
        llm_model=llm,
        model_id_at_time=llm.model_id,
        cost_usd=Decimal(cost),
        priced=True,
        **fields,
    )
    if days_ago:
        ModelUsage.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return row


def test_the_user_list_shows_the_month_tokens_and_cost_without_inflating_by_attempts(
    client, superuser, django_user_model, llm
):
    maria = django_user_model.objects.create_user(username="maria")
    for level in (1, 2, 3):
        Attempt.objects.create(
            user=maria,
            scenario=Scenario.objects.get(slug="negociar-prazo"),
            level=Level.objects.get(order=level),
        )
    _usage(llm, maria, input_tokens=100, output_tokens=20, cost="0.0100")
    _usage(llm, maria, input_tokens=1, output_tokens=1, cost="9", days_ago=70)
    client.force_login(superuser)

    page = client.get(reverse("admin:users_user_changelist"))
    row = next(u for u in page.context["cl"].result_list if u.username == "maria")

    assert row.month_tokens == 120
    assert row.month_cost == Decimal("0.0100")
    assert row.sessions_started == 3


def test_the_user_detail_shows_the_usage_by_purpose_and_model(
    client, superuser, django_user_model, llm
):
    maria = django_user_model.objects.create_user(username="maria")
    _usage(llm, maria, UsagePurpose.JUDGE, input_tokens=100, output_tokens=20, cost="0.0100")
    client.force_login(superuser)

    page = client.get(reverse("admin:users_user_change", args=[maria.pk])).content.decode()

    assert "Uso de modelos neste mês" in page
    assert "Uso de modelos em todo o período" in page
    assert "gpt-oss" in page
    assert "estimativas" in page
