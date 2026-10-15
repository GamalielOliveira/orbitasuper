"""Simulador de operação do Super.

Roda DENTRO do container do backend e usa a API de verdade (http://localhost:8000),
com tokens gerados pelo próprio app (gera_token + JWT_SECRET). Nenhuma senha em texto.

Modos:
  python -m sim.simulador plano --data hoje [--por-dia 100]    # só calcula e mostra o plano (NÃO grava nada)
  python -m sim.simulador dia   --data 2026-10-15 [--forcar]   # dia "acelerado" (hoje: até agora-50min, depois termina tudo)
  python -m sim.simulador teste --pedidos 3                    # teste rápido: N pedidos na última 1h30
  python -m sim.simulador tick  [--janela 5]                   # tempo real (cron a cada N minutos, com flock)
  python -m sim.simulador resumo [--data 2026-10-15]

Como funciona o modo acelerado: um relógio virtual anda de minuto em minuto. Cada ação passa pela API
(estoque, reservas, pagamento, extrato: tudo igual à operação real) e logo depois o horário gravado
é trocado pelo horário virtual. Assim os painéis mostram o dia como se tivesse acontecido.

O dia é PLANEJADO antes (horários, clientes, ticket-alvo e destino de cada pedido) com sorteio fixo
por data: rodar de novo o 'plano' dá o mesmo resultado.

Regras:
- só clientes simulados (clientes.simulado) e funcionários com simulado=true; nunca 2001 nem 9001;
- não mexe em pedido de cliente real: se o primeiro da fila for real, o robô espera;
- sem pedido novo com a loja fechada; quem sai no fechamento termina tudo o que ficou aberto;
- cliente: no máximo 3 pedidos por dia, e cada pedido a mais no dia reduz a chance dele (x0,33);
- ticket: média do dia no ticket do cliente (~R$100), picos um pouco maiores, teto R$300 por pedido;
- expirados e recusados: quantidade exata (8% e 3% do plano), não "sorte".
"""
import argparse, hashlib, json, math, os, random, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.auth import gera_token
from app.db import engine

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8"))
TZ = ZoneInfo(CFG["fuso"])
API = os.getenv("SIM_API", "http://localhost:8000")
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
PROIBIDOS = set(CFG["regras"]["nao_simular"])
SIM_CLIENTE = "cliente_matricula IN (SELECT matricula FROM clientes WHERE simulado)"
P, T = CFG["pedidos"], CFG["tempos"]
DRENAR_H = 3   # horas depois do fechamento para terminar o que ficou aberto


# ---------------------------------------------------------------- utilidades
def h(*partes) -> float:
    """Sorteio fixo (0..1) a partir de um texto: o mesmo pedido sempre tem os mesmos tempos."""
    return int(hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:12], 16) / 16 ** 12

