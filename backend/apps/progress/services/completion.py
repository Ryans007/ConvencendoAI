from apps.catalog.models import Scenario, Track
from apps.progress.models import Attempt


def is_scenario_completed(user, scenario: Scenario) -> bool:
    """Um cenário está concluído quando o aluno tem alguma tentativa aprovada nele,
    em qualquer nível — aprovar qualquer nível conclui o cenário.
    """
    return Attempt.objects.filter(user=user, scenario=scenario, passed=True).exists()


def is_track_completed(user, track: Track) -> bool:
    """Uma trilha está concluída quando todos os seus cenários estão."""
    scenarios = list(track.scenarios.all())
    if not scenarios:
        return False
    return all(is_scenario_completed(user, scenario) for scenario in scenarios)


def is_track_unlocked(user, track: Track) -> bool:
    """A primeira trilha por ordem está sempre liberada; as demais dependem da
    conclusão da trilha imediatamente anterior.
    """
    previous = Track.objects.filter(order__lt=track.order).order_by("-order").first()
    if previous is None:
        return True
    return is_track_completed(user, previous)


def is_scenario_unlocked(user, scenario: Scenario) -> bool:
    """Um cenário está liberado quando a trilha em que vive está liberada e, dentro
    dela, o cenário imediatamente anterior está concluído.
    """
    if not is_track_unlocked(user, scenario.track):
        return False

    previous = (
        Scenario.objects.filter(track=scenario.track, order__lt=scenario.order)
        .order_by("-order")
        .first()
    )
    if previous is None:
        return True
    return is_scenario_completed(user, previous)
