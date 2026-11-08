# Equipe interna — papéis, sem escala e sem tarefa nova

Depende do branch `cursor/reposicao-noturna-7f9f`. Não substitui esse PR e não mexe no recibo noturno `AUTO`.

Isto não publica nada na VPS. O checkout que está em `/opt/super` é o da reposição. Não troque esse checkout por este branch neste passo. Não rode migration, não rode `--aplicar` e não mexa no cron.

## O que esta fatia faz

A meta interna é 18 pessoas, sem os entregadores:

| Papel | Meta | O que faz hoje |
| --- | --- | --- |
| gerente | 1 | painel, como hoje |
| líder | 2 | nada ainda; vê o quadro, não separa e não entrega |
| separador | 7 | separação, como hoje |
| embalador | 4 | nada ainda |
| repositor | 4 | nada ainda |

T1 é 1 líder, 4 separadores e 2 embaladores. T2 é 1 líder, 3 separadores e 2 embaladores. Os 4 repositores são o grupo da noite. Entregador só entrega e não entra nos 18.

A operação diurna combinada é 08:00–22:00. A janela prevista do repositor é 22:00–06:00. Entrada, intervalo e folga não estão definidos. Isso não é escala.

O simulador continua chamando só separador e entregador. Volume de pedido e ticket não mudam.

## O que não está pronto

Líder não distribui gente. Embalador não embala. Repositor não faz tarefa e não cria outra entrada de estoque. O recibo da madrugada continua sendo o `AUTO`.

Quem já está cadastrado não muda de papel, de PIN nem de histórico. O 9001 segue gerente. Os separadores 1001–1008 e os entregadores 2001–2009 ficam como estão. As vagas novas, se um dia forem gravadas, são `LABL`, `LABE` e `LABR`, com nome "simulado" e sem PIN conhecido.

## Conferir, um comando por vez

Nenhum comando abaixo roda na VPS agora.

Quando este branch estiver num ambiente seu, com `DATABASE_URL` já definida e sem imprimir essa URL, a leitura é:

```bash
python -m app.equipe
```

Ela não grava. Se a coluna `turno` ainda não existir, o comando recusa.

A migration, noutro momento e noutro comando, só adiciona `turno` vazio e a lista de papéis. Não insere pessoa:

```bash
alembic upgrade d5f7a9b1c3e4
```

Gravar as vagas novas é outra decisão. Não remaneja os separadores que já passam de 7:

```bash
python -m app.equipe --aplicar
```

Não há cron para isto.