def hm(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%H:%M")

def minuto(t: datetime) -> datetime:
    return t.astimezone(TZ).replace(second=0, microsecond=0)

def horario_loja(d: date):
    de, ate = CFG["loja"][DIAS[d.weekday()]]
    return (datetime.combine(d, datetime.strptime(de, "%H:%M").time(), TZ),
            datetime.combine(d, datetime.strptime(ate, "%H:%M").time(), TZ))

def loja_aberta(t: datetime) -> bool:
    a, f = horario_loja(t.astimezone(TZ).date())
    return a <= t < f

def faixa(t: datetime):
    for nome, f in P["faixas"].items():
        if f["de"] <= hm(t) < f["ate"]: return nome, f
    return None, None

def disponivel(perfil: dict, t: datetime, ignorar: bool) -> bool:
    """Pode trabalhar agora? No turno e fora do almoço. Depois do fechamento, quem sai no fechamento
    continua (até DRENAR_H horas) para terminar o que ficou aberto."""
    if ignorar: return True
    tl = t.astimezone(TZ); dom = tl.weekday() == 6
    e = perfil.get("entrada_domingo" if dom else "entrada"); s = perfil.get("saida_domingo" if dom else "saida")
    if not e or not s: return False
    x = hm(tl)
    if e <= x < s:
        return not (perfil.get("almoco_inicio", "99") <= x < perfil.get("almoco_fim", "00"))
    # drenagem: confere o fechamento de hoje e o de ontem (depois da meia-noite)
    for dd in (tl.date(), tl.date() - timedelta(days=1)):
        _, fecha = horario_loja(dd)
        if s == hm(fecha) and fecha <= tl < fecha + timedelta(hours=DRENAR_H): return True
    return False


# ---------------------------------------------------------------- plano do dia
def minutos_abertos(d: date):
    a, f = horario_loja(d)
    out, t = [], a
    while t < f:
        out.append((t, faixa(t)[1]["peso"] if faixa(t)[1] else 1.0)); t += timedelta(minutes=1)
    return out

def fator_ticket_normalizado(d: date):
    """Multiplicador por faixa dividido pela média ponderada do dia: a média do dia fica = ticket do cliente."""
    ms = minutos_abertos(d)
    media = sum(w * (faixa(t)[1] or {"ticket": 1})["ticket"] for t, w in ms) / sum(w for _, w in ms)
    return {n: f["ticket"] / media for n, f in P["faixas"].items()}

def horarios_suaves(d: date, n: int, rnd) -> list[datetime]:
    """n horários espalhados pelo dia conforme o peso das faixas, sem buracos: quantis estratificados com
    um pouco de variação (cada pedido cai na sua 'fatia' do dia)."""
    ms = minutos_abertos(d)
    tot = sum(w for _, w in ms); acum, out, i, s = [], [], 0, 0.0
    for t, w in ms: s += w; acum.append(s)
    for k in range(n):
        alvo = (k + rnd.uniform(0.15, 0.85)) / n * tot
        while acum[i] < alvo: i += 1
        out.append(ms[i][0] + timedelta(seconds=int(rnd.random() * 59)))
    return sorted(minuto(x) for x in out)

def plano(d: date, clientes, n: int, ja_feitos: Counter | None = None):
    """Lista de pedidos do dia: horário, cliente, ticket-alvo e destino (paga / expira / recusa)."""
    rnd = random.Random(f"plano{d.isoformat()}")
    horas = horarios_suaves(d, n, rnd)
    fat = fator_ticket_normalizado(d)
    cont = Counter(ja_feitos or {})
    destinos = ["paga"] * n
    idx = list(range(n)); rnd.shuffle(idx)
    ne, nr = round(n * P["prob_expirar"]), round(n * P["prob_recusar"])
    for j in idx[:ne]: destinos[j] = "expira"
    for j in idx[ne:ne + nr]: destinos[j] = "recusa"
    sig = P["ticket_variacao"]
    out = []
    for k, t in enumerate(horas):
        fx = faixa(t)[0]
        cands = [c for c in clientes if cont[c.matricula] < P["max_por_cliente_dia"]] or clientes
        pesos = [float(c.perfil.get("pedidos_semana", 1)) * (1.6 if fx in c.perfil.get("faixas", []) else 0.8)
                 * P["fator_repeticao"] ** cont[c.matricula] for c in cands]
        cli = rnd.choices(cands, pesos)[0]; cont[cli.matricula] += 1
        alvo = float(cli.perfil.get("ticket_medio", 100)) * fat.get(fx, 1) * rnd.lognormvariate(-sig * sig / 2, sig)
        alvo = min(max(alvo, P["ticket_piso"]), P["ticket_teto"] * 0.9)
        out.append({"t": t, "cli": cli, "alvo": round(alvo, 2), "destino": destinos[k], "k": k})
    return out

def produtos_livres(c):
    return c.execute(text("""
        SELECT p.sku, p.categoria, p.preco::float AS preco, SUM(l.quantidade - l.reservado)::int AS livre
        FROM produtos p JOIN lotes l ON l.sku = p.sku
             AND (l.validade IS NULL OR l.validade >= (now() AT TIME ZONE 'America/Sao_Paulo')::date)
        WHERE p.preco > 0.5 AND position('_exp-' in p.sku) = 0 AND position('_sample' in p.sku) = 0 AND p.nome NOT LIKE '**%'
        GROUP BY p.sku HAVING SUM(l.quantidade - l.reservado) > 0""")).all()

def monta_itens(prods, cliente, alvo, rnd, livre=None):
    """Itens até chegar perto do alvo, sem estourar: item caro só se couber; 2-3 unidades só de item barato."""
    if not prods: return [], 0.0
    livre = livre if livre is not None else {p.sku: p.livre for p in prods}
    cats = cliente.perfil.get("categorias", [])
    favs = [p for p in prods if p.categoria in cats] or prods
    itens, total, tentativas = {}, 0.0, 0
    teto = min(P["ticket_teto"], alvo * 1.15 + 5)
    while total < alvo * 0.90 and len(itens) < P["max_itens"] and tentativas < 400:
        tentativas += 1
        p = rnd.choice(favs if rnd.random() < 0.8 else prods)
        resta = teto - total
        if p.preco > resta: continue
        q = 1 if p.preco >= 15 else rnd.choices([1, 2, 3], [65, 25, 10])[0]
        q = min(q, int(resta // p.preco), livre.get(p.sku, 0) - itens.get(p.sku, 0))
        if q <= 0: continue
        itens[p.sku] = itens.get(p.sku, 0) + q; total += q * p.preco
    return [{"sku": s, "quantidade": q} for s, q in itens.items()], round(total, 2)


class Sim:
    def __init__(self, virtual: bool, ignorar_turno=False, log=print):
        self.virtual, self.ignorar, self.log = virtual, ignorar_turno, log
        self.tokens, self.destino, self.criados = {}, {}, {}
        with engine.connect() as c:
            self.equipe = {r.matricula: r for r in c.execute(text(
                "SELECT matricula, nome, funcao, perfil FROM funcionarios WHERE simulado AND ativo AND funcao IN ('separador','entregador')")).all()
                if r.matricula not in PROIBIDOS}
            self.clientes = c.execute(text("SELECT * FROM clientes WHERE simulado AND ativo ORDER BY matricula")).all()
        self.cli = {c.matricula: c for c in self.clientes}

    # ------------------------------------------------------------ API
    def token(self, mat, nome, funcao):
        if mat not in self.tokens: self.tokens[mat] = gera_token(mat, nome, funcao)
        return self.tokens[mat]

    def api(self, metodo, caminho, tok, corpo=None):
        req = urllib.request.Request(API + caminho, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def tf(self, mat):
        f = self.equipe[mat]; return self.token(mat, f.nome, f.funcao)

    # ------------------------------------------------------------ horários (modo virtual)
    def retime(self, c, numero, **cols):
        """Troca os horários gravados pela API pelo horário virtual (só no modo acelerado)."""
        if not self.virtual or not cols: return
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        c.execute(text(f"UPDATE pedidos SET {sets} WHERE numero = :n"), {"n": numero, **cols})

    def retime_extras(self, c, pid, desde_mov, desde_oc, t):
        if not self.virtual: return
        c.execute(text("UPDATE movimentacoes_estoque SET criado_em=:t WHERE pedido_id=:p AND id>:d"), {"t": t, "p": pid, "d": desde_mov})
        c.execute(text("UPDATE ocorrencias_entrega SET criado_em=:t WHERE pedido_id=:p AND id>:d"), {"t": t, "p": pid, "d": desde_oc})

    def marcos(self, c):
        return (c.execute(text("SELECT COALESCE(MAX(id),0) FROM movimentacoes_estoque")).scalar(),
                c.execute(text("SELECT COALESCE(MAX(id),0) FROM ocorrencias_entrega")).scalar())

    def feitos_no_dia(self, d: date) -> Counter:
        with engine.connect() as c:
            return Counter({r[0]: r[1] for r in c.execute(text(f"""SELECT cliente_matricula, COUNT(*) FROM pedidos WHERE {SIM_CLIENTE}
                            AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date = :d GROUP BY 1"""), {"d": d})})

    # ------------------------------------------------------------ 1) novos pedidos
    def criar(self, item):
        t, cli = item["t"], item["cli"]
        rnd = random.Random(f"itens{t.isoformat()}#{item['k']}")
        with engine.connect() as c:
            itens, _ = monta_itens(produtos_livres(c), cli, item["alvo"], rnd)
        if not itens: self.log("sem estoque para montar pedido"); return
        end = {"cep": cli.cep or "31000-000", "rua": cli.rua, "numero_end": cli.numero_end, "bairro": cli.bairro,
               "cidade": cli.cidade, "uf": cli.uf, "lat": cli.lat, "lon": cli.lon}
        tok = self.token(cli.matricula, cli.nome, "cliente")
        st, r = self.api("POST", "/pedidos", tok, {"cliente": "", "itens": itens, "endereco": end})
        if st == 409:   # alguém pegou o último item no meio do caminho: tenta de novo com estoque fresco
            with engine.connect() as c:
                itens, _ = monta_itens(produtos_livres(c), cli, item["alvo"], rnd)
            st, r = self.api("POST", "/pedidos", tok, {"cliente": "", "itens": itens, "endereco": end})
        if st != 201: self.log(f"{hm(t)} pedido NÃO criado ({st}): {r}"); return
        n = r["numero"]; self.destino[n] = item["destino"]; self.criados[n] = t
        with engine.begin() as c:
            pid = c.execute(text("SELECT id FROM pedidos WHERE numero=:n"), {"n": n}).scalar()
            # quem vai expirar já fica com o horário virtual (o app expira sozinho depois de 15 min);
            # quem vai pagar só recebe o horário virtual depois de pago (senão o app expiraria antes)
            if item["destino"] == "expira": self.retime(c, n, criado_em=t)
            self.retime_extras(c, pid, 0, 0, t)
        self.log(f"{hm(t)} novo {n} {cli.nome} ({len(itens)} itens, R$ {r['total']}, {item['destino']})")
        self.criados_ok += 1

    # ------------------------------------------------------------ 2) pagamento
    def destino_de(self, n):
        # pedido de outra execução ainda sem pagamento: quem ia pagar já pagou no fim da execução dele
        # (pagamentos(..., ate_o_fim=True)), então o que sobrou é destino "expira": deixa o app expirar
        return self.destino.get(n, "expira")

    def pagamentos(self, t, ate_o_fim=False):
        with engine.connect() as c:
            pend = c.execute(text(f"""SELECT p.numero, p.cliente_matricula, p.criado_em FROM pedidos p
                                      WHERE p.status='aguardando_pagamento' AND {SIM_CLIENTE}
                                        AND NOT EXISTS (SELECT 1 FROM pagamentos g WHERE g.pedido_id = p.id)""")).all()
        for p in pend:
            dest = self.destino_de(p.numero)
            if dest == "expira": continue
            base = self.criados.get(p.numero, p.criado_em)
            a, b = P["pagar_em_seg"]
            if not ate_o_fim and t < base + timedelta(seconds=a + (b - a) * h(p.numero, "paga")): continue
            cli = self.cli[p.cliente_matricula]
            recusa = dest == "recusa"
            metodo = "cartao" if recusa or h(p.numero, "metodo") < 0.5 else "pix"
            st, r = self.api("POST", f"/pedidos/{p.numero}/pagamento", self.token(cli.matricula, cli.nome, "cliente"),
                             {"metodo": metodo, "cartao_final": "0000" if recusa else ("4242" if metodo == "cartao" else None)})
            if st != 201: self.log(f"pagamento falhou {p.numero}: {r}"); continue
            s = "aguardando_pagamento"
            for _ in range(40):   # o "gateway" responde em ~5 s pelo webhook
                with engine.connect() as c:
                    s = c.execute(text("SELECT status FROM pedidos WHERE numero=:n"), {"n": p.numero}).scalar()
                if s != "aguardando_pagamento": break
                time.sleep(0.5)
            with engine.begin() as c:
                self.retime(c, p.numero, criado_em=base)
                if self.virtual:
                    c.execute(text("UPDATE pagamentos SET criado_em=:t, atualizado_em=:t WHERE pedido_id=(SELECT id FROM pedidos WHERE numero=:n)"), {"t": t, "n": p.numero})
                    c.execute(text("""UPDATE eventos_pagamento SET recebido_em=:t WHERE pagamento_id IN
                                      (SELECT g.id FROM pagamentos g JOIN pedidos x ON x.id=g.pedido_id WHERE x.numero=:n)"""), {"t": t, "n": p.numero})
            self.log(f"{hm(t)} pagamento {p.numero} -> {s}")

    # ------------------------------------------------------------ 3) separação
    def livres(self, c, funcao, t):
        ocupados_sql = ("SELECT separador FROM pedidos WHERE status='em_separacao' AND separador IS NOT NULL" if funcao == "separador"
                        else "SELECT entregador FROM pedidos WHERE status IN ('atribuido','a_caminho','chegou') AND entregador IS NOT NULL")
        ocupados = {r[0] for r in c.execute(text(ocupados_sql))}
        cands = [f for f in self.equipe.values() if f.funcao == funcao and f.matricula not in ocupados and disponivel(f.perfil or {}, t, self.ignorar)]
        return sorted(cands, key=lambda f: h(f.matricula, t.isoformat()))   # revezamento

    def separacao(self, t):
        while True:   # pegar: só se o primeiro da fila for de cliente simulado
            with engine.connect() as c:
                topo = c.execute(text("SELECT numero, cliente_matricula FROM pedidos WHERE status='pago' ORDER BY criado_em LIMIT 1")).first()
                livres = self.livres(c, "separador", t)
            if not topo or not livres or topo.cliente_matricula not in self.cli: break
            st, r = self.api("POST", "/separacao/pegar", self.tf(livres[0].matricula))
            if st != 200: break
            with engine.begin() as c: self.retime(c, r["numero"], separacao_inicio=t)
            self.log(f"{hm(t)} {livres[0].nome} pegou {r['numero']}")
        with engine.connect() as c:
            em = c.execute(text(f"""SELECT p.id, p.numero, p.separador, p.separacao_inicio, COUNT(i.id) AS n FROM pedidos p
                                    JOIN itens_pedido i ON i.pedido_id=p.id WHERE p.status='em_separacao' AND {SIM_CLIENTE}
                                    GROUP BY p.id""")).all()
        for p in em:
            f = self.equipe.get(p.separador)
            if not f: continue
            pf = f.perfil or {}
            dur = (T["separacao_base_seg"] + T["separacao_por_item_seg"] * p.n) / float(pf.get("velocidade", 1))
            if h(p.numero, "atraso_sep") < float(pf.get("atraso", 0.05)): dur *= T["fator_atraso_separacao"]
            if t < p.separacao_inicio + timedelta(seconds=dur): continue
            tok = self.tf(f.matricula)
            with engine.connect() as c:
                itens = c.execute(text("SELECT id, sku FROM itens_pedido WHERE pedido_id=:p AND status='pendente'"), {"p": p.id}).all()
                m0, o0 = self.marcos(c)
            corpo = []
            for it in itens:
                e = {"id": it.id, "status": "separado", "substituto_sku": None}
                if h(p.numero, it.id, "erro") < float(pf.get("erro", 0.03)):
                    e["status"] = "faltando"
                    if h(p.numero, it.id, "sub") < 0.5:
                        st, subs = self.api("GET", f"/separacao/substitutos/{urllib.parse.quote(it.sku)}", tok)
                        if st == 200 and subs: e.update(status="substituido", substituto_sku=subs[0]["sku"])
                corpo.append(e)
            st, r = self.api("POST", f"/separacao/{p.numero}/concluir", tok, corpo)
            if st != 200: self.log(f"concluir falhou {p.numero}: {r}"); continue
            with engine.begin() as c:
                self.retime(c, p.numero, separacao_fim=t); self.retime_extras(c, p.id, m0, o0, t)
            self.log(f"{hm(t)} {f.nome} concluiu {p.numero} (faltas {r.get('faltas', 0)})")

    # ------------------------------------------------------------ 4) entrega
    def entrega(self, t):
        while True:
            with engine.connect() as c:
                topo = c.execute(text("SELECT numero, cliente_matricula FROM pedidos WHERE status='pronto' ORDER BY separacao_fim LIMIT 1")).first()
                livres = self.livres(c, "entregador", t)
            if not topo or not livres or topo.cliente_matricula not in self.cli: break
            f = livres[0]; tok = self.tf(f.matricula)
            st, r = self.api("POST", "/entrega/pegar", tok)
            if st != 200: break
            self.api("POST", f"/entrega/{r['numero']}/retirei", tok)
            with engine.begin() as c: self.retime(c, r["numero"], saiu_em=t)
            self.log(f"{hm(t)} {f.nome} saiu com {r['numero']}")
        with engine.connect() as c:
            rua = c.execute(text(f"""SELECT id, numero, status, entregador, cliente_matricula, saiu_em, chegou_em FROM pedidos
                                     WHERE status IN ('a_caminho','chegou') AND {SIM_CLIENTE}""")).all()
        for p in rua:
            f = self.equipe.get(p.entregador)
            if not f: continue
            pf, tok = f.perfil or {}, self.tf(f.matricula)
            with engine.connect() as c: m0, o0 = self.marcos(c)
            if p.status == "a_caminho":
                km = float(self.cli[p.cliente_matricula].dist_loja_km or 2) if p.cliente_matricula in self.cli else 2
                dur = max(120, km / T["velocidade_moto_kmh"] * 3600 / float(pf.get("velocidade", 1)))
                atraso = h(p.numero, "atraso_rota") < float(pf.get("atraso", 0.05))
                if atraso: dur *= T["fator_atraso_rota"]
                if t < p.saiu_em + timedelta(seconds=dur): continue
                if atraso: self.api("POST", f"/entrega/{p.numero}/ocorrencia", tok, {"tipo": "transito", "texto": "Trânsito lento"})
                self.api("POST", f"/entrega/{p.numero}/cheguei", tok)
                with engine.begin() as c:
                    self.retime(c, p.numero, chegou_em=t); self.retime_extras(c, p.id, m0, o0, t)
            else:
                a, b = T["porta_seg"]; dur = a + (b - a) * h(p.numero, "porta")
                demora = h(p.numero, "cliente") < T["prob_cliente_demora"]
                if demora: dur *= T["fator_cliente_demora"]
                if t < p.chegou_em + timedelta(seconds=dur): continue
                if demora: self.api("POST", f"/entrega/{p.numero}/ocorrencia", tok, {"tipo": "cliente", "texto": "Cliente demorou a atender"})
                self.api("POST", f"/entrega/{p.numero}/entreguei", tok)
                with engine.begin() as c:
                    self.retime(c, p.numero, entregue_em=t); self.retime_extras(c, p.id, m0, o0, t)
                self.log(f"{hm(t)} {f.nome} entregou {p.numero}")

    # ------------------------------------------------------------ laço
    def passo(self, t):
        self.pagamentos(t); self.separacao(t); self.entrega(t)

    def em_andamento(self):
        with engine.connect() as c:
            return c.execute(text(f"""SELECT COUNT(*) FROM pedidos WHERE {SIM_CLIENTE} AND status IN
                                      ('aguardando_pagamento','pago','em_separacao','pronto','atribuido','a_caminho','chegou')""")).scalar()

    def rodar_virtual(self, itens, inicio, limite):
        """Relógio virtual de minuto em minuto, de 'inicio' até 'limite' (ou até não sobrar nada aberto)."""
        self.criados_ok = 0
        t = minuto(inicio)   # alinhado no minuto (o teste antigo perdia o pedido do 1º minuto por causa dos segundos)
        fila = sorted(itens, key=lambda x: x["t"])
        ultimo = fila[-1]["t"] if fila else t
        while t <= limite:
            while fila and fila[0]["t"] <= t: self.criar(fila.pop(0))
            self.passo(t)
            # depois do último pedido, para quando não sobrar nada aberto (expirados somem sozinhos em até 15 min)
            if t > ultimo + timedelta(minutes=16) and not fila and self.em_andamento() == 0: break
            t += timedelta(minutes=1)
        self.log(f"criados {self.criados_ok} de {len(itens)} planejados; abertos no fim: {self.em_andamento()}")

    def cursor(self, d: date) -> datetime:
        """Último pedido simulado já criado hoje (pelo 'dia' ou por um tick anterior): o tick continua dali."""
        with engine.connect() as c:
            m = c.execute(text(f"""SELECT MAX(criado_em) FROM pedidos WHERE {SIM_CLIENTE}
                                   AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date = :d"""), {"d": d}).scalar()
        return minuto(m) if m else horario_loja(d)[0] - timedelta(minutes=1)

    def tick(self, janela_min):
        """Tempo real: roda ~janela-1 min, criando os pedidos do plano do dia na hora certa e andando a fila a cada minuto.
        Continua de onde o 'dia' ou o tick anterior parou (sem duplicar); horários já passados são criados na hora (recuperação)."""
        ini = datetime.now(TZ); d = ini.date()
        fim = ini + timedelta(minutes=max(1, janela_min - 1), seconds=-20)
        cur = self.cursor(d)
        fila = sorted((x for x in plano(d, self.clientes, P["por_dia"], self.feitos_no_dia(d)) if cur < x["t"] <= fim), key=lambda x: x["t"])
        atras = sum(1 for x in fila if x["t"] < minuto(ini))
        self.log(f"== tick {ini:%d/%m %H:%M:%S} · continua depois de {hm(cur)} · {len(fila)} pedidos na janela"
                 + (f" ({atras} atrasados, criados agora)" if atras else ""))
        self.criados_ok = 0
        while True:
            agora = datetime.now(TZ)
            while fila and fila[0]["t"] <= agora: self.criar(fila.pop(0))
            self.passo(agora)
            if agora >= fim: break
            time.sleep(max(1.0, min(60 - datetime.now(TZ).second, (fim - datetime.now(TZ)).total_seconds())))
        self.pagamentos(datetime.now(TZ), ate_o_fim=True)   # ninguém "que ia pagar" fica pendente para o próximo tick
        self.log(f"criados {self.criados_ok} · abertos: {self.em_andamento()}")


# ---------------------------------------------------------------- relatórios
def mostra_plano(itens, prods, titulo):
    print(f"\n== {titulo}: {len(itens)} pedidos")
    if not itens: return
    livre = {p.sku: p.livre for p in prods}
    tot, por_hora, ped_cli, unidades = [], Counter(), Counter(), 0
    for x in itens:
        its, v = monta_itens(prods, x["cli"], x["alvo"], random.Random(f"itens{x['t'].isoformat()}#{x['k']}"), livre)
        for i in its: livre[i["sku"]] -= i["quantidade"]; unidades += i["quantidade"]
        tot.append(v); por_hora[x["t"].hour] += 1; ped_cli[x["cli"].matricula] += 1
    pagos = [v for v, x in zip(tot, itens) if x["destino"] == "paga"]
    print(f"ticket médio (pagos): R$ {sum(pagos)/max(len(pagos),1):.2f} · mín R$ {min(tot):.2f} · máx R$ {max(tot):.2f}")
    print(f"destinos: {dict(Counter(x['destino'] for x in itens))}")
    print(f"clientes diferentes: {len(ped_cli)} · máx pedidos de um cliente: {max(ped_cli.values())} · distribuição: {dict(sorted(Counter(ped_cli.values()).items()))}")
    print(f"unidades que sairiam do estoque: {unidades} · SKUs que zerariam: {sum(1 for p in prods if livre[p.sku] <= 0)}")
    print("por hora: " + "  ".join(f"{hh:02d}h:{por_hora[hh]}" for hh in range(6, 23) if por_hora[hh] or 7 <= hh <= 21))

def resumo(d: date | None):
    filtro = SIM_CLIENTE + (" AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date = :d" if d else "")
    with engine.connect() as c:
        print("\nPedidos simulados por status:")
        for r in c.execute(text(f"SELECT status, COUNT(*) FROM pedidos WHERE {filtro} GROUP BY 1 ORDER BY 2 DESC"), {"d": d}):
            print(f"  {r[0]:<22}{r[1]:>5}")
        r = c.execute(text(f"SELECT COUNT(*), ROUND(AVG(total)::numeric,2) FROM pedidos WHERE {filtro} AND status='entregue'"), {"d": d}).first()
        print(f"Entregues: {r[0]} · ticket médio R$ {r[1]}")


def main():
    ap = argparse.ArgumentParser(description="Simulador do Super")
    ap.add_argument("modo", choices=["plano", "dia", "teste", "tick", "resumo"])
    ap.add_argument("--data", default="hoje", help="AAAA-MM-DD ou 'hoje'")
    ap.add_argument("--pedidos", type=int, default=3, help="modo teste")
    ap.add_argument("--por-dia", type=int, default=None, help="sobrepõe pedidos.por_dia da config")
    ap.add_argument("--janela", type=int, default=5, help="minutos (modo tick)")
    ap.add_argument("--forcar", action="store_true", help="simula mesmo se o dia já tem pedidos simulados")
    a = ap.parse_args()
    agora = datetime.now(TZ); hoje = agora.date()
    d = hoje if a.data == "hoje" else date.fromisoformat(a.data)
    n = a.por_dia or P["por_dia"]

    if a.modo == "resumo": return resumo(d)
    if a.modo in ("tick", "dia", "teste"):   # uma simulação por vez (tick do cron x dia manual)
        global TRAVA
        TRAVA = engine.connect()
        if not TRAVA.execute(text("SELECT pg_try_advisory_lock(715151)")).scalar():
            print("outra simulação está rodando; saindo."); return
    if a.modo == "tick": Sim(virtual=False).tick(a.janela); return
    if a.modo == "teste":
        s = Sim(virtual=True, ignorar_turno=True)
        ini = minuto(agora - timedelta(minutes=90))
        itens = [{"t": ini + timedelta(minutes=2 * k), "cli": random.Random(f"t{k}{ini}").choice(s.clientes), "alvo": 100.0,
                  "destino": "paga", "k": k} for k in range(a.pedidos)]
        s.rodar_virtual(itens, ini, agora); return resumo(hoje)

    if d > hoje: sys.exit("Data no futuro.")
    s = Sim(virtual=(a.modo == "dia"))
    feitos = s.feitos_no_dia(d)
    itens = plano(d, s.clientes, n, feitos)
    abre, fecha = horario_loja(d)
    # hoje: só pedidos até agora - folga, para tudo terminar antes de "agora" (o resto do dia fica para o tick)
    corte = min(fecha, agora - timedelta(minutes=P["folga_fim_hoje_min"])) if d == hoje else fecha
    itens = [x for x in itens if x["t"] < corte]
    if a.modo == "plano":
        with engine.connect() as c: prods = produtos_livres(c)
        mostra_plano(itens, prods, f"PLANO {d} (nada gravado){' até ' + hm(corte) if d == hoje else ''}")
        return
    if sum(feitos.values()) and not a.forcar: sys.exit(f"{d} já tem {sum(feitos.values())} pedidos simulados (use --forcar para somar mais).")
    limite = min(fecha + timedelta(hours=DRENAR_H), agora)
    s.rodar_virtual(itens, abre, limite)
    resumo(d)


if __name__ == "__main__":
    main()
