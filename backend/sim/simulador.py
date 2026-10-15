"""Simulador de operação do Super.

Roda DENTRO do container do backend e usa a API de verdade (http://localhost:8000),
com tokens gerados pelo próprio app (gera_token + JWT_SECRET). Nenhuma senha em texto.

Modos:
  python -m sim.simulador dia   --data 2026-10-15 [--forcar]   # dia inteiro "acelerado" (para hoje: até agora)
  python -m sim.simulador teste --pedidos 3                    # teste rápido: N pedidos na última 1h30
  python -m sim.simulador tick  [--janela 5]                   # tempo real (cron a cada N minutos)
  python -m sim.simulador resumo [--data 2026-10-15]

Como o modo acelerado funciona: um relógio virtual anda de minuto em minuto. Cada ação passa pela API
(estoque, reservas, pagamento, extrato: tudo igual à operação real) e logo depois o horário gravado
é trocado pelo horário virtual. Assim os painéis mostram o dia como se tivesse acontecido.

Só age com clientes simulados (clientes.simulado) e funcionários com simulado=true.
Nunca usa o Carlos (2001) nem o 9001. Não mexe em pedido de cliente real: se o primeiro da fila
for real, o robô espera.
"""
import argparse, hashlib, json, math, os, random, sys, time, urllib.error, urllib.parse, urllib.request
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


# ---------------------------------------------------------------- utilidades
def h(*partes) -> float:
    """Sorteio fixo (0..1) a partir de um texto: o mesmo pedido sempre tem o mesmo destino/tempos."""
    return int(hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:12], 16) / 16 ** 12

