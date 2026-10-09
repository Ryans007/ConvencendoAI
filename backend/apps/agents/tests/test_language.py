from apps.agents.services.language import looks_english


def test_portuguese_full_of_technology_names_is_still_portuguese():
    assert not looks_english("Decidi usar FastAPI com PostgreSQL e Redis porque era mais rápido.")
    assert not looks_english("Sim, trabalhei em equipe.")
    assert not looks_english("aplicativo web")
    assert looks_english("I found the new API needs extra data mapping.")
    assert looks_english("Could we push the deadline by a week?")
