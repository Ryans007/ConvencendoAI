# Avaliação da conversa

Como medir, com os modelos reais, se a **troca entre as personas** é natural e se cada persona
**respeita o papel** do cenário. Serve para comparar o antes e o depois de um ajuste de prompt,
de catálogo ou de modelo, e para ter números (e exemplos reais) para o TCC.

O comando faz chamadas **pagas** a modelos. Toda execução mostra antes, no máximo, quantas
chamadas fará, e recusa começar acima do teto (`--max-calls`, padrão 800).

## O que ele mede

| Camada | O que roda | O que mede |
|---|---|---|
| **1. Roteador** | 21 falas do aluno com o rótulo de quem ele chamou, repetidas 2 vezes | Acerto quando o aluno chama alguém pelo nome e falsos "chamados" quando ele só respondeu |
| **2. Situações fixas** | 15 pontos da conversa, de 3 a 5 amostras cada, com o nó real da persona | Se passa a vez quando o assunto é da colega, se quem entra se apresenta, uma pergunta só, a última fala dirigida ao aluno e perguntas de sim ou não sobre o papel, respondidas por um juiz |
| **3. Sessões completas** | 5 sessões do grafo real com um **aluno simulado** (perfil e instruções por fala, como "chame o Tom pelo nome") | Quem conduz cada rodada, por que a condução mudou (o aluno chamou, equilíbrio ou passagem de vez), rodadas com duas perguntas, rodadas que terminam dirigidas a outra persona e apresentação de quem estreia |

Além disso, um **juiz** (o modelo configurado como avaliador) julga cada fala de persona numa
lista de verificação: fica na função, age como o arquétipo, usa só os fatos da cena, não corrige
o inglês, responde primeiro ao aluno, não repete pergunta, no máximo uma pergunta, só inglês e
não entrega a tarefa.

O juiz recebe a conversa até a fala. Um fato que o **aluno** acabou de dizer e a persona
repete ou comenta não conta como inventado. A **última fala da sessão** é julgada como
fechamento: o sistema manda fechar sem pergunta, então o juiz não cobra pergunta nem resistência
dela, e olha se o fechamento combina com a função e o arquétipo.

As **métricas de troca** vêm do código (eventos registrados nos nós do grafo), não do juiz. O
juiz mede o papel, e por ser da mesma família das personas deve ser **calibrado** por uma pessoa
antes de suas taxas serem usadas como medida (veja abaixo).

## Como rodar

Sempre dentro do container:

```bash
docker compose exec backend python manage.py evaluate_conversation --dry-run
docker compose exec backend python manage.py evaluate_conversation --label baseline
```

Opções úteis:

| Opção | Para quê |
|---|---|
| `--dry-run` | Só mostra a estimativa de chamadas. Nenhuma chamada é feita. |
| `--layers router,situations,sessions` | Roda só algumas camadas. |
| `--scenario negociar-prazo --level 3` | Só um cenário e nível. |
| `--samples 5` | Amostras por situação (substitui o valor de cada caso). |
| `--persona-model openai/gpt-oss-120b` | Usa outro modelo de chat **só nesta execução** (id numérico ou `model_id`; também `--router-model` e `--judge-model`). A configuração gravada não muda. |
| `--no-judge` | Não chama o juiz: mais barato, sem a parte de papel. |
| `--max-calls 1200` | Teto de chamadas. |
| `--label antes-do-ajuste` | Nome da execução, na pasta e no relatório. |

Cada execução grava uma pasta `backend/.evaluation/AAAAMMDD-HHMMSS-<rótulo>/`, fora do git:

- `report.md`: o relatório em português (placar com as metas, erros do roteador, resultado de
  cada situação com exemplos das falas que falharam, as sessões com transcrição, o juiz e o
  consumo);
- `results.json`: os dados brutos;
- `review.csv`: só com `--calibration-sample N`.

O uso gerado aparece no admin (*Uso de modelos*) sem aluno e com o nome **avaliação**.

## Como ler o relatório

1. **Placar:** cada métrica com a meta e o resultado (✔, ✘ ou — quando a camada não rodou). As
   metas ficam em `apps/agents/evaluation/cases/targets.json`.
2. **Exemplos:** os números apontam o problema; as falas mostram como ele soa. Leia as falas
   que falharam antes de decidir o que ajustar.
3. **Sessões:** o aluno simulado fala melhor que um aluno real, e as amostras são pequenas.
   Compare duas execuções com a mesma configuração antes de acreditar numa diferença pequena.
4. **Consumo:** tokens por papel e o tempo por chamada da persona (mediana e 90%), para decidir
   se um modelo maior vale a latência.

## Como calibrar o juiz

```bash
docker compose exec backend python manage.py evaluate_conversation --label calibrar --calibration-sample 40
```

Abra o `review.csv` da pasta da execução (o Excel abre). A coluna `context` traz as falas que
vieram antes, as mesmas que o juiz recebeu: itens como "responde ao aluno primeiro", "não repete
pergunta" e "só usa fatos da cena" só se decidem com elas. Na coluna `human`, escreva `yes` ou
`no` (ou `sim` e `não`) conforme **você** ache que a fala cumpre o item. Salve e rode:

```bash
docker compose exec backend python manage.py evaluate_conversation --calibrate .evaluation/<pasta>/review.csv
```

Ele mostra a concordância total e por item, e as falas em que você discordou do juiz, com o
motivo dele. Linhas em branco ou com outra resposta ficam de fora. Só use as taxas do juiz como
medida depois de saber a concordância.

Editores de CSV que alinham as colunas com espaços, ou que gravam `campo , "texto, com vírgula"`,
são aceitos: a leitura ignora os espaços ao redor dos cabeçalhos e dos valores.

Um arquivo gerado antes de existir a coluna `context`, e que você já preencheu, ganha o contexto
sem perder as respostas:

```bash
docker compose exec backend python manage.py evaluate_conversation --add-context .evaluation/<pasta>/review.csv
```

O contexto vem do `results.json` da mesma pasta, e o arquivo original fica ao lado, como
`review.csv.bak`.

## Como acrescentar um caso

Os casos são JSON em `apps/agents/evaluation/cases/`, validados antes de qualquer chamada:

- `router.json`: uma fala do aluno, a conversa até ali, a persona da vez e `accepted` (quem é
  aceito como destinatário; `none` significa "ninguém"; `null` marca o caso como ambíguo, que
  aparece no relatório mas não entra na conta).
- `situations.json`: o ponto da conversa, a persona da vez, as marcas da rodada (`taking_over`,
  `addressed`) e `expect`, com verificações estruturais (`passes_to`, `no_handoff`,
  `single_question`, `last_line_to_student`, `introduces`, `scene_resolved`, `next_speaker`) e
  perguntas de sim ou não para o juiz (`{"judge": "..."}`).
- `students.json`: o perfil do aluno simulado e as instruções por fala (`beats`).
- `targets.json`: a meta de cada métrica, no mínimo (`min`) ou no máximo (`max`).

Uma persona, um cenário ou um nível que não existe interrompe a execução antes de qualquer
chamada, com a mensagem do caso e do que está errado.

## O que a avaliação não faz

- Não usa conversas de alunos reais: o sistema não guarda a transcrição das sessões.
- Não roda na integração contínua: cada execução custa dinheiro e depende de provedores.
- Não verifica a regra de perguntas técnicas: ela foi liberada por decisão de produto.
