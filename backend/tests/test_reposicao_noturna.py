"""Testes da reposição noturna num Postgres local e vazio.

Não lê .env.prod, não usa o banco daki/super e recusa AMBIENTE=prod.
Rode a partir da pasta backend, com o venv do projeto:

  python -m unittest discover -s tests -v
"""
import io
import json
import os
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

if os.environ.get("AMBIENTE") == "prod":
    raise SystemExit("recusado: teste não roda com AMBIENTE=prod")

HOST = "127.0.0.1"
DB = "reposicao_noturna_teste"
if DB in {"daki", "super", "postgres"} or HOST not in {"127.0.0.1", "localhost"}:
    raise SystemExit("recusado: banco de teste inseguro")

os.environ["DATABASE_URL"] = f"postgresql+psycopg://daki:daki_dev@{HOST}:5432/{DB}"

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import text

from app.db import engine
from app.main import _entrada_lote, _validade_auto
from app.reposicao_noturna import ATOR_AUTOMATICO, ReposicaoRecusada, executar, main

TZ = ZoneInfo("America/Sao_Paulo")
UTC = ZoneInfo("UTC")
HOJE = datetime.now(TZ).date()
ONTEM = HOJE - timedelta(days=1)
ANTEONTEM = HOJE - timedelta(days=2)
AMANHA = HOJE + timedelta(days=1)
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def sp(dia, hh, mm=0, ss=0):
    return datetime(dia.year, dia.month, dia.day, hh, mm, ss, tzinfo=TZ)


def _admin():
    import psycopg
    return psycopg.connect(f"postgresql://daki:daki_dev@{HOST}:5432/postgres", autocommit=True)


def _recriar_banco():
    with _admin() as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (DB,))
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB)))
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER daki").format(sql.Identifier(DB)))


def _apagar_banco():
    engine.dispose()
    with _admin() as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (DB,))
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB)))


def _tabela(c, nome):
    return c.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": nome}).scalar()


def _limpar():
    with engine.begin() as c:
        c.execute(text("""
            TRUNCATE reposicao_noturna_origem, reposicoes_noturnas, movimentacoes_estoque,
                     lotes, produtos, funcionarios, lojas RESTART IDENTITY CASCADE
        """))


def _seq(c):
    seqs = {}
    for tabela in ("lotes", "movimentacoes_estoque", "reposicoes_noturnas"):
        nome = c.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": tabela}).scalar()
        if not nome:
            continue
        seqs[tabela] = tuple(c.execute(text(f"SELECT last_value, is_called FROM {nome}")).one())
    return seqs


def estado():
    with engine.connect() as c:
        counts = {}
        for tabela in ("lotes", "movimentacoes_estoque", "reposicoes_noturnas", "reposicao_noturna_origem", "funcionarios"):
            counts[tabela] = c.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar()
        lotes = [tuple(r) for r in c.execute(text(
            "SELECT id, loja_id, sku, quantidade, reservado, validade, entrada_em FROM lotes ORDER BY id")).all()]
        movs = [tuple(r) for r in c.execute(text("""
            SELECT id, lote_id, sku, loja_id, tipo, quantidade, campo, saldo_quantidade, saldo_reservado,
                   funcionario, motivo, criado_em
            FROM movimentacoes_estoque ORDER BY id""")).all()]
        origem = [tuple(r) for r in c.execute(text("""
            SELECT movimentacao_id, reposicao_id, lote_id, movimentacao_entrada_id, sku, loja_id, dia, unidades
            FROM reposicao_noturna_origem ORDER BY movimentacao_id""")).all()]
        return {"counts": counts, "lotes": lotes, "movs": movs, "origem": origem, "seqs": _seq(c)}


def loja(c, id_):
    c.execute(text("INSERT INTO lojas (id, nome, cidade) VALUES (:i, :n, 'BH')"), {"i": id_, "n": f"Loja {id_}"})


def produto(c, sku, perecivel=False):
    c.execute(text("""INSERT INTO produtos (sku, nome, categoria, corredor, preco, perecivel)
                      VALUES (:s, :s, 'Teste', 1, 1, :p)"""), {"s": sku, "p": perecivel})


