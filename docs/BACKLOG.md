# Backlog

Funcionalidades combinadas e ainda não implementadas. Bugs não entram aqui: cada bug vira
uma issue no GitHub.

## Aprendizado espaçado com o agente professor

**Situação atual.** Ao fim de cada sessão, o avaliador já extrai até 4 itens de erro de
linguagem, cada um com a forma que o aluno produziu e a forma correta. Mas esses itens
**não são gravados**: existem só durante a avaliação e se perdem. Nenhum agente corrige o
aluno, e isso é de propósito: as personas ficam no papel e nunca ensinam, e a correção só
aparece no relatório. O que volta numa sessão seguinte é só o resumo de memória da trilha.

**O que se quer.** Um agente professor, fora das cenas, que retoma com o aluno os erros que
ele cometeu, em intervalos que crescem conforme ele acerta (por exemplo, 1, 3, 7 e 14 dias),
até o item ser dominado.

```gherkin
Cenário: o erro da sessão vira item de revisão
  Dado que o aluno disse "I have worked there yesterday" numa sessão
  Quando a sessão for avaliada
  Então o item fica gravado com a forma produzida e a forma correta
  E a primeira revisão fica marcada para o dia seguinte

Cenário: revisão vencida aparece na jornada
  Dado que o aluno tem itens com a data de revisão já vencida
  Quando ele abrir a jornada
  Então a jornada mostra que há revisões pendentes com o professor

Cenário: acertar espaça, errar aproxima
  Dado uma revisão de um item com intervalo de 3 dias
  Quando o aluno usar a forma correta
  Então a próxima revisão fica para daqui a 7 dias
  Mas se ele errar de novo, a próxima revisão volta para o dia seguinte
```

**Caminho provável.**
- Um model para o item de revisão, com atributos para a forma produzida, a forma correta, o
  intervalo atual, a data da próxima revisão e os acertos.
- A revisão vencida é calculada por comparação de datas na leitura, como o cooldown, sem job
  agendado e sem Celery.
- O professor é um papel novo, com prompt próprio: o único que corrige o aluno.

**Decisões em aberto.**
- Formato da sessão com o professor: por voz, como as cenas, ou exercícios curtos na tela.
- O algoritmo do intervalo: caixas fixas, mais simples, ou um algoritmo que ajusta pela
  dificuldade de cada item.
- Se o professor tem um modelo próprio configurável no admin, como o roteador.

## Acesso por convite e painel do super-admin

**Situação atual.** Qualquer pessoa cria conta sozinha: a tela de entrada tem o modo de
cadastro, e a API tem `POST /api/auth/register/`. O admin do Django existe para o catálogo, os
modelos de LLM e a auditoria das tentativas. O sistema não envia e-mail nenhum.

**O que se quer.** Com a infraestrutura no ar, só entra quem o super-admin liberar. Não existe
cadastro pelo próprio usuário. O super-admin cria o acesso num painel; a pessoa recebe um
e-mail de confirmação com uma senha temporária e é obrigada a trocá-la no primeiro login. O
super-admin também pode desativar um acesso.

```gherkin
Cenário: não há cadastro aberto
  Dado uma pessoa sem acesso liberado
  Quando ela abrir a tela de entrada
  Então não existe opção de criar conta
  E a API não aceita cadastro

Cenário: super-admin libera um acesso
  Dado o super-admin no painel
  Quando ele cadastrar o e-mail de uma pessoa
  Então a pessoa recebe um e-mail de confirmação com uma senha temporária

Cenário: primeiro login exige trocar a senha
  Dado que a pessoa entrou com a senha temporária
  Então ela precisa definir uma senha nova antes de chegar à jornada

Cenário: acesso desativado
  Dado que o super-admin desativou o acesso de um aluno
  Quando o aluno tentar entrar
  Então a entrada é recusada
```

**Caminho provável.**
- Remover o cadastro da API e da tela de entrada.
- Um atributo no usuário que obriga a trocar a senha, e o fluxo de troca no primeiro login.
- O painel: o próprio admin do Django, com uma ação de "liberar acesso", ou uma tela própria
  no frontend, restrita ao super-admin.
