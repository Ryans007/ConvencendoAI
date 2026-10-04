# Backlog

Funcionalidades combinadas e ainda não implementadas. Bugs não entram aqui: cada bug vira
uma issue no GitHub.

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
