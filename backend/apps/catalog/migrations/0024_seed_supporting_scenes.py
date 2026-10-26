from django.db import migrations

TRAVEL_TRACK_SLUG = "viagem-e-intercambio"

RESTAURANT_TRACK = {
    "slug": "restaurante-e-servicos",
    "title": "Restaurante e Serviços",
    "order": 3,
    "student_role": "Você está morando em Nova York por alguns meses e saiu para jantar com "
    "sua amiga Mia no Bella Vista, um restaurante italiano do seu bairro.",
}

NEW_PERSONAS = {"Mike": "austin", "Ben": "daniel", "Olivia": "diana", "Mia": "autumn"}

LEVEL_THREE_WEIGHTS = {"pragmatics": 15, "vocabulary": 10}

NEW_ROOM_FACTS = (
    "Fatos da cena, para responder quando o hóspede perguntar (todos os personagens da cena "
    "conhecem todos eles): o quarto novo, no quinto andar, fica ao lado do elevador, e o "
    "elevador funciona a noite toda. O hotel tem um quarto livre no terceiro andar, no fim do "
    "corredor, longe do elevador e com o ar-condicionado funcionando. Esse quarto fica pronto "
    "em cerca de quinze minutos, e Mike leva as malas assim que ele estiver pronto. A troca não "
    "tem nenhum custo extra. Uma segunda troca no mesmo dia precisa da autorização do gerente. "
    "O hotel não oferece reembolso nem desconto na diária, e ninguém da cena tem autorização "
    "para prometer isso."
)

WRONG_ORDER_FACTS = (
    "Fatos da cena, para responder quando o cliente perguntar (todos os personagens da cena "
    'conhecem todos eles): o pedido anotado diz só "risoto de cogumelos", sem a observação '
    '"sem queijo", porque o garçom esqueceu de anotar. O queijo já vai misturado no risoto, '
    "então não dá para só tirar de cima. A cozinha refaz o risoto sem queijo em cerca de quinze "
    "minutos e pode passá-lo na frente dos outros pedidos. A gerente pode tirar o prato errado "
    "da conta ou oferecer uma sobremesa por conta da casa. O restaurante não dá desconto na "
    "conta inteira, e só a gerente autoriza tirar algo da conta."
)

BIRTHDAY_FACTS = (
    "Fatos da cena, para responder quando o cliente perguntar (todos os personagens da cena "
    "conhecem todos eles): no próximo sábado, a mesa grande, de doze lugares, está livre às "
    "sete ou às nove da noite. Grupos com mais de oito pessoas pedem o menu fechado de três "
    "pratos, por 45 dólares por pessoa, com opção vegetariana e risoto sem queijo. A reserva de "
    "grupo precisa de um sinal de 100 dólares, pago até quinta-feira, que é descontado da conta "
    "no sábado. O grupo pode trazer o próprio bolo, com taxa de 3 dólares por pessoa, e a "
    "gerente pode dispensar essa taxa. O restaurante não dá desconto no menu fechado nem "
    "dispensa o sinal."
)