def hm(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%H:%M")

def loja_aberta(t: datetime) -> bool:
    de, ate = CFG["loja"][DIAS[t.astimezone(TZ).weekday()]]
    return de <= hm(t) < ate

def faixa(t: datetime):
    for nome, f in P["faixas"].items():
        if f["de"] <= hm(t) < f["ate"]: return nome, f
    return None, None

def no_turno(perfil: dict, t: datetime, ignorar: bool) -> bool:
    """No horário do turno e fora do almoço."""
    if ignorar: return True
    dom = t.astimezone(TZ).weekday() == 6
    e = perfil.get("entrada_domingo" if dom else "entrada"); s = perfil.get("saida_domingo" if dom else "saida")
    if not e or not s: return False
    x = hm(t)
    return e <= x < s and not (perfil.get("almoco_inicio", "99") <= x < perfil.get("almoco_fim", "00"))


class Sim:
    def __init__(self, virtual: bool, ignorar_turno=False, log=print):
        self.virtual, self.ignorar, self.log = virtual, ignorar_turno, log
        self.tokens = {}
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
    def retime(self, c, numero, t, **cols):
        """Troca os horários gravados pela API pelo horário virtual t (só no modo acelerado)."""
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

    # ------------------------------------------------------------ 1) novos pedidos
    def chegadas(self, a: datetime, b: datetime, forcar: int | None = None) -> list[datetime]:
        """Horários de pedidos na janela [a, b). Mais pedidos nas faixas de pico."""
        mins, t = [], a.replace(second=0, microsecond=0)
        while t < b:
            if forcar is not None or loja_aberta(t): mins.append(t)
            t += timedelta(minutes=1)
        if forcar is not None:
            rnd = random.Random(f"teste{a.isoformat()}")
            return sorted(rnd.choice(mins[: max(1, len(mins) // 3)]) for _ in range(forcar))
        # peso total de um dia (minutos abertos x peso da faixa) para virar "pedidos por minuto"
        dia = a.astimezone(TZ).replace(hour=0, minute=0)
        total = sum((faixa(dia + timedelta(minutes=i))[1] or {"peso": 0})["peso"]
                    for i in range(24 * 60) if loja_aberta(dia + timedelta(minutes=i)))
        out = []
        for m in mins:
            lam = P["por_dia"] * (faixa(m)[1] or {"peso": 0})["peso"] / max(total, 1)
            rnd = random.Random(f"chegada{m.isoformat()}")
            # Poisson simples (λ é pequeno: quase sempre 0 ou 1 por minuto)
            k, p, L = 0, rnd.random(), math.exp(-lam)
            acc = L
            while p > acc and k < 5: k += 1; L *= lam / k; acc += L
            out += [m] * k
        return out

    def escolhe_cliente(self, t, rnd):
        fx = faixa(t)[0]
        pesos = [float(c.perfil.get("pedidos_semana", 1)) * (2.0 if fx in c.perfil.get("faixas", []) else 0.5) for c in self.clientes]
        return rnd.choices(self.clientes, pesos)[0]

    def monta_itens(self, c, cliente, t, rnd):
        alvo = float(cliente.perfil.get("ticket_medio", 100)) * (faixa(t)[1] or {"ticket": 1})["ticket"] * rnd.lognormvariate(0, 0.25)
        prods = c.execute(text("""
            SELECT p.sku, p.categoria, p.preco::float AS preco, SUM(l.quantidade - l.reservado) AS livre
            FROM produtos p JOIN lotes l ON l.sku = p.sku
                 AND (l.validade IS NULL OR l.validade >= (now() AT TIME ZONE 'America/Sao_Paulo')::date)
            WHERE p.preco > 0.5 AND position('_exp-' in p.sku) = 0 AND position('_sample' in p.sku) = 0 AND p.nome NOT LIKE '**%'
            GROUP BY p.sku HAVING SUM(l.quantidade - l.reservado) > 0""")).all()
        if not prods: return [], 0
        cats = cliente.perfil.get("categorias", [])
        favs = [p for p in prods if p.categoria in cats] or prods
        itens, total = {}, 0.0
        while total < alvo and len(itens) < P["max_itens"]:
            p = rnd.choice(favs if rnd.random() < 0.8 else prods)
            q = min(rnd.choices([1, 2, 3], [70, 20, 10])[0], int(p.livre) - itens.get(p.sku, 0))
            if q <= 0: continue
            itens[p.sku] = itens.get(p.sku, 0) + q; total += q * p.preco
        return [{"sku": s, "quantidade": q} for s, q in itens.items()], total

    def novos_pedidos(self, horarios):
        for i, t in enumerate(horarios):
            rnd = random.Random(f"pedido{t.isoformat()}#{i}{random.random() if not self.virtual else ''}")
            cli = self.escolhe_cliente(t, rnd)
            with engine.connect() as c:
                itens, _ = self.monta_itens(c, cli, t, rnd)
            if not itens: self.log("sem estoque para montar pedido"); continue
            end = {"cep": cli.cep or "31000-000", "rua": cli.rua, "numero_end": cli.numero_end, "bairro": cli.bairro,
                   "cidade": cli.cidade, "uf": cli.uf, "lat": cli.lat, "lon": cli.lon}
            st, r = self.api("POST", "/pedidos", self.token(cli.matricula, cli.nome, "cliente"), {"cliente": "", "itens": itens, "endereco": end})
            if st != 201: self.log(f"pedido recusado ({st}): {r}"); continue
            n = r["numero"]
            with engine.begin() as c:
                pid = c.execute(text("SELECT id FROM pedidos WHERE numero=:n"), {"n": n}).scalar()
                if h(n, "expira") < P["prob_expirar"]:
                    # nunca vai pagar: data de criação já no horário virtual (o app expira sozinho depois de 15 min)
                    self.retime(c, n, t, criado_em=t)
                    self.retime_extras(c, pid, 0, 0, t)
                else:
                    # guarda o horário virtual de criação na reserva; o pedido só recebe criado_em depois de pago
                    self.retime_extras(c, pid, 0, 0, t)
            self.criados[n] = t
            self.log(f"{hm(t)} novo {n} {cli.nome} ({len(itens)} itens, R$ {r['total']})")

    # ------------------------------------------------------------ 2) pagamento
    def pagamentos(self, t):
        with engine.connect() as c:
            pend = c.execute(text(f"""SELECT p.numero, p.cliente_matricula, p.criado_em FROM pedidos p
                                      WHERE p.status='aguardando_pagamento' AND {SIM_CLIENTE}
                                        AND NOT EXISTS (SELECT 1 FROM pagamentos g WHERE g.pedido_id = p.id)""")).all()
        for p in pend:
            if h(p.numero, "expira") < P["prob_expirar"]: continue
            base = self.criados.get(p.numero, p.criado_em)
            a, b = P["pagar_em_seg"]
            if t < base + timedelta(seconds=a + (b - a) * h(p.numero, "paga")): continue
            cli = self.cli[p.cliente_matricula]
            recusa = h(p.numero, "recusa") < P["prob_recusar"]
            metodo = "cartao" if recusa or h(p.numero, "metodo") < 0.5 else "pix"
            st, r = self.api("POST", f"/pedidos/{p.numero}/pagamento", self.token(cli.matricula, cli.nome, "cliente"),
                             {"metodo": metodo, "cartao_final": "0000" if recusa else ("4242" if metodo == "cartao" else None)})
            if st != 201: self.log(f"pagamento falhou {p.numero}: {r}"); continue
            # o "gateway" responde em ~5 s pelo webhook; espera para o resto andar na ordem certa
            for _ in range(40):
                with engine.connect() as c:
                    s = c.execute(text("SELECT status FROM pedidos WHERE numero=:n"), {"n": p.numero}).scalar()
                if s != "aguardando_pagamento": break
                time.sleep(0.5)
            with engine.begin() as c:
                self.retime(c, p.numero, t, criado_em=base)
                if self.virtual:
                    c.execute(text("""UPDATE pagamentos SET criado_em=:t, atualizado_em=:t WHERE pedido_id=(SELECT id FROM pedidos WHERE numero=:n)"""), {"t": t, "n": p.numero})
                    c.execute(text("""UPDATE eventos_pagamento SET recebido_em=:t WHERE pagamento_id IN
                                      (SELECT g.id FROM pagamentos g JOIN pedidos x ON x.id=g.pedido_id WHERE x.numero=:n)"""), {"t": t, "n": p.numero})
            self.log(f"{hm(t)} pago? {p.numero} -> {s}")

    # ------------------------------------------------------------ 3) separação
    def livres(self, c, funcao, t):
        ocupados_sql = ("SELECT separador FROM pedidos WHERE status='em_separacao' AND separador IS NOT NULL" if funcao == "separador"
                        else "SELECT entregador FROM pedidos WHERE status IN ('atribuido','a_caminho','chegou') AND entregador IS NOT NULL")
        ocupados = {r[0] for r in c.execute(text(ocupados_sql))}
        cands = [f for f in self.equipe.values() if f.funcao == funcao and f.matricula not in ocupados and no_turno(f.perfil or {}, t, self.ignorar)]
        return sorted(cands, key=lambda f: h(f.matricula, t.isoformat()))   # revezamento

    def separacao(self, t):
        # pegar: só se o primeiro da fila for de cliente simulado
        while True:
            with engine.connect() as c:
                topo = c.execute(text("SELECT numero, cliente_matricula FROM pedidos WHERE status='pago' ORDER BY criado_em LIMIT 1")).first()
                livres = self.livres(c, "separador", t)
            if not topo or not livres or topo.cliente_matricula not in self.cli: break
            st, r = self.api("POST", "/separacao/pegar", self.tf(livres[0].matricula))
            if st != 200: break
            with engine.begin() as c:
                self.retime(c, r["numero"], t, separacao_inicio=t)
            self.log(f"{hm(t)} {livres[0].nome} pegou {r['numero']}")
        # concluir quando o tempo de separação passou
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
                self.retime(c, p.numero, t, separacao_fim=t)
                self.retime_extras(c, p.id, m0, o0, t)
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
            st, _ = self.api("POST", f"/entrega/{r['numero']}/retirei", tok)
            with engine.begin() as c:
                self.retime(c, r["numero"], t, saiu_em=t)
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
                st, _ = self.api("POST", f"/entrega/{p.numero}/cheguei", tok)
                with engine.begin() as c:
                    self.retime(c, p.numero, t, chegou_em=t); self.retime_extras(c, p.id, m0, o0, t)
            else:
                a, b = T["porta_seg"]; dur = a + (b - a) * h(p.numero, "porta")
                demora = h(p.numero, "cliente") < T["prob_cliente_demora"]
                if demora: dur *= T["fator_cliente_demora"]
                if t < p.chegou_em + timedelta(seconds=dur): continue
                if demora: self.api("POST", f"/entrega/{p.numero}/ocorrencia", tok, {"tipo": "cliente", "texto": "Cliente demorou a atender"})
                st, _ = self.api("POST", f"/entrega/{p.numero}/entreguei", tok)
                with engine.begin() as c:
                    self.retime(c, p.numero, t, entregue_em=t); self.retime_extras(c, p.id, m0, o0, t)
                self.log(f"{hm(t)} {f.nome} entregou {p.numero}")

    # ------------------------------------------------------------ laço
    def passo(self, t):
        self.pagamentos(t); self.separacao(t); self.entrega(t)

    def em_andamento(self):
        with engine.connect() as c:
            return c.execute(text(f"""SELECT COUNT(*) FROM pedidos WHERE {SIM_CLIENTE} AND status IN
                                      ('pago','em_separacao','pronto','atribuido','a_caminho','chegou')""")).scalar()

    def rodar_virtual(self, inicio, fim, forcar=None, ate_esvaziar=True):
        """Relógio virtual de minuto em minuto. Pedidos chegam até 'fim'; depois só termina o que está em andamento."""
        self.criados = {}
        agora = datetime.now(TZ)
        t, limite = inicio, min(fim + timedelta(hours=3), agora)
        chegada_fim = min(fim, agora)
        pendentes = sorted(self.chegadas(inicio, chegada_fim, forcar))
        self.log(f"{len(pendentes)} pedido(s) planejado(s) entre {hm(inicio)} e {hm(chegada_fim)}")
        while t <= limite:
            prox = t + timedelta(minutes=1)
            agora_min = [x for x in pendentes if t <= x < prox]
            if agora_min: self.novos_pedidos(agora_min)
            self.passo(t)
            if t >= chegada_fim and (not ate_esvaziar or self.em_andamento() == 0): break
            t = prox

    def tick(self, janela_min):
        self.criados = {}
        agora = datetime.now(TZ)
        self.novos_pedidos(self.chegadas(agora - timedelta(minutes=janela_min), agora))
        self.passo(agora)


def ja_simulado(d: date) -> int:
    with engine.connect() as c:
        return c.execute(text(f"""SELECT COUNT(*) FROM pedidos WHERE {SIM_CLIENTE}
                                  AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date = :d"""), {"d": d}).scalar()


def resumo(d: date | None):
    filtro = f"{SIM_CLIENTE}" + (" AND (criado_em AT TIME ZONE 'America/Sao_Paulo')::date = :d" if d else "")
    with engine.connect() as c:
        print("\nPedidos simulados por status:")
        for r in c.execute(text(f"SELECT status, COUNT(*) FROM pedidos WHERE {filtro} GROUP BY 1 ORDER BY 2 DESC"), {"d": d}):
            print(f"  {r[0]:<22}{r[1]:>5}")
        r = c.execute(text(f"SELECT COUNT(*), ROUND(AVG(total)::numeric,2) FROM pedidos WHERE {filtro} AND status='entregue'"), {"d": d}).first()
        print(f"Entregues: {r[0]} · ticket médio R$ {r[1]}")


def main():
    ap = argparse.ArgumentParser(description="Simulador do Super")
    ap.add_argument("modo", choices=["dia", "teste", "tick", "resumo"])
    ap.add_argument("--data", help="AAAA-MM-DD ou 'hoje' (padrão hoje)", default="hoje")
    ap.add_argument("--pedidos", type=int, default=3)
    ap.add_argument("--janela", type=int, default=5, help="minutos (modo tick)")
    ap.add_argument("--forcar", action="store_true", help="simula mesmo se o dia já tem pedidos simulados")
    a = ap.parse_args()
    hoje = datetime.now(TZ).date()
    d = hoje if a.data == "hoje" else date.fromisoformat(a.data)

    if a.modo == "resumo": return resumo(d)
    if a.modo == "tick":
        Sim(virtual=False).tick(a.janela); return
    if a.modo == "teste":
        agora = datetime.now(TZ)
        Sim(virtual=True, ignorar_turno=True).rodar_virtual(agora - timedelta(minutes=90), agora - timedelta(minutes=60), forcar=a.pedidos)
        return resumo(hoje)
    # dia inteiro
    if d > hoje: sys.exit("Data no futuro.")
    if ja_simulado(d) and not a.forcar: sys.exit(f"{d} já tem pedidos simulados (use --forcar para somar mais).")
    de, ate = CFG["loja"][DIAS[d.weekday()]]
    ini = datetime.combine(d, datetime.strptime(de, "%H:%M").time(), TZ)
    fim = datetime.combine(d, datetime.strptime(ate, "%H:%M").time(), TZ)
    Sim(virtual=True).rodar_virtual(ini, fim)
    resumo(d)


if __name__ == "__main__":
    main()
