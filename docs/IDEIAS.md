# Ideias e pendências — ORBITA

Lista viva do que ainda falta ou pode melhorar. Marque `[x]` quando fizer.

## Automações (n8n)
- [ ] Alerta de pedido atrasado (passou da meta de 20 min ou travado em uma etapa)
- [ ] Lembrete de pagamento antes de expirar (taxa de expiração hoje: 34,8%)
- [ ] Promoção automática de itens vencendo (≤ 3 dias)
- [ ] Alerta de estoque baixo / zerado
- [ ] Resumo diário do gerente (vendas, atrasos, perdas, estoque)

## Operação
- [ ] Timer de separação reseta ao recarregar a página
- [ ] Trocar produtos com emoji em "Próximos a vencer" por foto/nome real
- [ ] Traccar Client enviando posição a cada 10 s
- [ ] Configurar GPS de Diego e Fernanda
- [ ] `JWT_SECRET` forte antes do deploy
- [ ] eslint: setState dentro de useEffect (Separadores, Estoque)

## Análise (cartões futuros)
- [ ] Domingo é o pior dia
- [ ] Carlos +42% no tempo de rota
- [ ] Açougue = 52% do faturamento
- [ ] Perdas no painel (por período)
- [ ] Mapa de calor de atrasos por bairro

## Estoque
- [ ] Curva ABC
- [ ] Sugestão de compra pelo giro
- [ ] FEFO na separação (vence primeiro, sai primeiro)
- [ ] Inventário cíclico
- [ ] Perdas por motivo

## Infra / DevOps
- [ ] Deploy em VPS com domínio fixo (substitui o túnel)
- [ ] Backup do Postgres
- [ ] Monitoramento
- [ ] CI (testes e build a cada push)

## Aprendizado
- [ ] Mini backend do zero
- [ ] Trilha gerente + DevOps: infra, rotas, banco, usuários, estoque

## Feito
- [x] Entrada de mercadoria com data de entrada (padrão hoje); validade não pode ser antes da entrada e avisa quando é hoje (e4)
- [x] Editar validade de um lote (só gerente), registrada no extrato como ajuste de 0 un. (e4)

## Deploy (super.orbitacode.cloud)
Domínio definitivo: **super.orbitacode.cloud**. Antes de subir:
- [ ] `JWT_SECRET` forte
- [ ] Limpar produtos de teste com "**Prox Venc**" no nome
- [ ] Traccar Client enviando posição a cada 10 s
- [ ] Deploy na VPS

## Adiado
- Automações n8n e o mini backend do zero ficam para depois de alguns dias de uso real.

## Login na loja (b2)
- [x] Loja do cliente (/) só abre com login; aceita gerente e (no futuro) perfil `cliente`
- [ ] Trocar a senha do 9001 (hoje 1234) por uma forte antes do deploy em super.orbitacode.cloud
- [ ] Criar logins `cliente` de verdade (cadastro) quando abrir para outras pessoas
- [ ] Proteger `GET /entrega/{numero}/posicao` (ainda aberto: mostra onde está o entregador)