SCENES = (
    {
        "track": TRAVEL_TRACK_SLUG,
        "slug": "quarto-novo-barulhento",
        "title": "Quarto novo barulhento",
        "order": 2,
        "objective": "Conseguir outro quarto silencioso ainda hoje, sem custo extra.",
        "context": "Logo depois de falar com a recepção sobre o ar-condicionado, você foi "
        "mudado para um quarto no quinto andar. Se você tinha escolhido o conserto, o técnico "
        "descobriu que a peça só chega amanhã, e o hotel o mudou de quarto mesmo assim. Mike, o "
        "carregador, levou suas malas. O quarto novo fica colado ao elevador e o barulho não "
        "para. Você desce com Mike até a recepção, onde Emma atende. James, o gerente, ainda "
        "está no balcão.",
        "closing_hint": "The conversation is nearly over. Say out loud which room the guest "
        "is moving to and when it will be ready, so the guest knows exactly what to expect.",
        "facts": NEW_ROOM_FACTS,
        "roles": (
            {
                "persona": "Emma",
                "archetype": "Gatekeeper",
                "scene_function": "recepcionista do hotel",
                "traits": "educada, um pouco constrangida por ser o segundo problema, segue o "
                "procedimento",
                "resistance": "primeiro oferece uma solução no mesmo quarto (tampões de ouvido "
                "e pedir à manutenção que confira o elevador); pergunta o que exatamente "
                "incomoda antes de procurar outro quarto",
                "concession": "procura outro quarto quando o hóspede explica o barulho e pede "
                "para sair do quarto; como é a segunda troca no mesmo dia, chama James para "
                "autorizar",
                "decides_outcome": False,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 1,
            },
            {
                "persona": "James",
                "archetype": "Autoridade",
                "scene_function": "gerente do hotel",
                "traits": "calmo, resolve rápido, quer o hóspede satisfeito",
                "resistance": "lembra que já é a segunda troca de hoje e pergunta exatamente o "
                "que o hóspede precisa no quarto novo, para não errar de novo",
                "concession": "autoriza o quarto do terceiro andar, longe do elevador, e "
                "confirma em quanto tempo ele fica pronto",
                "decides_outcome": True,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 2,
            },
            {
                "persona": "Mike",
                "archetype": "Aliado",
                "scene_function": "carregador de malas do hotel",
                "traits": "simpático, fala pouco, subiu com o hóspede e ouviu o barulho",
                "resistance": "não decide nada nem promete quarto; só conta o que viu e o que "
                "sabe dos andares",
                "concession": "confirma o barulho do elevador quando o hóspede descreve o "
                "problema, e se oferece para levar as malas de novo",
                "decides_outcome": False,
                "presence": "supporting",
                "entry_cue": "When the guest describes the problem with the new room",
                "opening_order": 3,
            },
        ),
        "criteria": (
            ("c1", "Explicou claramente qual é o problema do quarto novo"),
            (
                "c2",
                "Pediu um quarto com uma condição concreta (longe do elevador ou em outro andar)",
            ),
            ("c3", "Perguntou quando o quarto fica pronto ou como as malas vão ser levadas"),
            ("c4", "Confirmou qual é o quarto novo e quando a troca acontece"),
        ),
        "comprehension": "Respondeu de forma clara e coerente às perguntas de sim ou não "
        "feitas pela recepção sobre o quarto novo",
    },
    {
        "track": RESTAURANT_TRACK["slug"],
        "slug": "pedido-errado",
        "title": "Pedido errado",
        "order": 1,
        "objective": "Resolver o prato que chegou errado: conseguir o prato certo logo e não "
        "pagar pelo erro.",
        "context": "Você e Mia jantam no Bella Vista numa sexta-feira à noite, e a casa está "
        "cheia. Você pediu um risoto de cogumelos sem queijo, porque tem intolerância a "
        "lactose, mas o risoto chegou coberto de queijo. Mia estava junto quando você fez o "
        "pedido. Ben é o garçom da mesa e Olivia é a gerente do restaurante.",
        "closing_hint": "The conversation is nearly over. Say out loud what the restaurant is "
        "going to do about the dish and the bill, and how long the new dish will take.",
        "facts": WRONG_ORDER_FACTS,
        "roles": (
            {
                "persona": "Ben",
                "archetype": "Gatekeeper",
                "scene_function": "garçom da mesa",
                "traits": "simpático, apressado, a casa está cheia",
                "resistance": 'primeiro diz que anotou só "risoto" e oferece tirar o queijo de '
                "cima; pergunta o que exatamente foi pedido",
                "concession": "aceita mandar refazer o prato quando o cliente explica o que "
                "pediu e por que não pode comer queijo; para tirar o prato da conta, chama "
                "Olivia",
                "decides_outcome": False,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 1,
            },
            {
                "persona": "Olivia",
                "archetype": "Autoridade",
                "scene_function": "gerente do restaurante",
                "traits": "calma, educada, cuida da reputação da casa",
                "resistance": "pergunta o que aconteceu e o que o cliente prefere antes de decidir",
                "concession": "manda refazer o risoto com prioridade e tira o prato da conta",
                "decides_outcome": True,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 2,
            },
            {
                "persona": "Mia",
                "archetype": "Aliado",
                "scene_function": "sua amiga, que janta com você",
                "traits": "animada, educada, está do seu lado",
                "resistance": "não faz a reclamação por você nem fala com a gerente no seu lugar",
                "concession": "confirma que você pediu o risoto sem queijo quando o garçom "
                "duvida do pedido",
                "decides_outcome": False,
                "presence": "supporting",
                "entry_cue": "When the waiter doubts what the student ordered",
                "opening_order": 3,
            },
        ),
        "criteria": (
            ("c1", "Explicou o que pediu e o que chegou errado"),
            ("c2", "Explicou por que não pode comer o prato que chegou"),
            ("c3", "Pediu uma solução concreta (refazer o prato, trocar ou tirar da conta)"),
            ("c4", "Confirmou o que o restaurante vai fazer e em quanto tempo"),
        ),
        "comprehension": "Respondeu de forma clara e coerente às perguntas de sim ou não "
        "feitas pelo garçom e pela gerente sobre o pedido",
    },
    {
        "track": RESTAURANT_TRACK["slug"],
        "slug": "reservar-aniversario",
        "title": "Reservar o aniversário",
        "order": 2,
        "objective": "Reservar uma mesa para dez pessoas no próximo sábado, para o seu "
        "aniversário, com um preço que caiba no grupo.",
        "context": "Ainda no mesmo jantar no Bella Vista, depois que o problema do prato foi "
        "resolvido, você aproveita para reservar uma mesa para comemorar o seu aniversário no "
        "próximo sábado, com dez amigos. Mia vai ajudar a organizar a festa. Olivia, a gerente, "
        "cuida das reservas, e Ben vai atender a mesa no sábado.",
        "closing_hint": "The conversation is nearly over. Say out loud the booking details: "
        "the day, the time, the number of people, the menu and what the student needs to pay "
        "in advance.",
        "facts": BIRTHDAY_FACTS,
        "roles": (
            {
                "persona": "Olivia",
                "archetype": "Autoridade",
                "scene_function": "gerente do restaurante, cuida das reservas",
                "traits": "profissional, quer compensar o problema de hoje sem abrir exceção "
                "demais",
                "resistance": "segue as regras de grupo da casa (menu fechado e sinal); "
                "pergunta data, horário e número de pessoas antes de prometer qualquer coisa",
                "concession": "fecha a reserva quando o cliente diz data, horário e número de "
                "pessoas e aceita o menu de grupo; por causa do problema de hoje, dispensa a "
                "taxa do bolo se o cliente pedir",
                "decides_outcome": True,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 1,
            },
            {
                "persona": "Ben",
                "archetype": "Gatekeeper",
                "scene_function": "garçom que vai atender a mesa no sábado",
                "traits": "prestativo, conhece bem o cardápio",
                "resistance": "lembra que grupos com mais de oito pessoas só podem pedir o menu "
                "fechado; pergunta se alguém do grupo tem restrição alimentar",
                "concession": "explica as opções do menu fechado, incluindo o risoto sem "
                "queijo, quando o cliente pergunta",
                "decides_outcome": False,
                "presence": "principal",
                "entry_cue": "",
                "opening_order": 2,
            },
            {
                "persona": "Mia",
                "archetype": "Aliado",
                "scene_function": "sua amiga, que ajuda a organizar a festa",
                "traits": "animada, prática, conhece os amigos do grupo",
                "resistance": "não fecha a reserva nem negocia no seu lugar",
                "concession": "confirma quantas pessoas vêm e quanto o grupo pode gastar quando "
                "o preço entra na conversa",
                "decides_outcome": False,
                "presence": "supporting",
                "entry_cue": "When the price or the number of guests comes up",
                "opening_order": 3,
            },
        ),
        "criteria": (
            ("c1", "Disse a data, o horário e quantas pessoas vêm"),
            ("c2", "Perguntou sobre o cardápio ou o preço por pessoa"),
            ("c3", "Negociou uma condição (o bolo, o sinal ou o horário)"),
            ("c4", "Confirmou a reserva com data, horário e o que precisa pagar antes"),
        ),
        "comprehension": "Respondeu de forma clara e coerente às perguntas de sim ou não "
        "feitas pela gerente e pelo garçom sobre a reserva",
    },
)


