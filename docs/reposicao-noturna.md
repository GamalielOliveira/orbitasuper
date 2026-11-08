# Reposição noturna — proposta para revisão

Esta página explica a proposta. Ela **não liga** a reposição, **não roda** migration no banco real, **não aplica** estoque e **não instala** cron. O corte de ativação **ainda não foi escolhido**. Enquanto essa data não entrar na mão de quem opera, `--aplicar` recusa e não grava nada.

Cada bloco abaixo é **um comando só**. Não junte com `&&`, não faça um script que migre, aplique e agende juntos, e não leia nem dê `source` em `.env.prod`.

O relógio do dia é `America/Sao_Paulo`. A VPS de referência está em `Etc/UTC`. 04:00 em Brasília é 07:00 UTC. Desde 2019 esse fuso não usa horário de verão, então a conta se mantém o ano inteiro. Se um dia o deslocamento mudar, a hora do cron precisa ser revista. O dia da saída continua certo porque o SQL usa o nome do fuso, não um `-3` fixo.

## O que entra na conta

Uma saída elegível é uma linha de `movimentacoes_estoque` com:

- `tipo = saida`
- `campo = quantidade`
- `quantidade` negativa (saiu do físico)
- `loja_id` da loja pedida (na operação, a loja 2)
- dia de `criado_em` em São Paulo **maior ou igual ao corte** e **menor que o dia da execução**

A demanda do produto é a soma dessas unidades, sempre positiva. Reserva, liberação, perda, ajuste, entrada e saída que não seja física negativa são ignoradas. Não entram na soma e não são vinculadas.

Há um estoque só, o de `lotes`. Não há separação de prateleira e depósito. Cada execução cria **um lote novo por produto**, com uma `entrada` no extrato. Isso registra o recebimento já concluído. Não há fila de separador, nem turno, nem tarefa de funcionário. O comando é só o recibo.

## O que não entra

- Pedido, reserva e liberação. Ontem a referência observada foi de saídas (427 SKUs, 600 unidades), não de pedidos.
- Entrada manual. Ela **não é abatida** da saída e **não é tratada como se cobrisse** uma saída. O `POST /gerente/estoque/reposicao` continua só de gerente, sem idempotência: chamar de novo soma estoque de novo. A reposição noturna não chama essa rota, não usa o crachá 9001 e não fabrica token.
- O gerente 9001 repôs hoje 172 SKUs × 20 = 3440 unidades, e 22 SKUs também tiveram saída ontem. Não dá para saber qual entrada manual corresponde a qual saída. Por isso **não há backfill**. Esse passado fica antes do corte.
- Simulador, escala, horário de abertura, meta de pedidos e ticket. O tick de 5 minutos e o fechamento às 22:00 com drenagem até cerca de 00:55 continuam como estão.

## Corte

O corte é o primeiro dia de São Paulo cujas saídas podem ser repostas. Dias anteriores nunca são vinculados, mesmo que alguém lance a saída depois.

O corte **não está gravado** em config, ambiente nem banco. Cada `--aplicar` precisa receber `--corte AAAA-MM-DD`. Sem isso o comando para e não grava.

Para não repor o período ambíguo, a data segura é um dia que **ainda não começou** (amanhã no calendário de São Paulo). A madrugada seguinte é a primeira que encontra um dia encerrado dentro do corte. Escolher um dia já vivido inclui esse dia e os seguintes ainda não vinculados. Só faça isso de propósito, depois de ler a prévia.

## Chegada tardia e lançamento atrasado

O dia da saída é o dia de `criado_em` em São Paulo, não o dia em que o pedido foi aberto.

A loja fecha às 22:00. Quem já estava em entrega pode concluir até cerca de 00:55 (o simulador deixa a equipe que sai no fechamento drenar por até 3 horas; no tick o horário gravado é o relógio real). Uma entrega às 00:40 já pertence ao dia novo.

A execução das 04:00 não pega esse movimento: o dia dele ainda é “hoje”, e hoje não está encerrado. Também não pega saída entre 00:00 e 04:00. Esses movimentos entram na madrugada **seguinte**, uma vez.

Se uma saída for inserida depois, com `criado_em` num dia que já passou, a próxima execução pega essa linha se o dia for maior ou igual ao corte e ainda não houver vínculo. O mesmo vale para uma madrugada que deixou de rodar: na execução seguinte, todo dia já encerrado, dentro do corte e ainda sem vínculo, entra no mesmo recibo (um lote por produto, somando esses dias). Isso não reabre o período anterior ao corte. Não existe modo de escolher um intervalo antigo à parte.

