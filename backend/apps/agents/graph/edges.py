from apps.agents.graph.state import ScenarioState


def student_left(state: ScenarioState) -> str:
    """Roteamento após `listen`: a entrada do aluno acabou?

    O conteúdo da fala nunca encerra a sessão. Procurar palavras como "goodbye" ou
    "exit" dentro da fala encerrava a cena quando o aluno só as usava numa frase
    ("our exit strategy"); para sair antes, a tela tem o próprio botão.
    """
    if state.get("should_end"):
        return "end"
    return "continue"


def make_scene_ended(max_turns: int):
    """Roteamento após `persona`: a cena foi resolvida, ou os turnos se esgotaram?"""

    def scene_ended(state: ScenarioState) -> str:
        if state.get("scene_resolved"):
            return "end"
        if state.get("turn_count", 0) >= max_turns:
            return "end"
        return "continue"

    return scene_ended
