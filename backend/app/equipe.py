"""Equipe interna do laboratório: contagem e vagas novas.

Não remaneja quem já existe, não apaga ninguém e não mexe no recibo noturno AUTO.
Separação, entrega, volume de pedidos e ticket ficam como estão.

Papéis novos (líder, embalador, repositor) ainda não executam tarefa.
A janela 08–22 e a 22:00–06:00 são rótulos da meta, não uma escala validada.

Uso, com DATABASE_URL já no ambiente (não imprima a URL):
  python -m app.equipe
  python -m app.equipe --aplicar
"""
import argparse
import json
import os
import secrets
from sqlalchemy import text

from app.auth import PAPEIS, PAPEIS_INTERNOS, hash_pin
from app.db import engine

ALVO = {"gerente": 1, "lider": 2, "separador": 7, "embalador": 4, "repositor": 4}
META_INTERNA = sum(ALVO.values())
TURNOS = {
    "T1": {"lider": 1, "separador": 4, "embalador": 2},
    "T2": {"lider": 1, "separador": 3, "embalador": 2},
    "noite": {"repositor": 4},
}
# Vagas novas, com nome de papel simulado. Não são pessoas reais e não substituem matrícula existente.
VAGAS = (
    {"matricula": "LABL01", "nome": "Líder simulado 1", "funcao": "lider", "turno": "T1"},
    {"matricula": "LABL02", "nome": "Líder simulado 2", "funcao": "lider", "turno": "T2"},
    {"matricula": "LABE01", "nome": "Embalador simulado 1", "funcao": "embalador", "turno": "T1"},
    {"matricula": "LABE02", "nome": "Embalador simulado 2", "funcao": "embalador", "turno": "T1"},
    {"matricula": "LABE03", "nome": "Embalador simulado 3", "funcao": "embalador", "turno": "T2"},
    {"matricula": "LABE04", "nome": "Embalador simulado 4", "funcao": "embalador", "turno": "T2"},
    {"matricula": "LABR01", "nome": "Repositor simulado 1", "funcao": "repositor", "turno": "noite"},
    {"matricula": "LABR02", "nome": "Repositor simulado 2", "funcao": "repositor", "turno": "noite"},
    {"matricula": "LABR03", "nome": "Repositor simulado 3", "funcao": "repositor", "turno": "noite"},
    {"matricula": "LABR04", "nome": "Repositor simulado 4", "funcao": "repositor", "turno": "noite"},
)
ATIVIDADE = {
    "gerente": "painel do gerente, como hoje",
    "separador": "separação de pedido, como hoje",
    "entregador": "só entrega; fica fora dos 18 internos",
    "lider": "pendente",
    "embalador": "pendente",
    "repositor": "pendente",
}
def _decisoes(ativos, pessoas):
    saida = []
    sep = ativos.get("separador", 0)
    if sep != ALVO["separador"]:
        saida.append(f"Separadores ativos: {sep}. A meta é {ALVO['separador']}. Ninguém muda de papel até haver uma escolha.")
    sem_turno = [p.matricula for p in pessoas if p.ativo and p.funcao == "separador" and not p.turno]
    if sem_turno:
        saida.append("Separadores sem turno: " + ", ".join(sem_turno) + ". T1 pede 4 e T2 pede 3. As vagas seguem sem nome.")
    saida.append("Entrada, intervalo e folga não estão definidos. 08:00–22:00 e 22:00–06:00 não são escala.")
    saida.append("Os papéis de laboratório não têm PIN. Não existe senha padrão.")
    return saida
_CADEADO = 735_000_000


class EquipeRecusada(Exception):
    """Parou antes de gravar pessoa."""


def _pin_inacessivel() -> str:
    """Hash bcrypt de um segredo descartado. Não há PIN para informar nem registrar."""
    return hash_pin(secrets.token_urlsafe(32))