Rodar de novo no mesmo dia não duplica. Duas execuções ao mesmo tempo, na mesma loja, esperam um cadeado da transação. A segunda vê o vínculo da primeira e não cria outro lote. Se a gravação quebra no meio, a transação desfaz lote, extrato e vínculo juntos.

## Rastro

O ator no extrato é o texto `AUTO`. Não é matrícula, não é o 9001 e não existe em `funcionarios`. A coluna Func. do extrato mostra esse texto cru; a tela não busca nome em `funcionarios` e não quebra se a matrícula não existir. Se alguém cadastrar uma pessoa com matrícula `AUTO`, o comando recusa, para não assinar no lugar dela.

Cada saída elegível ganha uma linha em `reposicao_noturna_origem` apontando para a execução (`reposicoes_noturnas`), o lote novo e a movimentação de entrada. A chave é o id da saída: não há segunda linha para a mesma origem.

O motivo da entrada cita reposição noturna, a loja, o dia da saída e as unidades. A data de entrada do lote é a manhã da execução (o dia em que o recibo é lançado), não o dia da venda. A validade reutiliza o prazo do último lote **daquela loja**; sem prazo, perecível fica em 7 dias e o resto em 180. O lote novo não nasce vencido.

A API manual de entrada continua na loja de menor id quando ninguém informa loja. A reposição noturna passa a loja 2 explícita.

## Conferir, um comando por vez

Nada disto roda na VPS nesta revisão. O container que está no ar foi montado no commit `0b78964` e **não contém** este comando nem esta migration. Não rode `python` nem `alembic` no host: o banco de produção só existe na rede do Compose, e o fallback do código é o banco de desenvolvimento.

O script conhecido é `/opt/super-backups/backup.sh`. O conteúdo dele não foi lido. Não execute o script neste passo: ele pode ler senha ou gravar dump.

O único comando desta etapa, na raiz da VPS:

```bash
ls -lh /opt/super-backups/backup.sh
```

Se o `ls` disser que o arquivo não existe, pare. Não procure outro caminho e não abra `.env.prod`.

## Decisões que ainda não foram tomadas

Cada uma é um passo futuro, separado. Nenhuma está autorizada agora.

- Confirmar, depois de ler o `backup.sh`, se o dump que ele produz existe e está recente. O caminho do dump não está neste repositório.
- Publicar esta branch na imagem do projeto `super` (`docker compose -f docker-compose.prod.yml --env-file .env.prod -p super`, a partir de `/opt/super`). Isso troca o que está no ar. O `--env-file` é lido pelo Compose; não imprima o arquivo.
- Rodar a migration **dentro** do container novo, com o trabalho em `/app`: `docker compose -f docker-compose.prod.yml --env-file .env.prod -p super exec backend alembic upgrade head`. Ela só cria duas tabelas.
- Prévia, no mesmo `exec`, com `python -m app.reposicao_noturna --loja 2`. Não grava.
- Escolher o corte. Sem essa data não há apply. Data que ainda não começou não reabre o passado. Data já vivida repõe, num recibo só, todo dia encerrado desde o corte que ainda não tenha vínculo.
- Apply, noutro momento: o mesmo comando com `--corte AAAA-MM-DD` e `--aplicar`.
- Cron, só depois disso, numa linha nova. Não alterar o cron que já roda o simulador. 07:00 UTC é 04:00 em Brasília. O exemplo fica inativo:

```cron
# INATIVO. Não colar no crontab.
# 0 7 * * *  cd /opt/super; docker compose -f docker-compose.prod.yml --env-file .env.prod -p super exec -T backend python -m app.reposicao_noturna --loja 2 --corte AAAA-MM-DD --aplicar
```

## Como voltar atrás

Um downgrade desta revisão, se um dia for decidido, roda dentro do container (`alembic downgrade c3d5e7f9a0b1`). Ele só apaga as duas tabelas novas. **Não remove** lote nem linha de `entrada` que um `--aplicar` já tenha gravado. Não rode isso agora.

Não apague vínculo deixando o estoque, nem apague o lote deixando o vínculo. No primeiro caso a próxima madrugada reporia de novo. No segundo o saldo some e o histórico mente. Desfazer um recibo, se um dia for preciso, é um ajuste manual com motivo escrito, olhando `reposicao_noturna_origem`. Esta proposta não traz comando de desfazer.

## O que foi testado, e onde

Os testes usam um Postgres local chamado `reposicao_noturna_teste`. Eles recusam `AMBIENTE=prod` e não apontam para o banco `daki` nem `super`.

Na pasta `backend`:

```bash
python -m unittest discover -s tests -v
```
