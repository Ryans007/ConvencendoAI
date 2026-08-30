# Ciclo de revisão espaçada — proposta do agente professor

Status: **não validado**. Este documento registra uma ideia em discussão, pendente de
prototipagem. Nada aqui foi implementado.

## Contexto

O ciclo de revisão espaçada é a validação pedagógica pendente do projeto: o algoritmo de
repetição espaçada (SM-2) precisa continuar existindo, mas cartões de estudo (flashcards)
foram descartados como mecanismo de revisão — o argumento é que cartões servem para
aprender palavras novas isoladas, e isso não combina com um sistema focado em conversação.

Duas ideias anteriores foram discutidas e ficaram em aberto:

1. **Elicitação encoberta** — uma cena de conversa comum, com um tema escolhido para induzir
   o uso natural do item revisado, sem o aluno saber que está sendo revisado. Risco
   identificado: o alvo linguístico é estreito demais para garantir que a cena o produza de
   forma confiável, e a evasão do aluno não tem garantia de convergência dentro do próprio
   mecanismo.
2. **Recordação direta falada** — mostrar o item errado, o aluno produz a forma corrigida por
   áudio, o sistema avalia certo ou errado e mostra a forma correta em caso de erro, com
   autoavaliação de dificuldade. Risco identificado: estruturalmente muito próximo de um
   cartão de estudo, só que falado — o critério de exclusão dos cartões é a forma da
   interação (recordação isolada), não a modalidade (escrito versus falado), então essa
   versão pode ainda esbarrar no mesmo critério.

Este documento descreve uma terceira ideia, que parece resolver os dois riscos acima ao ser
uma conversa real com um interlocutor que ensina, em vez de uma cena disfarçada ou um cartão
falado.

## A ideia: um agente professor

Em vez de uma cena de papel (como as usadas nos cenários graduados) ou de um cartão isolado,
a sessão de revisão é uma conversa real com uma persona no papel de professor, que:

- explica o que o aluno errou e por quê;
- dá as alternativas corretas;
- faz uma pergunta real, situacional, que exige a resposta correta;
- espera o aluno falar;
- avalia a resposta.

Isso está claramente dentro de um sistema de conversação, porque há um interlocutor, há
turnos, e a interação é ensino direto — não é um cartão com frente e verso, nem uma cena que
tenta camuflar o alvo.

## Fluxo, por item revisado

```
1. O professor explica o que o aluno errou e por que está errado
2. O professor da as alternativas corretas
3. O professor faz uma pergunta real, situacional, que exige a resposta correta
4. O sistema espera o aluno falar
5. O aluno fala

6. Se a resposta esta errada:
     o avaliador da ate X tentativas dentro da mesma sessao
     se o aluno nao acerta depois de X tentativas:
       o item e marcado como errado
       o item volta a aparecer mais cedo (intervalo mais curto) para nova tentativa
   Se a resposta esta correta:
     o avaliador julga se o aluno teve dificuldade ou nao
       (nao e autoavaliacao do aluno -- e o agente que julga, a partir da fala)

7. O resultado de cada item (acertou sem dificuldade / acertou com dificuldade /
   errou depois de X tentativas) alimenta o algoritmo SM-2, recalculando o
   proximo intervalo de revisao daquele item
```

## O que já existe no núcleo e seria reaproveitado

O agente avaliador do núcleo conversacional já extrai, ao final de toda sessão graduada, até
quatro itens de erro de linguagem — cada um com a forma que o aluno produziu e a forma
correta. Essa extração já existe e seria a fonte dos itens que entram no banco de revisão;
o que falta é tudo o que vem depois: o agendamento por SM-2, a seleção dos itens vencidos, e
a sessão de revisão com o professor descrita acima.

## Diferenças em relação aos cenários graduados

- Não há rubrica de sete dimensões nem nota de 0 a 100.
- Não há cooldown de doze horas nem gate suave.
- Não há papel do aluno de uma trilha, nem trilha, nem nível de dificuldade.
- A atividade fica sempre disponível ao aluno, contanto que existam itens vencidos.
- O professor provavelmente não é um dos seis arquétipos interacionais usados nos cenários
  graduados (Gatekeeper, Avaliador, Aliado, Adversário, Autoridade, Par) — nenhum deles
  descreve alguém que ensina explicitamente sem resistência. É provável que essa persona
  viva fora do catálogo de arquétipos.

## Perguntas em aberto

Nenhuma das perguntas abaixo foi decidida. Ficam registradas para a próxima rodada de
discussão.

- **Valor de X** (quantas tentativas antes de marcar o item como errado). O núcleo já usa o
  limite de duas tentativas antes de mudar de assunto num cenário graduado; não está
  decidido se o mesmo limite vale aqui.
- **O quanto o professor nomeia o erro passado.** Dizer abertamente "você errou isso antes"
  versus enquadrar de forma mais sutil ("vamos praticar uma situação parecida") — os dois
  continuam sendo conversa real, a diferença é só de tom.
- **Quantos itens por sessão e quantos turnos ao todo.** O formato geral do projeto para
  atividades curtas é de cerca de oito turnos; não está calculado se isso é suficiente para
  explicar, exemplificar, ouvir e avaliar três ou quatro itens.
- **Onde essa persona professor vive no sistema** — como uma entidade própria, fora do
  catálogo de personas e arquétipos usado pelos cenários graduados, ou como uma extensão
  dele. Este documento assume que é uma entidade separada, mas isso não foi decidido.
- **Escopo do banco de itens de revisão** — já decidido: pertence ao
  aluno globalmente, não é escopado a uma trilha.

## Próximo passo sugerido

Antes de qualquer modelagem de dados ou código: prototipar o mecanismo isoladamente (fora do
schema definitivo do produto).