- O envio de e-mail por um serviço próprio, isolado atrás de uma interface, para a troca de
  provedor não mexer no resto.

**Decisões em aberto.**
- **O provedor de e-mail.** O Resend é um serviço hospedado; o que ele tem de código aberto é
  o React Email, para montar os templates. Existem alternativas auto-hospedáveis compatíveis
  com a API do Resend (por exemplo, o useSend, antes chamado Unsend), além de um servidor SMTP
  próprio. Vale confirmar a opção antes de escolher.
- **Senha temporária ou link.** Uma senha temporária viaja em texto no e-mail; um link de
  definição de senha, com validade curta e uso único, evita isso.
- **O painel:** admin do Django ou tela própria.

## Cenário com mais de duas personas

**Situação atual.** O catálogo já aceita qualquer número de papéis por cenário, e o roteador e
o equilíbrio de turno escolhem entre todos. Mas o resto foi desenhado e medido com duas
personas: o prompt fala do "outro personagem", no singular; a passagem de vez e as regras de
equilíbrio foram calibradas com duas; e a tela da sessão mostra um único avatar, sem indicar
qual persona está falando.

**O que se quer.** Cenários com três ou mais personas que conversam entre si e com o aluno de
forma natural, sem que nenhuma monopolize a cena nem que o aluno se perca em quem está
falando.

```gherkin
Cenário: três personas dividem a cena
  Dado um cenário com três personas
  Quando a sessão correr até o fim
  Então as três falam ao longo da cena
  E nenhuma conduz mais rodadas seguidas que o máximo do cenário

Cenário: o aluno sabe quem está falando
  Dado um cenário com três personas
  Quando uma delas falar
  Então a tela mostra qual persona está falando

Cenário: o aluno chama uma das três pelo nome
  Dado um cenário com três personas
  Quando o aluno se dirigir a uma delas pelo nome
  Então é ela quem responde
```

**Caminho provável.**
- Revisar os prompts da persona e do roteador para "os outros personagens", no plural.
- Revisar a passagem de vez e a escolha de quem conduz para N personas.
- A tela da sessão mostra as personas da cena e destaca quem fala.
- Um cenário novo, semeado, e sessões simuladas para medir antes de publicar.

## Revisar as métricas de avaliação dos relatórios

**Situação atual.** A nota é a soma de sete dimensões com pesos por nível: objetivo,
fluência, vocabulário, gramática, pronúncia, pragmática e autonomia. O objetivo vem dos
critérios cumpridos, e as outras são julgadas pelo modelo sobre a transcrição. A
**pronúncia** tem peso em todos os níveis, mas **nunca é julgada**: o avaliador recebe só o
texto, nunca o áudio. Por isso ela não aparece no relatório, e a nota é normalizada sobre o
peso que foi avaliado. A autonomia passou a considerar as dicas. A calibração dos níveis 1 e
2 continua pendente.

**O que se quer.** Revisar se cada dimensão mede o que diz medir, se os números do relatório
fazem sentido para o aluno e para o nível, e o que fazer com a pronúncia.

```gherkin
Cenário: a nota acompanha uma avaliação humana
  Dado um conjunto de sessões de referência avaliadas por uma pessoa
  Quando o avaliador avaliar as mesmas sessões
  Então as notas de cada dimensão ficam próximas das notas humanas

Cenário: o relatório não mostra dimensão que não foi avaliada
  Dado uma dimensão que o avaliador não julga
  Quando o aluno abrir o relatório
  Então ela não aparece com nota
```

**Caminho provável.**
- Montar um conjunto de sessões de referência, reais e simuladas, por nível.
- Comparar as notas do avaliador com uma avaliação humana e ajustar as orientações de cada
  dimensão e os pesos.
- Decidir a pronúncia: tirá-la da rubrica ou avaliá-la a partir do áudio.
- Incluir aqui a calibração dos níveis 1 e 2.