def seed_supporting_scenes(apps, schema_editor):
    """Semeia as três cenas de três personagens: a segunda cena do hotel e a trilha do
    restaurante.

    Cada cena tem duas personas principais e um coadjuvante, que fala pouco e nunca decide. Os
    três papéis de cada cena recebem os mesmos fatos, porque uma pergunta do aluno sem nome vai
    para quem está falando com ele e todos precisam dar a mesma resposta. A carga usa
    `update_or_create` por slug e por nome, e pode ser aplicada de novo sem duplicar nada.
    """
    Track = apps.get_model("catalog", "Track")
    Persona = apps.get_model("catalog", "Persona")
    Scenario = apps.get_model("catalog", "Scenario")
    Archetype = apps.get_model("catalog", "Archetype")
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")
    Criterion = apps.get_model("catalog", "Criterion")
    Level = apps.get_model("catalog", "Level")
    ScenarioLevelWeightOverride = apps.get_model("catalog", "ScenarioLevelWeightOverride")

    restaurant = dict(RESTAURANT_TRACK)
    Track.objects.update_or_create(slug=restaurant.pop("slug"), defaults=restaurant)
    for name, voice in NEW_PERSONAS.items():
        Persona.objects.update_or_create(name=name, defaults={"voice": voice})

    level_1 = Level.objects.get(order=1)
    level_3 = Level.objects.get(order=3)
    production_levels = list(Level.objects.filter(order__in=[2, 3]))

    for scene in SCENES:
        scenario, _ = Scenario.objects.update_or_create(
            slug=scene["slug"],
            defaults={
                "track": Track.objects.get(slug=scene["track"]),
                "title": scene["title"],
                "order": scene["order"],
                "objective": scene["objective"],
                "context": scene["context"],
                "closing_hint": scene["closing_hint"],
                "cooldown_hours": 12,
                "max_consecutive_turns": 5,
            },
        )
        for role in scene["roles"]:
            ScenarioRole.objects.update_or_create(
                scenario=scenario,
                persona=Persona.objects.get(name=role["persona"]),
                defaults={
                    "archetype": Archetype.objects.get(name=role["archetype"]),
                    "scene_function": role["scene_function"],
                    "traits": role["traits"],
                    "resistance": role["resistance"],
                    "concession": role["concession"],
                    "extra_instruction": scene["facts"],
                    "decides_outcome": role["decides_outcome"],
                    "presence": role["presence"],
                    "entry_cue": role["entry_cue"],
                    "opening_order": role["opening_order"],
                },
            )
        for order, (code, text) in enumerate(scene["criteria"], start=1):
            criterion, _ = Criterion.objects.update_or_create(
                scenario=scenario, code=code, defaults={"text": text, "order": order}
            )
            criterion.levels.set(production_levels)
        criterion, _ = Criterion.objects.update_or_create(
            scenario=scenario,
            code="c5",
            defaults={"text": scene["comprehension"], "order": len(scene["criteria"]) + 1},
        )
        criterion.levels.set([level_1])
        for dimension, weight in LEVEL_THREE_WEIGHTS.items():
            ScenarioLevelWeightOverride.objects.update_or_create(
                scenario=scenario,
                level=level_3,
                dimension=dimension,
                defaults={"weight": weight},
            )


def remove_supporting_scenes(apps, schema_editor):
    """Remove só o que a carga criou: as três cenas, a trilha do restaurante e as personas
    novas que não estejam em nenhum outro cenário.

    Papéis, critérios e ajustes de peso saem junto com as cenas. As tentativas de aluno
    protegem o cenário, então desfazer falha se alguém já fez uma das cenas novas, em vez de
    apagar o histórico dele.
    """
    Track = apps.get_model("catalog", "Track")
    Persona = apps.get_model("catalog", "Persona")
    Scenario = apps.get_model("catalog", "Scenario")

    Scenario.objects.filter(slug__in=[scene["slug"] for scene in SCENES]).delete()
    Track.objects.filter(slug=RESTAURANT_TRACK["slug"], scenarios__isnull=True).delete()
    Persona.objects.filter(name__in=NEW_PERSONAS, scenario_roles__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0023_scenario_role_presence"),
    ]

    operations = [
        migrations.RunPython(seed_supporting_scenes, remove_supporting_scenes),
    ]
