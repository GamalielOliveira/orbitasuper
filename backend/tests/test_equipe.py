"""Equipe interna: papéis, contagem e vagas novas. Banco local só.

Não aponta para produção. A URL é a mesma do teste da reposição noturna
para os dois arquivos dividirem um engine só.
"""
import os
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO

if os.environ.get("AMBIENTE") == "prod":
    raise SystemExit("recusado: teste não roda com AMBIENTE=prod")

HOST = "127.0.0.1"
DB = "reposicao_noturna_teste"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://daki:daki_dev@{HOST}:5432/{DB}"

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import text

from app.auth import exige, gera_token, hash_pin
from fastapi.security import HTTPAuthorizationCredentials
from app.db import engine
from app.equipe import ALVO, aplicar, main, previa
from app.main import LoginIn, app, fila, gerente_equipe, login, minha_entrega, pegar, pegar_entrega, quadro, concluir
from app.reposicao_noturna import executar

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ELENCO = [
    ("9001", "Gamaliel", "gerente", False),
    ("1001", "Ana", "separador", True),
    ("1002", "Bruno", "separador", True),
    ("1003", "Ana Paula Souza", "separador", True),
    ("1004", "Bruno Carvalho", "separador", True),
    ("1005", "Juliana Ribeiro", "separador", True),
    ("1006", "Marcos Vinícius Lima", "separador", True),
    ("1007", "Patrícia Gomes", "separador", True),
    ("1008", "Rafael Teixeira", "separador", True),
    ("2001", "Carlos", "entregador", False),
    ("2002", "Diego", "entregador", True),
    ("2003", "Fernanda", "entregador", True),
    ("2004", "Lucas Ferreira", "entregador", True),
    ("2005", "Rodrigo Nascimento", "entregador", True),
    ("2006", "Aline Cardoso", "entregador", True),
    ("2007", "Gustavo Pereira", "entregador", True),
    ("2008", "Vanessa Moreira", "entregador", True),
    ("2009", "Felipe Araújo", "entregador", True),
]


def _admin():
    import psycopg
    return psycopg.connect(f"postgresql://daki:daki_dev@{HOST}:5432/postgres", autocommit=True)


def _recriar():
    with _admin() as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (DB,))
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB)))
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER daki").format(sql.Identifier(DB)))


def _limpar():
    with engine.begin() as c:
        c.execute(text("""
            TRUNCATE reposicao_noturna_origem, reposicoes_noturnas, movimentacoes_estoque,
                     itens_pedido, pedidos, lotes, produtos, funcionarios, lojas RESTART IDENTITY CASCADE
        """))


def _pessoa(c, matricula, nome, funcao, simulado, turno=None, ativo=True):
    c.execute(text("""
        INSERT INTO funcionarios (matricula, nome, funcao, pin_hash, ativo, disponivel, simulado, turno)
        VALUES (:m, :n, :f, :p, :a, true, :s, :t)
    """), {"m": matricula, "n": nome, "f": funcao, "p": hash_pin(f"somente-teste-{matricula}"),
           "a": ativo, "s": simulado, "t": turno})


def _elenco(c, separadores=8):
    for mat, nome, funcao, simulado in ELENCO:
        if funcao == "separador" and int(mat) - 1000 > separadores:
            continue
        _pessoa(c, mat, nome, funcao, simulado)


def _foto():
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text("""
            SELECT matricula, nome, funcao, pin_hash, ativo, disponivel, device_id, simulado, perfil::text, turno
            FROM funcionarios ORDER BY matricula
        """)).all()]


def _contagens():
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in (
            "funcionarios", "pedidos", "movimentacoes_estoque", "reposicoes_noturnas", "reposicao_noturna_origem", "lotes")}