def _exigir_schema(c):
    ok = c.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'funcionarios' AND column_name = 'turno'
    """)).first()
    if not ok:
        raise EquipeRecusada("Falta a coluna funcionarios.turno. Rode a migration da equipe antes. Nada foi gravado.")


def _ler(c):
    pessoas = c.execute(text("""
        SELECT matricula, nome, funcao, ativo, simulado, turno
        FROM funcionarios ORDER BY matricula
    """)).all()
    ativos, por_turno = {}, {}
    for p in pessoas:
        if not p.ativo:
            continue
        ativos[p.funcao] = ativos.get(p.funcao, 0) + 1
        if p.turno:
            chave = (p.turno, p.funcao)
            por_turno[chave] = por_turno.get(chave, 0) + 1
    return pessoas, ativos, por_turno


def _plano(pessoas, ativos):
    """Quem seria inserido, sem ultrapassar a meta e sem alterar matrícula existente."""
    existentes = {p.matricula for p in pessoas}
    projetado = dict(ativos)
    inserir = []
    for vaga in VAGAS:
        if vaga["matricula"] in existentes:
            continue
        if projetado.get(vaga["funcao"], 0) >= ALVO[vaga["funcao"]]:
            continue
        inserir.append(dict(vaga))
        projetado[vaga["funcao"]] = projetado.get(vaga["funcao"], 0) + 1
    return inserir


def _resumo(pessoas, ativos, por_turno, inserir, gravou):
    def bloco(funcao):
        atual = ativos.get(funcao, 0)
        alvo = ALVO.get(funcao)
        return {
            "atual": atual,
            "alvo": alvo,
            "faltam": max((alvo or 0) - atual, 0) if alvo is not None else None,
            "excedente": max(atual - alvo, 0) if alvo is not None else 0,
            "atividade": ATIVIDADE.get(funcao, "desconhecida"),
        }
    interno = sum(ativos.get(f, 0) for f in PAPEIS_INTERNOS)
    turnos = {}
    for turno, metas in TURNOS.items():
        turnos[turno] = {
            funcao: {"alvo": meta, "alocados": por_turno.get((turno, funcao), 0)}
            for funcao, meta in metas.items()
        }
    excedente_sep = max(ativos.get("separador", 0) - ALVO["separador"], 0)
    fechada = interno == META_INTERNA and excedente_sep == 0 and not inserir
    return {
        "modo": "aplicar" if gravou else "preview",
        "gravou": gravou,
        "interno": {"atual": interno, "alvo": META_INTERNA, "fechada": interno == META_INTERNA and excedente_sep == 0},
        "externo_entregador": {"atual": ativos.get("entregador", 0), "conta_no_interno": False},
        "por_funcao": {f: bloco(f) for f in PAPEIS},
        "turnos": turnos,
        "janela_diurna": "08:00-22:00",
        "janela_repositor_prevista": "22:00-06:00",
        "escala_validada": False,
        "reposicao_noturna": "AUTO, sem segunda entrada e sem tarefa de repositor",
        "propostos": [{**v, "simulado": True} for v in inserir],
        "preservados": len(pessoas),
        "decisoes_pendentes": _decisoes(ativos, pessoas),
        "meta_interna_fechada": fechada,
    }


def previa() -> dict:
    if not os.environ.get("DATABASE_URL"):
        raise EquipeRecusada("Sem DATABASE_URL no ambiente. Nada foi gravado.")
    with engine.begin() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        _exigir_schema(c)
        pessoas, ativos, por_turno = _ler(c)
        return _resumo(pessoas, ativos, por_turno, _plano(pessoas, ativos), False)


def aplicar() -> dict:
    if not os.environ.get("DATABASE_URL"):
        raise EquipeRecusada("Sem DATABASE_URL no ambiente. Nada foi gravado.")
    with engine.begin() as c:
        _exigir_schema(c)
        c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CADEADO})
        pessoas, ativos, por_turno = _ler(c)
        inserir = _plano(pessoas, ativos)
        if not inserir:
            saida = _resumo(pessoas, ativos, por_turno, [], False)
            saida["modo"] = "aplicar"
            saida["mensagem"] = "Nada a inserir. Ninguém foi alterado."
            return saida
        for vaga in inserir:
            c.execute(text("""
                INSERT INTO funcionarios (matricula, nome, funcao, pin_hash, ativo, disponivel, simulado, turno)
                VALUES (:m, :n, :f, :p, true, true, true, :t)
            """), {"m": vaga["matricula"], "n": vaga["nome"], "f": vaga["funcao"], "p": _pin_inacessivel(), "t": vaga["turno"]})
        pessoas, ativos, por_turno = _ler(c)
        saida = _resumo(pessoas, ativos, por_turno, [], True)
        saida["inseridos"] = [v["matricula"] for v in inserir]
        saida["mensagem"] = "Só entraram vagas novas. Quem já estava cadastrado não mudou."
        return saida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Equipe interna (padrão: só leitura, não grava)")
    ap.add_argument("--aplicar", action="store_true", help="insere só as vagas novas que ainda cabem na meta")
    args = ap.parse_args(argv)
    try:
        resultado = aplicar() if args.aplicar else previa()
    except EquipeRecusada as e:
        print(str(e))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