def lote(c, loja_id, sku, quantidade=20, reservado=0, validade=None, entrada=None):
    return c.execute(text("""INSERT INTO lotes (loja_id, sku, validade, entrada_em, quantidade, reservado)
                             VALUES (:l, :s, :v, :e, :q, :r) RETURNING id"""),
                     {"l": loja_id, "s": sku, "v": validade, "e": entrada, "q": quantidade, "r": reservado}).scalar()


def mov(c, lote_id, sku, loja_id, tipo, qtd, campo, quando, funcionario=None, motivo=None, saldo_q=0, saldo_r=0):
    return c.execute(text("""
        INSERT INTO movimentacoes_estoque (
            lote_id, sku, loja_id, tipo, quantidade, campo, saldo_quantidade, saldo_reservado,
            funcionario, motivo, criado_em)
        VALUES (:l, :s, :loja, :t, :q, :c, :sq, :sr, :f, :m, :quando)
        RETURNING id"""), {
        "l": lote_id, "s": sku, "loja": loja_id, "t": tipo, "q": qtd, "c": campo,
        "sq": saldo_q, "sr": saldo_r, "f": funcionario, "m": motivo, "quando": quando,
    }).scalar()


def setUpModule():
    os.chdir(BACKEND)
    _recriar_banco()
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    command.upgrade(cfg, "head")
    with engine.begin() as c:
        loja(c, 2)
        produto(c, "SNT")
        sentinela = lote(c, 2, "SNT", quantidade=7)
    # Desce até antes da reposição noturna. Um passo só (-1) passaria a ser outra migration.
    command.downgrade(cfg, "b2c4d6e8f0a1")
    with engine.connect() as c:
        if _tabela(c, "reposicoes_noturnas") or _tabela(c, "reposicao_noturna_origem"):
            raise AssertionError("downgrade deixou tabela da reposição noturna")
        saldo = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": sentinela}).scalar()
        if saldo != 7:
            raise AssertionError("downgrade alterou lote existente")
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        if not _tabela(c, "reposicoes_noturnas") or not _tabela(c, "reposicao_noturna_origem"):
            raise AssertionError("upgrade não recriou as tabelas novas")
        saldo = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": sentinela}).scalar()
        if saldo != 7:
            raise AssertionError("upgrade alterou lote existente")
    _limpar()


def tearDownModule():
    _apagar_banco()


