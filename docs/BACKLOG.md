# Backlog

Funcionalidades combinadas e ainda não implementadas. Bugs não entram aqui: cada bug vira
uma issue no GitHub.

## Ver o último relatório de cada nível

**Situação atual.** O relatório de toda tentativa concluída já fica salvo no banco: nota
final, sub-nota de cada dimensão, resultado de cada critério e feedback (`Attempt`,
`ScoreBreakdown` e `AttemptCriterion`), e a API o devolve em `GET /api/attempts/<id>/`.
Mas o aluno só chega a ele no fim da sessão, porque a jornada não informa qual foi a
última tentativa de cada nível. Fechou a tela do relatório, não tem mais como voltar a
ele.

**O que se quer.** Na jornada, cada nível já tentado mostra o acesso ao relatório da
última tentativa concluída naquele nível, aprovada ou reprovada.

```gherkin
Cenário: aluno revê o relatório de um nível já tentado
  Dado que o aluno concluiu uma tentativa no nível 1 da entrevista
  Quando ele abrir a jornada
  Então o nível 1 da entrevista mostra o acesso ao último relatório
  E ao abrir, ele vê a nota, as sub-notas, os critérios e o feedback daquela tentativa

Cenário: vale a tentativa mais recente, aprovada ou não
  Dado que o aluno foi aprovado no nível 1 e depois tentou de novo e foi reprovado
  Quando ele abrir o último relatório do nível 1
  Então ele vê o relatório da tentativa reprovada, a mais recente

Cenário: nível nunca tentado
  Dado que o aluno nunca concluiu uma tentativa no nível 2
  Quando ele abrir a jornada
  Então o nível 2 não mostra acesso a relatório

Cenário: relatório de outro aluno (já garantido hoje, a preservar)
  Dado o id de uma tentativa de outro aluno
  Quando o aluno tentar abrir esse relatório
  Então a API responde "não encontrado", como se a tentativa não existisse
```

**Caminho provável.**
- A jornada (`GET /api/journey/`) passa a devolver, em cada nível, a última tentativa
  concluída: id, nota, aprovação e data.
- A tela da jornada ganha o acesso ao relatório, que abre a tela de relatório já
  existente.

Nenhum dado novo precisa ser gravado.

## Mostrar a dica da persona na tela da sessão por voz

**Situação atual.** Em toda rodada a persona gera uma dica em português, curta, que diz
como responder à pergunta feita (por exemplo, "Sim ou não." no nível 1). A política de
dicas de cada nível já decide quando ela aparece: sempre, só quando o aluno trava, ou
nunca. Mas, na sessão por voz, a dica **não chega à tela**: o WebSocket só envia o áudio
das personas e mensagens de controle, por decisão de produto (sessão sem transcrição na
tela). A dica só aparece no log do servidor e na execução pelo terminal.

**O que se quer.** Na tela da sessão por voz, mostrar a dica da rodada quando a política
do nível permitir, sem mostrar a transcrição da fala da persona.

```gherkin
Cenário: nível com dica sempre visível
  Dado uma sessão no nível 1, cuja política de dicas é "sempre"
  Quando a persona terminar de falar
  Então a tela mostra a dica da rodada, em português
  E não mostra o texto da fala da persona

Cenário: nível em que a dica só aparece quando o aluno trava
  Dado uma sessão no nível 2, cuja política de dicas é "quando travar"
  Quando o aluno responder normalmente
  Então a tela não mostra a dica

Cenário: nível sem dica
  Dado um nível cuja política de dicas é "nunca"
  Quando a persona terminar de falar
  Então a tela não mostra nenhuma dica
```

**Caminho provável.**
- O servidor envia uma mensagem de controle `hint` junto das falas de cada rodada,
  respeitando a política de dicas do nível.
- A tela da sessão mostra a dica enquanto é a vez do aluno.
- Decisão a tomar antes: a dica revela o que a persona perguntou, o que aproxima a
  sessão de uma transcrição. Vale confirmar que isso é aceitável para o produto.
