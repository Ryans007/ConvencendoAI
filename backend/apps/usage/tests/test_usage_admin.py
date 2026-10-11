from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.llm.models import LLMModel, LLMProvider
from apps.usage.constants import UsagePurpose
from apps.usage.models import ModelUsage
from apps.usage.services.usage_totals import month_start, usage_breakdown, usage_totals

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password=_PASSWORD
    )


@pytest.fixture
def llm():
    provider = LLMProvider.objects.create(code="g", name="G", base_url="https://x/v1", api_key="k")
    return LLMModel.objects.create(provider=provider, model_id="gpt-oss", display_name="g")


def _usage(llm, user=None, purpose=UsagePurpose.PERSONA, cost="0.001", days_ago=0, **fields):
    row = ModelUsage.objects.create(
        user=user,
        username_at_time=user.username if user else "",
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


def test_the_superuser_lists_the_usage_with_totals_of_the_filtered_cut(
    client, superuser, django_user_model, llm
):
    maria = django_user_model.objects.create_user(username="maria")
    joao = django_user_model.objects.create_user(username="joao")
    _usage(llm, maria, input_tokens=100, output_tokens=20, cost="0.001")
    _usage(llm, maria, input_tokens=50, output_tokens=10, cost="0.002")
    _usage(llm, joao, input_tokens=999, output_tokens=1, cost="0.5")
    client.force_login(superuser)

    page = client.get(reverse("admin:usage_modelusage_changelist"), {"user__id__exact": maria.pk})
    totals = page.context["usage_totals"]

    assert page.status_code == 200
    assert (totals.calls, totals.input_tokens, totals.output_tokens) == (2, 150, 30)
    assert totals.cost_usd == Decimal("0.003")


def test_the_usage_screen_is_read_only_and_only_for_the_superuser(
    client, superuser, django_user_model, llm
):
    row = _usage(llm)
    staff = django_user_model.objects.create_user(
        username="equipe", password=_PASSWORD, is_staff=True
    )
    staff.user_permissions.set(Permission.objects.filter(content_type__app_label="usage"))

    client.force_login(staff)
    assert client.get(reverse("admin:usage_modelusage_changelist")).status_code == 403
    assert "uso de modelos" not in client.get(reverse("admin:index")).content.decode().lower()

    client.force_login(superuser)
    delete_url = reverse("admin:usage_modelusage_delete", args=[row.pk])
    change = client.get(reverse("admin:usage_modelusage_change", args=[row.pk]))
    assert client.post(reverse("admin:usage_modelusage_add"), {}).status_code == 403
    assert client.post(delete_url, {"post": "yes"}).status_code == 403
    assert change.status_code == 200
    assert b'name="_save"' not in change.content


def test_system_use_is_listed_as_system(client, superuser, llm):
    _usage(llm, None)
    client.force_login(superuser)

    page = client.get(reverse("admin:usage_modelusage_changelist")).content.decode()

    assert "sistema" in page


def test_the_breakdown_separates_by_purpose_and_model_and_by_period(django_user_model, llm):
    maria = django_user_model.objects.create_user(username="maria")
    _usage(llm, maria, UsagePurpose.PERSONA, input_tokens=100, output_tokens=10, cost="0.01")
    _usage(llm, maria, UsagePurpose.JUDGE, input_tokens=200, output_tokens=20, cost="0.02")
    _usage(
        llm, maria, UsagePurpose.JUDGE, input_tokens=300, output_tokens=30, cost="0.03",
        days_ago=70,
    )

    everything = {row.purpose: row for row in usage_breakdown(maria)}
    month = {row.purpose: row for row in usage_breakdown(maria, month_start())}

    assert everything["judge"].input_tokens == 500
    assert everything["judge"].cost_usd == Decimal("0.05")
    assert month["judge"].input_tokens == 200
    assert set(month) == {"persona", "judge"}


def test_the_totals_of_nothing_are_zero(llm):
    totals = usage_totals(ModelUsage.objects.all())

    assert (totals.calls, totals.input_tokens, totals.cost_usd) == (0, 0, 0)