class ReposicaoNoturnaTeste(unittest.TestCase):
    def setUp(self):
        _limpar()

    def test_previa_nao_grava_nem_marcador(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A", quantidade=11)
            mov(c, lid, "A", 2, "saida", -4, "quantidade", sp(ONTEM, 15), funcionario="E02", motivo="entregue ao cliente")
        antes = estado()
        previa = executar(loja_id=2, agora=sp(HOJE, 4))
        com_corte = executar(loja_id=2, corte=ONTEM, agora=sp(HOJE, 4))
        self.assertEqual(antes, estado())
        self.assertEqual(previa["modo"], "preview")
        self.assertFalse(previa["gravou"])
        self.assertIsNotNone(previa["bloqueio"])
        self.assertEqual(previa["demanda"]["unidades"], 0)
        self.assertEqual(previa["ontem"]["unidades"], 4)
        self.assertEqual(previa["ontem"]["movimentos"], 1)
        self.assertFalse(com_corte["gravou"])
        self.assertIsNone(com_corte["bloqueio"])
        self.assertEqual(com_corte["demanda"]["unidades"], 4)
        self.assertEqual(com_corte["demanda"]["itens"][0]["sku"], "A")
        self.assertTrue(com_corte["demanda"]["itens"][0]["validade"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--loja", "2"])
        self.assertEqual(rc, 0)
        corpo = json.loads(buf.getvalue())
        self.assertEqual(corpo["modo"], "preview")
        self.assertFalse(corpo["gravou"])
        self.assertEqual(antes, estado())

    def test_sem_database_url_nao_grava(self):
        with engine.begin() as c:
            loja(c, 2)
        antes = estado()
        url = os.environ.pop("DATABASE_URL")
        try:
            with self.assertRaises(ReposicaoRecusada):
                executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
            with self.assertRaises(ReposicaoRecusada):
                executar(loja_id=2, agora=sp(HOJE, 4))
        finally:
            os.environ["DATABASE_URL"] = url
        self.assertEqual(antes, estado())

    def test_aplicar_sem_corte_recusa(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A")
            mov(c, lid, "A", 2, "saida", -4, "quantidade", sp(ONTEM, 12))
        antes = estado()
        with self.assertRaises(ReposicaoRecusada):
            executar(loja_id=2, aplicar=True, agora=sp(HOJE, 4))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--loja", "2", "--aplicar"])
        self.assertEqual(rc, 2)
        self.assertIn("corte", buf.getvalue().lower())
        with redirect_stdout(io.StringIO()):
            rc_ruim = main(["--loja", "2", "--corte", "AAAA-MM-DD", "--aplicar"])
        self.assertEqual(rc_ruim, 2)
        self.assertEqual(antes, estado())

    def test_corte_exclui_historico(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            produto(c, "B")
            la = lote(c, 2, "A", quantidade=30)
            lb = lote(c, 2, "B", quantidade=8)
            antigo = mov(c, la, "A", 2, "saida", -5, "quantidade", sp(ANTEONTEM, 11))
            recente = mov(c, la, "A", 2, "saida", -3, "quantidade", sp(ONTEM, 11))
            outro = mov(c, lb, "B", 2, "saida", -1, "quantidade", sp(ONTEM, 18))
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertTrue(r["gravou"])
        self.assertEqual(r["demanda"]["unidades"], 4)
        self.assertEqual(r["antes_do_corte"], {"movimentos": 1, "unidades": 5})
        with engine.connect() as c:
            vinculados = {row[0] for row in c.execute(text("SELECT movimentacao_id FROM reposicao_noturna_origem"))}
            saldo_a = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": la}).scalar()
        self.assertEqual(vinculados, {recente, outro})
        self.assertNotIn(antigo, vinculados)
        self.assertEqual(saldo_a, 30)
        _limpar()
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            la = lote(c, 2, "A", quantidade=30)
            mov(c, la, "A", 2, "saida", -9, "quantidade", sp(ONTEM, 11))
        antes = estado()
        vazio = executar(loja_id=2, corte=HOJE, aplicar=True, agora=sp(HOJE, 4))
        self.assertFalse(vazio["gravou"])
        self.assertEqual(vazio["demanda"]["unidades"], 0)
        self.assertEqual(vazio["antes_do_corte"]["unidades"], 9)
        self.assertEqual(antes["counts"], estado()["counts"])
        self.assertEqual(antes["lotes"], estado()["lotes"])
        self.assertEqual(antes["origem"], estado()["origem"])

    def test_escopo_da_loja(self):
        with engine.begin() as c:
            loja(c, 1)
            loja(c, 2)
            produto(c, "SECO", perecivel=False)
            entrada = ANTEONTEM
            lote(c, 1, "SECO", quantidade=10, validade=entrada + timedelta(days=15), entrada=entrada)
            l1 = lote(c, 1, "SECO", quantidade=10)
            l2 = lote(c, 2, "SECO", quantidade=10, validade=None, entrada=None)
            mov(c, l1, "SECO", 1, "saida", -4, "quantidade", sp(ONTEM, 10))
            id2 = mov(c, l2, "SECO", 2, "saida", -6, "quantidade", sp(ONTEM, 10))
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertEqual(r["demanda"]["unidades"], 6)
        with engine.connect() as c:
            novo = c.execute(text("""
                SELECT loja_id, quantidade, validade, entrada_em FROM lotes
                WHERE sku = 'SECO' AND entrada_em = :hoje AND quantidade = 6
            """), {"hoje": HOJE}).one()
            origem = c.execute(text("SELECT movimentacao_id, loja_id FROM reposicao_noturna_origem")).all()
            q1 = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": l1}).scalar()
        self.assertEqual(novo.loja_id, 2)
        self.assertEqual(novo.quantidade, 6)
        self.assertEqual(novo.entrada_em, HOJE)
        self.assertEqual(novo.validade, HOJE + timedelta(days=180))
        self.assertEqual([(o.movimentacao_id, o.loja_id) for o in origem], [(id2, 2)])
        self.assertEqual(q1, 10)

    def test_so_saida_fisica_negativa(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A", quantidade=40, reservado=0)
            quando = sp(ONTEM, 16)
            mov(c, lid, "A", 2, "entrada", 20, "quantidade", quando, funcionario="9001", motivo="reposição")
            mov(c, lid, "A", 2, "reserva", 5, "reservado", quando)
            mov(c, lid, "A", 2, "liberacao", -2, "reservado", quando)
            s1 = mov(c, lid, "A", 2, "saida", -4, "quantidade", quando, motivo="entregue ao cliente")
            mov(c, lid, "A", 2, "saida", 3, "quantidade", quando, motivo="sinal invertido")
            mov(c, lid, "A", 2, "perda", -1, "quantidade", quando, motivo="vencido")
            mov(c, lid, "A", 2, "ajuste", 8, "quantidade", quando, motivo="contagem")
            s2 = mov(c, lid, "A", 2, "saida", -1, "quantidade", quando, motivo="entregue ao cliente")
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertEqual(r["demanda"]["unidades"], 5)
        self.assertEqual(r["demanda"]["produtos"], 1)
        self.assertEqual(r["ignorados"]["entrada"], 1)
        self.assertEqual(r["ignorados"]["reserva"], 1)
        self.assertEqual(r["ignorados"]["liberacao"], 1)
        self.assertEqual(r["ignorados"]["perda"], 1)
        self.assertEqual(r["ignorados"]["ajuste"], 1)
        self.assertEqual(r["ignorados"]["saida_nao_fisica"], 1)
        with engine.connect() as c:
            origem = {row[0] for row in c.execute(text("SELECT movimentacao_id FROM reposicao_noturna_origem"))}
            novo = c.execute(text("SELECT quantidade FROM lotes WHERE sku = 'A' AND id <> :id"), {"id": lid}).scalar()
            velho = c.execute(text("SELECT quantidade, reservado FROM lotes WHERE id = :id"), {"id": lid}).one()
        self.assertEqual(origem, {s1, s2})
        self.assertEqual(novo, 5)
        self.assertEqual((velho.quantidade, velho.reservado), (40, 0))

    def test_meia_noite_sao_paulo(self):
        antes_meia = sp(ONTEM, 23, 59, 59)
        depois_meia = sp(HOJE, 0, 0, 0)
        utc_ainda_ontem = datetime(HOJE.year, HOJE.month, HOJE.day, 2, 59, 59, tzinfo=UTC)
        utc_ja_hoje = datetime(HOJE.year, HOJE.month, HOJE.day, 3, 0, 0, tzinfo=UTC)
        marcas = [
            ("A", -1, antes_meia),
            ("B", -10, depois_meia),
            ("C", -100, utc_ainda_ontem),
            ("D", -1000, utc_ja_hoje),
        ]
        with engine.begin() as c:
            loja(c, 2)
            for sku, qtd, quando in marcas:
                produto(c, sku)
                lid = lote(c, 2, sku)
                mov(c, lid, sku, 2, "saida", qtd, "quantidade", quando)
        r = executar(loja_id=2, corte=ANTEONTEM, aplicar=True, agora=sp(HOJE, 4))
        esperados = []
        for sku, qtd, quando in marcas:
            dia = quando.astimezone(TZ).date()
            if ANTEONTEM <= dia < HOJE:
                esperados.append(sku)
        self.assertEqual(sorted(item["sku"] for item in r["lotes"]), sorted(esperados))
        self.assertIn("A", esperados)
        self.assertNotIn("B", esperados)
        self.assertEqual(utc_ainda_ontem.astimezone(TZ).date(), ONTEM)
        self.assertEqual(utc_ja_hoje.astimezone(TZ).date(), HOJE)
        self.assertIn("C", esperados)
        self.assertNotIn("D", esperados)

    def test_chegada_tardia_e_lancamento_atrasado(self):
        with engine.begin() as c:
            loja(c, 2)
            for sku in ("CEDO", "TARDE", "MADRU"):
                produto(c, sku)
            cedo = lote(c, 2, "CEDO", quantidade=15)
            tarde = lote(c, 2, "TARDE", quantidade=15)
            madru = lote(c, 2, "MADRU", quantidade=15)
            id_cedo = mov(c, cedo, "CEDO", 2, "saida", -2, "quantidade", sp(ONTEM, 21))
            id_tarde = mov(c, tarde, "TARDE", 2, "saida", -7, "quantidade", sp(HOJE, 0, 40))
            id_madru = mov(c, madru, "MADRU", 2, "saida", -1, "quantidade", sp(HOJE, 3, 30))
        primeira = executar(loja_id=2, corte=ANTEONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertEqual(sorted(item["sku"] for item in primeira["lotes"]), ["CEDO"])
        self.assertEqual(primeira["lotes"][0]["unidades"], 2)
        with engine.connect() as c:
            vinculados = {row[0] for row in c.execute(text("SELECT movimentacao_id FROM reposicao_noturna_origem"))}
        self.assertEqual(vinculados, {id_cedo})
        with engine.begin() as c:
            id_atraso = mov(c, cedo, "CEDO", 2, "saida", -3, "quantidade", sp(ONTEM, 18), motivo="saída lançada depois")
        seguinte = executar(loja_id=2, corte=ANTEONTEM, aplicar=True, agora=sp(AMANHA, 4))
        recebidos = {item["sku"]: item["unidades"] for item in seguinte["lotes"]}
        self.assertEqual(recebidos, {"CEDO": 3, "MADRU": 1, "TARDE": 7})
        with engine.connect() as c:
            vezes = c.execute(text("""
                SELECT movimentacao_id, COUNT(*) FROM reposicao_noturna_origem GROUP BY movimentacao_id
            """)).all()
            saldo_cedo = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": cedo}).scalar()
        self.assertEqual({row[0] for row in vezes}, {id_cedo, id_tarde, id_madru, id_atraso})
        self.assertTrue(all(row[1] == 1 for row in vezes))
        self.assertEqual(saldo_cedo, 15)

    def test_validade_vencida_ou_nula(self):
        amanha = datetime.now(TZ).date() + timedelta(days=1)
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "PEREC", perecivel=True)
            produto(c, "SECO", perecivel=False)
            produto(c, "PRAZO", perecivel=False)
            produto(c, "NEG", perecivel=True)
            produto(c, "NULO", perecivel=False)
            lote(c, 2, "PEREC", validade=None, entrada=None)
            lote(c, 2, "SECO", validade=None, entrada=None)
            lote(c, 2, "PRAZO", quantidade=4, validade=HOJE - timedelta(days=10), entrada=HOJE - timedelta(days=20))
            lote(c, 2, "NEG", quantidade=4, validade=HOJE - timedelta(days=10), entrada=HOJE - timedelta(days=5))
            lote(c, 2, "NULO", quantidade=4, validade=(HOJE - timedelta(days=30)) + timedelta(days=12), entrada=HOJE - timedelta(days=30))
            ln = lote(c, 2, "NULO", quantidade=4, validade=None, entrada=None)
            for sku, lid in (
                ("PEREC", c_id(c, "PEREC")),
                ("SECO", c_id(c, "SECO")),
                ("PRAZO", c_id(c, "PRAZO")),
                ("NEG", c_id(c, "NEG")),
                ("NULO", ln),
            ):
                mov(c, lid, sku, 2, "saida", -1, "quantidade", sp(ONTEM, 9))
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        por = {item["sku"]: item for item in r["lotes"]}
        self.assertEqual(date_de(por["PEREC"]["validade"]), HOJE + timedelta(days=7))
        self.assertEqual(date_de(por["SECO"]["validade"]), HOJE + timedelta(days=180))
        self.assertEqual(date_de(por["PRAZO"]["validade"]), HOJE + timedelta(days=10))
        self.assertEqual(date_de(por["NEG"]["validade"]), HOJE + timedelta(days=7))
        self.assertEqual(date_de(por["NULO"]["validade"]), HOJE + timedelta(days=12))
        for item in r["lotes"]:
            validade = date_de(item["validade"])
            self.assertGreaterEqual(validade, amanha)
            self.assertGreaterEqual(validade, date_de(item["entrada_em"]))
        with engine.connect() as c:
            vencidos = c.execute(text("""
                SELECT COUNT(*) FROM lotes
                WHERE entrada_em = :hoje AND validade < (now() AT TIME ZONE 'America/Sao_Paulo')::date
            """), {"hoje": HOJE}).scalar()
        self.assertEqual(vencidos, 0)

    def test_demanda_vazia(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A", quantidade=6)
            mov(c, lid, "A", 2, "entrada", 6, "quantidade", sp(ONTEM, 8), motivo="recebimento")
        antes = estado()
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertFalse(r["gravou"])
        self.assertEqual(r["demanda"]["unidades"], 0)
        self.assertIsNone(r["reposicao_id"])
        self.assertEqual(antes, estado())

    def test_loja_e_ator_invalidos(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A")
            mov(c, lid, "A", 2, "saida", -2, "quantidade", sp(ONTEM, 10))
        antes = estado()
        for ator in ("9001", "", None, "auto", "AUTOMATICO"):
            with self.assertRaises(ReposicaoRecusada):
                executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4), ator=ator)
        with self.assertRaises(ReposicaoRecusada):
            executar(loja_id=99, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        with self.assertRaises(ReposicaoRecusada):
            executar(loja_id=0, corte=ONTEM, aplicar=False, agora=sp(HOJE, 4))
        self.assertEqual(antes, estado())
        with engine.begin() as c:
            c.execute(text("""INSERT INTO funcionarios (matricula, nome, funcao, pin_hash, ativo)
                              VALUES ('AUTO', 'Pessoa real', 'gerente', 'teste-sem-pin', true)"""))
        com_pessoa = estado()
        with self.assertRaises(ReposicaoRecusada):
            executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertEqual(com_pessoa, estado())

    def test_reexecucao(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            lid = lote(c, 2, "A", quantidade=12)
            mov(c, lid, "A", 2, "saida", -4, "quantidade", sp(ONTEM, 13))
        primeira = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        depois = estado()
        segunda = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertTrue(primeira["gravou"])
        self.assertFalse(segunda["gravou"])
        self.assertEqual(segunda["demanda"]["unidades"], 0)
        self.assertEqual(segunda["ja_vinculados"]["unidades"], 4)
        self.assertEqual(depois, estado())

    def test_concorrencia_uma_vez(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            produto(c, "B")
            la = lote(c, 2, "A", quantidade=9)
            lb = lote(c, 2, "B", quantidade=9)
            for i, (lid, sku) in enumerate(((la, "A"), (lb, "B"))):
                mov(c, lid, sku, 2, "saida", -2, "quantidade", sp(ONTEM, 10, i))
                mov(c, lid, sku, 2, "saida", -3, "quantidade", sp(ONTEM, 11, i))
        barreira = threading.Barrier(2)
        segurou, soltou, viu_vazio = [], [], []

        def gancho(candidatos):
            if not candidatos:
                viu_vazio.append(time.monotonic())
                return
            segurou.append(time.monotonic())
            time.sleep(0.4)
            soltou.append(time.monotonic())

        erros, resultados = [], []

        def rodar():
            barreira.wait()
            try:
                resultados.append(executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4), _gancho=gancho))
            except Exception as e:
                erros.append(e)

        t1 = threading.Thread(target=rodar)
        t2 = threading.Thread(target=rodar)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(erros, [])
        self.assertEqual(sum(1 for r in resultados if r["gravou"]), 1)
        self.assertEqual(sum(r["demanda"]["unidades"] for r in resultados), 10)
        self.assertTrue(segurou and soltou and viu_vazio)
        self.assertGreaterEqual(viu_vazio[0], soltou[0])
        with engine.connect() as c:
            origem = c.execute(text("SELECT COUNT(*), COALESCE(SUM(unidades), 0) FROM reposicao_noturna_origem")).one()
            runs = c.execute(text("SELECT COUNT(*) FROM reposicoes_noturnas")).scalar()
            novos = c.execute(text("SELECT COALESCE(SUM(quantidade), 0) FROM lotes WHERE id NOT IN (:a, :b)"), {"a": la, "b": lb}).scalar()
        self.assertEqual((origem[0], int(origem[1]), runs, int(novos)), (4, 10, 1, 10))

    def test_falha_desfaz_entrada_e_vinculo(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "AAA")
            lid = lote(c, 2, "AAA", quantidade=18)
            mov(c, lid, "AAA", 2, "saida", -4, "quantidade", sp(ONTEM, 12))
            mov(c, lid, "ZZZ", 2, "saida", -5, "quantidade", sp(ONTEM, 12))
        antes = estado()
        with self.assertRaises(ReposicaoRecusada) as ctx:
            executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertIn("ZZZ", str(ctx.exception))
        # Postgres não desfaz sequência. O teste confere as linhas: lote, extrato e vínculo voltam ao que eram.
        depois = estado()
        for chave in ("counts", "lotes", "movs", "origem"):
            self.assertEqual(antes[chave], depois[chave])

    def test_auditoria_sem_funcionario_inventado(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "A")
            produto(c, "B")
            la = lote(c, 2, "A", quantidade=10)
            lb = lote(c, 2, "B", quantidade=10)
            sa = mov(c, la, "A", 2, "saida", -4, "quantidade", sp(ONTEM, 14), funcionario="E02", motivo="entregue ao cliente", saldo_q=6, saldo_r=0)
            sb = mov(c, lb, "B", 2, "saida", -1, "quantidade", sp(ONTEM, 15), funcionario="E02", motivo="entregue ao cliente", saldo_q=9, saldo_r=0)
        antes_mov = {m[0]: m for m in estado()["movs"]}
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        with engine.connect() as c:
            pessoas = c.execute(text("SELECT COUNT(*) FROM funcionarios WHERE matricula = 'AUTO'")).scalar()
            entradas = c.execute(text("""
                SELECT sku, quantidade, campo, saldo_quantidade, saldo_reservado, funcionario, motivo, pedido_id
                FROM movimentacoes_estoque WHERE tipo = 'entrada' AND funcionario = 'AUTO' ORDER BY sku
            """)).all()
            origem = c.execute(text("""
                SELECT o.movimentacao_id, o.sku, o.unidades, o.loja_id, o.dia, o.lote_id,
                       e.quantidade AS entrada_qtd, l.loja_id AS lote_loja, l.quantidade AS lote_qtd, l.reservado AS lote_res
                FROM reposicao_noturna_origem o
                JOIN movimentacoes_estoque e ON e.id = o.movimentacao_entrada_id
                JOIN lotes l ON l.id = o.lote_id
                ORDER BY o.movimentacao_id
            """)).all()
            fontes = c.execute(text("""
                SELECT id, tipo, quantidade, campo, funcionario, motivo FROM movimentacoes_estoque WHERE id IN (:a, :b) ORDER BY id
            """), {"a": sa, "b": sb}).all()
        self.assertEqual(pessoas, 0)
        self.assertEqual(len(entradas), 2)
        self.assertEqual(r["ator"], ATOR_AUTOMATICO)
        for entrada in entradas:
            self.assertEqual(entrada.campo, "quantidade")
            self.assertGreater(entrada.quantidade, 0)
            self.assertEqual(entrada.saldo_quantidade, entrada.quantidade)
            self.assertEqual(entrada.saldo_reservado, 0)
            self.assertEqual(entrada.funcionario, "AUTO")
            self.assertIsNone(entrada.pedido_id)
            self.assertIn("reposição noturna", entrada.motivo)
            self.assertIn("loja 2", entrada.motivo)
            self.assertNotIn("9001", entrada.motivo)
        self.assertEqual({o.movimentacao_id for o in origem}, {sa, sb})
        for o in origem:
            self.assertEqual(o.loja_id, 2)
            self.assertEqual(o.dia, ONTEM)
            self.assertEqual(o.lote_loja, 2)
            self.assertEqual(o.lote_res, 0)
        por_lote = {}
        for o in origem:
            por_lote.setdefault(o.lote_id, {"un": 0, "entrada": o.entrada_qtd, "lote": o.lote_qtd})
            por_lote[o.lote_id]["un"] += o.unidades
        for info in por_lote.values():
            self.assertEqual(info["un"], info["entrada"])
            self.assertEqual(info["un"], info["lote"])
        self.assertEqual([(f.id, f.tipo, f.quantidade, f.campo, f.funcionario, f.motivo) for f in fontes], [
            (sa, "saida", -4, "quantidade", "E02", "entregue ao cliente"),
            (sb, "saida", -1, "quantidade", "E02", "entregue ao cliente"),
        ])
        depois = {m[0]: m for m in estado()["movs"]}
        self.assertEqual(antes_mov[sa], depois[sa])
        self.assertEqual(antes_mov[sb], depois[sb])

    def test_entrada_manual_nao_abate_saida(self):
        with engine.begin() as c:
            loja(c, 2)
            produto(c, "X")
            lid = lote(c, 2, "X", quantidade=50)
            entrada = mov(c, lid, "X", 2, "entrada", 20, "quantidade", sp(HOJE, 9), funcionario="9001", motivo="reposição")
            saida = mov(c, lid, "X", 2, "saida", -4, "quantidade", sp(ONTEM, 20), funcionario="E02", motivo="entregue ao cliente")
        r = executar(loja_id=2, corte=ONTEM, aplicar=True, agora=sp(HOJE, 4))
        self.assertEqual(r["demanda"]["unidades"], 4)
        with engine.connect() as c:
            origem = [tuple(row) for row in c.execute(text("SELECT movimentacao_id, unidades FROM reposicao_noturna_origem"))]
            novo = c.execute(text("SELECT quantidade FROM lotes WHERE sku = 'X' AND id <> :id"), {"id": lid}).scalar()
            velho = c.execute(text("SELECT quantidade FROM lotes WHERE id = :id"), {"id": lid}).scalar()
            manual = c.execute(text("SELECT funcionario, quantidade FROM movimentacoes_estoque WHERE id = :id"), {"id": entrada}).one()
        self.assertEqual(origem, [(saida, 4)])
        self.assertEqual(novo, 4)
        self.assertEqual(velho, 50)
        self.assertEqual((manual.funcionario, manual.quantidade), ("9001", 20))

    def test_entrada_lote_explicita_preserva_api_manual(self):
        with engine.begin() as c:
            loja(c, 1)
            loja(c, 2)
            produto(c, "P", perecivel=False)
            lote(c, 2, "P", validade=ONTEM + timedelta(days=40), entrada=ONTEM)
            lote(c, 1, "P", validade=ANTEONTEM + timedelta(days=9), entrada=ANTEONTEM)
        with engine.begin() as c:
            manual = _validade_auto(c, "P", HOJE)
            loja2 = _validade_auto(c, "P", HOJE, loja_id=2)
        self.assertEqual(manual, HOJE + timedelta(days=9))
        self.assertEqual(loja2, max(HOJE + timedelta(days=40), HOJE + timedelta(days=1)))
        with engine.begin() as c:
            sem_loja = _entrada_lote(c, "P", 2, HOJE + timedelta(days=9), HOJE, {"sub": "G01"}, "recebimento")
            com_loja = _entrada_lote(c, "P", 3, HOJE + timedelta(days=40), HOJE, {"sub": "G01"}, "recebimento", loja_id=2)
            destinos = {r.id: r.loja_id for r in c.execute(text(
                "SELECT id, loja_id FROM lotes WHERE id IN (:a, :b)"), {"a": sem_loja, "b": com_loja}).all()}
        self.assertEqual(destinos[sem_loja], 1)
        self.assertEqual(destinos[com_loja], 2)
        with self.assertRaises(HTTPException):
            with engine.begin() as c:
                _entrada_lote(c, "P", 1, None, HOJE, {"sub": "G01"}, "recebimento", loja_id=99)
        with engine.connect() as c:
            qtd = c.execute(text("SELECT COALESCE(SUM(quantidade), 0) FROM lotes WHERE id IN (:a, :b)"),
                            {"a": sem_loja, "b": com_loja}).scalar()
        self.assertEqual(qtd, 5)


def c_id(c, sku):
    return c.execute(text("SELECT MIN(id) FROM lotes WHERE sku = :s"), {"s": sku}).scalar()


def date_de(valor):
    if isinstance(valor, str):
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    return valor


if __name__ == "__main__":
    unittest.main()