def setUpModule():
    os.chdir(BACKEND)
    _recriar()
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    command.upgrade(cfg, "head")
    with engine.begin() as c:
        _pessoa(c, "9001", "Gamaliel", "gerente", False)
    command.downgrade(cfg, "c3d5e7f9a0b1")
    with engine.connect() as c:
        coluna = c.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'funcionarios' AND column_name = 'turno'
        """)).first()
        nome = c.execute(text("SELECT nome FROM funcionarios WHERE matricula = '9001'")).scalar()
        if coluna or nome != "Gamaliel":
            raise AssertionError("a migration da equipe alterou gente ou não desceu")
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        nome = c.execute(text("SELECT nome, funcao FROM funcionarios WHERE matricula = '9001'")).one()
        if tuple(nome) != ("Gamaliel", "gerente"):
            raise AssertionError("subir a migration de novo mudou o 9001")
    _limpar()


def tearDownModule():
    engine.dispose()
    with _admin() as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (DB,))
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB)))


class EquipeTeste(unittest.TestCase):
    def setUp(self):
        _limpar()

    def test_previa_nao_grava_e_nao_conta_entregador(self):
        with engine.begin() as c:
            _elenco(c)
        antes_f, antes_c = _foto(), _contagens()
        r = previa()
        self.assertFalse(r["gravou"])
        self.assertEqual(r["modo"], "preview")
        self.assertEqual(antes_f, _foto())
        self.assertEqual(antes_c, _contagens())
        self.assertEqual(r["interno"]["atual"], 9)
        self.assertEqual(r["interno"]["alvo"], 18)
        self.assertEqual(r["externo_entregador"], {"atual": 9, "conta_no_interno": False})
        self.assertEqual(r["por_funcao"]["separador"]["atual"], 8)
        self.assertEqual(r["por_funcao"]["separador"]["excedente"], 1)
        self.assertEqual(r["por_funcao"]["lider"]["atividade"], "pendente")
        self.assertEqual(r["por_funcao"]["embalador"]["atividade"], "pendente")
        self.assertEqual(r["por_funcao"]["repositor"]["atividade"], "pendente")
        self.assertEqual(r["por_funcao"]["separador"]["atividade"], "separação de pedido, como hoje")
        self.assertFalse(r["escala_validada"])
        self.assertIn("AUTO", r["reposicao_noturna"])
        self.assertEqual(r["turnos"]["T1"]["separador"], {"alvo": 4, "alocados": 0})
        self.assertEqual(r["turnos"]["T2"]["separador"], {"alvo": 3, "alocados": 0})
        self.assertEqual(sorted(v["matricula"] for v in r["propostos"]),
                         ["LABE01", "LABE02", "LABE03", "LABE04", "LABL01", "LABL02", "LABR01", "LABR02", "LABR03", "LABR04"])
        self.assertTrue(any("1008" in d for d in r["decisoes_pendentes"]))
        buf = StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main([]), 0)
        texto = buf.getvalue()
        self.assertNotIn("pin_hash", texto)
        self.assertNotIn("$2", texto)
        self.assertEqual(antes_f, _foto())

    def test_aplicar_preserva_elenco_e_e_idempotente(self):
        with engine.begin() as c:
            _elenco(c)
        antes = {linha[0]: linha for linha in _foto()}
        primeiro = aplicar()
        self.assertTrue(primeiro["gravou"])
        self.assertEqual(len(primeiro["inseridos"]), 10)
        self.assertEqual(primeiro["interno"]["atual"], 19)
        self.assertFalse(primeiro["meta_interna_fechada"])
        self.assertEqual(primeiro["externo_entregador"]["atual"], 9)
        depois = {linha[0]: linha for linha in _foto()}
        for mat, linha in antes.items():
            self.assertEqual(depois[mat], linha)
        with engine.connect() as c:
            lab = c.execute(text("""
                SELECT matricula, funcao, turno, simulado, nome FROM funcionarios
                WHERE matricula LIKE 'LAB%' ORDER BY matricula
            """)).all()
        self.assertEqual([(r.matricula, r.funcao, r.turno) for r in lab], [
            ("LABE01", "embalador", "T1"), ("LABE02", "embalador", "T1"),
            ("LABE03", "embalador", "T2"), ("LABE04", "embalador", "T2"),
            ("LABL01", "lider", "T1"), ("LABL02", "lider", "T2"),
            ("LABR01", "repositor", "noite"), ("LABR02", "repositor", "noite"),
            ("LABR03", "repositor", "noite"), ("LABR04", "repositor", "noite"),
        ])
        self.assertTrue(all("simulado" in r.nome and r.simulado for r in lab))
        congelado = _foto()
        segundo = aplicar()
        self.assertFalse(segundo["gravou"])
        self.assertEqual(congelado, _foto())
        with self.assertRaises(HTTPException) as ctx:
            login(LoginIn(matricula="LABL01", pin="1234"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_nao_ultrapassa_meta_nem_altera_quem_ja_ocupa(self):
        with engine.begin() as c:
            _pessoa(c, "L-REAL", "Líder já existente", "lider", True, turno="T1")
            _pessoa(c, "L-REAL2", "Líder já existente 2", "lider", True, turno="T2")
        antes = _foto()
        r = aplicar()
        self.assertNotIn("LABL01", r.get("inseridos", []))
        self.assertNotIn("LABL02", r.get("inseridos", []))
        self.assertEqual(r["por_funcao"]["lider"]["atual"], 2)
        depois = {linha[0]: linha for linha in _foto()}
        for linha in antes:
            self.assertEqual(depois[linha[0]], linha)

    def test_meta_fecha_sem_remanejamento_quando_separador_ja_e_7(self):
        with engine.begin() as c:
            _elenco(c, separadores=7)
        r = aplicar()
        self.assertEqual(r["interno"]["atual"], 18)
        self.assertTrue(r["interno"]["fechada"])
        self.assertEqual(r["por_funcao"]["separador"]["atual"], 7)
        self.assertEqual(r["externo_entregador"]["atual"], 9)
        self.assertFalse(r["escala_validada"])
        self.assertEqual(r["por_funcao"]["repositor"]["atividade"], "pendente")
        self.assertTrue(any("sem turno" in d for d in r["decisoes_pendentes"]))

    def test_falha_nao_deixa_vaga_pela_metade(self):
        with engine.begin() as c:
            _elenco(c, separadores=7)
        antes = _foto()
        import app.equipe as equipe
        real = equipe._pin_inacessivel
        n = {"n": 0}

        def quebra():
            n["n"] += 1
            if n["n"] == 3:
                raise RuntimeError("falha injetada")
            return real()

        equipe._pin_inacessivel = quebra
        try:
            with self.assertRaises(RuntimeError):
                aplicar()
        finally:
            equipe._pin_inacessivel = real
        self.assertEqual(antes, _foto())

    def test_concorrencia_insere_uma_vez(self):
        with engine.begin() as c:
            _elenco(c, separadores=7)
        barreira = threading.Barrier(2)
        erros, saidas = [], []

        def rodar():
            barreira.wait(timeout=30)
            try:
                saidas.append(aplicar())
            except Exception as e:
                erros.append(e)

        fios = [threading.Thread(target=rodar), threading.Thread(target=rodar)]
        for fio in fios:
            fio.start()
        for fio in fios:
            fio.join(30)
        self.assertEqual(erros, [])
        self.assertEqual(sum(1 for s in saidas if s["gravou"]), 1)
        with engine.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM funcionarios WHERE matricula LIKE 'LAB%'")).scalar()
        self.assertEqual(n, 10)

    def test_auth_nao_escala_e_fluxo_antigo_segue(self):
        with engine.begin() as c:
            c.execute(text("INSERT INTO lojas (id, nome, cidade) VALUES (2, 'Loja 2', 'BH')"))
            c.execute(text("""INSERT INTO produtos (sku, nome, categoria, corredor, preco, perecivel)
                              VALUES ('SKU1', 'Item', 'Teste', 1, 10, false)"""))
            lote = c.execute(text("""INSERT INTO lotes (loja_id, sku, quantidade, reservado)
                                     VALUES (2, 'SKU1', 5, 0) RETURNING id""")).scalar()
            pid = c.execute(text("""INSERT INTO pedidos (numero, loja_id, cliente, status, total)
                                    VALUES ('MD-TESTE', 2, 'Cliente teste', 'pago', 10) RETURNING id""")).scalar()
            c.execute(text("""INSERT INTO itens_pedido (pedido_id, sku, quantidade, preco_unitario, lote_id)
                              VALUES (:p, 'SKU1', 1, 10, :l)"""), {"p": pid, "l": lote})
            _pessoa(c, "1001", "Ana", "separador", True)
            _pessoa(c, "2001", "Carlos", "entregador", False)
            _pessoa(c, "TLID", "Líder simulado teste", "lider", True, turno="T1")
        quem = {
            "separador": {"sub": "1001", "nome": "Ana", "funcao": "separador"},
            "entregador": {"sub": "2001", "nome": "Carlos", "funcao": "entregador"},
            "lider": {"sub": "TLID", "nome": "Líder simulado teste", "funcao": "lider"},
            "embalador": {"sub": "X", "nome": "Embalador simulado", "funcao": "embalador"},
            "repositor": {"sub": "Y", "nome": "Repositor simulado", "funcao": "repositor"},
            "admin": {"sub": "Z", "nome": "Admin", "funcao": "admin"},
            "cliente": {"sub": "C", "nome": "Cliente", "funcao": "cliente"},
            "gerente": {"sub": "9001", "nome": "Gamaliel", "funcao": "gerente"},
        }

        def codigo(fn):
            try:
                fn()
                return 200
            except HTTPException as e:
                return e.status_code

        def crachá(papel):
            dados = quem[papel]
            token = gera_token(dados["sub"], dados["nome"], dados["funcao"])
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        def porta(area, papel):
            return codigo(lambda: exige(area)(crachá(papel)))

        for papel in ("lider", "embalador", "repositor", "entregador", "admin", "cliente"):
            self.assertEqual(porta("separador", papel), 403, papel)
            self.assertEqual(porta("gerente", papel), 403, papel)
        for papel in ("lider", "embalador", "repositor", "separador", "admin", "cliente"):
            self.assertEqual(porta("entregador", papel), 403, papel)
        self.assertEqual(porta("separador", "separador"), 200)
        self.assertEqual(porta("separador", "gerente"), 200)
        self.assertEqual(porta("entregador", "entregador"), 200)
        self.assertEqual(porta("gerente", "gerente"), 200)
        self.assertEqual(self._papel_da_rota("/separacao/pegar", "POST"), "separador")
        self.assertEqual(self._papel_da_rota("/entrega/pegar", "POST"), "entregador")
        self.assertEqual(self._papel_da_rota("/gerente/estoque", "GET"), "gerente")
        self.assertEqual(self._papel_da_rota("/gerente/equipe", "GET"), "gerente")

        entrou = login(LoginIn(matricula="1001", pin="somente-teste-1001"))
        self.assertEqual(entrou["funcao"], "separador")
        self.assertEqual(codigo(lambda: login(LoginIn(matricula="1001", pin="1234"))), 401)
        self.assertEqual(login(LoginIn(matricula="TLID", pin="somente-teste-TLID"))["funcao"], "lider")
        for papel in ("embalador", "repositor", "admin", "cliente"):
            self.assertEqual(codigo(lambda papel=papel: quadro(u=quem[papel])), 403)
        self.assertEqual(codigo(lambda: quadro(u=quem["lider"])), 200)
        self.assertEqual(codigo(lambda: quadro(u=quem["separador"])), 200)
        self.assertEqual(codigo(lambda: fila(u=quem["gerente"])), 200)
        self.assertFalse(gerente_equipe(u=quem["gerente"])["gravou"])
        self.assertEqual(codigo(lambda: minha_entrega(u=quem["entregador"])), 200)

        pegou = pegar(u=quem["separador"])
        item = pegou["itens"][0]["id"]
        from app.main import ItemSep
        fechou = concluir("MD-TESTE", [ItemSep(id=item, status="separado")], u=quem["separador"])
        self.assertEqual(fechou["status"], "pronto")
        entregou = pegar_entrega(u=quem["entregador"])
        self.assertEqual(entregou["status"], "atribuido")

    def _papel_da_rota(self, path, method):
        rota = next(r for r in app.routes if getattr(r, "path", None) == path and method in r.methods)
        achadas = []

        def andar(dep):
            call = getattr(dep, "call", None)
            for celula in getattr(call, "__closure__", None) or ():
                if getattr(celula, "cell_contents", None) in ("separador", "entregador", "gerente"):
                    achadas.append(celula.cell_contents)
            for sub in getattr(dep, "dependencies", []) or []:
                andar(sub)

        andar(rota.dependant)
        self.assertEqual(len(achadas), 1)
        return achadas[0]
        with engine.connect() as c:
            pedido = c.execute(text("SELECT status, separador, entregador FROM pedidos WHERE numero = 'MD-TESTE'")).one()
        self.assertEqual((pedido.status, pedido.separador, pedido.entregador), ("atribuido", "1001", "2001"))

    def test_funcao_desconhecida_nao_entra(self):
        with self.assertRaises(Exception):
            with engine.begin() as c:
                _pessoa(c, "XXX", "Papel inventado", "admin", True)

    def test_reposicao_noturna_nao_muda(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Sao_Paulo")
        hoje = datetime.now(tz).date()
        with engine.begin() as c:
            c.execute(text("INSERT INTO lojas (id, nome, cidade) VALUES (2, 'Loja 2', 'BH')"))
            c.execute(text("""INSERT INTO produtos (sku, nome, categoria, corredor, preco, perecivel)
                              VALUES ('SKU1', 'Item', 'Teste', 1, 10, false)"""))
            lid = c.execute(text("""INSERT INTO lotes (loja_id, sku, quantidade, reservado)
                                    VALUES (2, 'SKU1', 5, 0) RETURNING id""")).scalar()
            c.execute(text("""
                INSERT INTO movimentacoes_estoque (
                    lote_id, sku, loja_id, tipo, quantidade, campo, saldo_quantidade, saldo_reservado, criado_em)
                VALUES (:l, 'SKU1', 2, 'saida', -2, 'quantidade', 3, 0, :t)
            """), {"l": lid, "t": datetime(hoje.year, hoje.month, hoje.day, 12, tzinfo=tz) - timedelta(days=1)})
            _elenco(c)
        antes = _contagens()
        r = executar(loja_id=2, corte=hoje + timedelta(days=1), aplicar=True, agora=datetime(hoje.year, hoje.month, hoje.day, 4, tzinfo=tz))
        self.assertFalse(r["gravou"])
        self.assertEqual(antes["reposicao_noturna_origem"], _contagens()["reposicao_noturna_origem"])
        self.assertEqual(antes["lotes"], _contagens()["lotes"])
        aplicar()
        self.assertEqual(antes["movimentacoes_estoque"], _contagens()["movimentacoes_estoque"])
        self.assertEqual(antes["reposicoes_noturnas"], _contagens()["reposicoes_noturnas"])
        self.assertEqual(ALVO["repositor"], 4)


if __name__ == "__main__":
    unittest.main()
