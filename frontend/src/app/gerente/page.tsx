"use client";
// Painel do gerente · passo 1: números do dia e lista de pedidos.
import { useCallback, useEffect, useState } from "react";

const API = "/api"; // passa pelo Next, que repassa para o backend (funciona também pelo túnel)

// Formato dos dados que o backend devolve em GET /gerente/resumo
type Pedido = { numero: string; status: string; cliente: string; bairro: string | null; total: string; criado_em: string; separador: string | null; entregador: string | null };
type Tempos = { loja: number | null; rota: number | null; porta: number | null; total: number | null;
  metas: { loja: number; rota: number; porta: number; total: number }; entregues: number; no_prazo_pct: number | null; atrasados: number };
type Resumo = { contagem: Record<string, number>; faturamento: string; pedidos: Pedido[]; tempos: Tempos };

// Segundos -> "m:ss" (ex.: 754 -> "12:34")
const mmss = (s: number | null) => s == null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
// Cor do cartão comparando com a meta: verde até a meta, amarelo até 50% acima, vermelho além disso
const corMeta = (s: number | null, meta: number) => s == null ? "bg-white text-gray-500" : s <= meta ? "bg-green-100 text-green-800" : s <= meta * 1.5 ? "bg-yellow-100 text-yellow-800" : "bg-red-100 text-red-700";
const brl = (v: number | string) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

// Nome e cor de cada status, na ordem em que aparecem nos cartões
const STATUS: { k: string; nome: string; cor: string }[] = [
  { k: "aguardando_pagamento", nome: "Aguardando pagamento", cor: "bg-gray-100 text-gray-700" },
  { k: "pago", nome: "Pagos (fila)", cor: "bg-blue-100 text-blue-800" },
  { k: "em_separacao", nome: "Separando", cor: "bg-yellow-100 text-yellow-800" },
  { k: "pronto", nome: "Prontos", cor: "bg-green-100 text-green-800" },
  { k: "em_rota", nome: "Em rota", cor: "bg-purple-100 text-purple-800" },
  { k: "entregue", nome: "Entregues", cor: "bg-emerald-100 text-emerald-800" },
  { k: "expirado", nome: "Expirados", cor: "bg-red-100 text-red-700" },
];
// Status detalhados do banco -> rótulo curto na tabela
const ROTULO: Record<string, string> = { aguardando_pagamento: "Aguardando pgto", pago: "Pago", em_separacao: "Separando", pronto: "Pronto",
  atribuido: "Aguardando retirada", a_caminho: "A caminho", chegou: "Na porta", entregue: "Entregue", expirado: "Expirado", pagamento_recusado: "Recusado" };

export default function Gerente() {
  // Login: guardamos o crachá (token) e o nome depois de entrar
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [resumo, setResumo] = useState<Resumo | null>(null);

  async function entrar() {
    const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matricula: mat, pin }) });
    const d = await r.json();
    if (!r.ok) return setErro(d.detail);
    if (d.funcao !== "gerente") return setErro("Esta área é só para gerentes.");
    setUser({ token: d.token, nome: d.nome }); setErro("");
  }

  // Busca o resumo no backend mandando o crachá no cabeçalho Authorization
  const carregar = useCallback(async () => {
    if (!user) return;
    const r = await fetch(`${API}/gerente/resumo`, { headers: { Authorization: `Bearer ${user.token}` } });
    if (r.ok) setResumo(await r.json());
    else if (r.status === 401) setUser(null); // crachá vencido: volta para o login
  }, [user]);

  // Atualiza ao entrar e depois a cada 5 segundos
  useEffect(() => { carregar(); const t = setInterval(carregar, 5000); return () => clearInterval(t); }, [carregar]);

  // Tela de login (mesmo fluxo de matrícula + PIN das outras áreas)
  if (!user) return (
    <main className="flex min-h-screen items-center justify-center bg-slate-800 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">OrbitaSuper</p>
        <p className="mb-5 text-sm text-gray-500">Área do gerente</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Matrícula" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} placeholder="PIN" type="password" maxLength={4} className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);

  return (
    <main className="min-h-screen bg-gray-100 text-gray-900">
      {/* Cabeçalho */}
      <header className="bg-slate-800 text-white">
        <div className="mx-auto flex max-w-[1232px] items-center justify-between px-4 py-3">
          <span className="font-bold">📊 OrbitaSuper · Gerente · {user.nome}</span>
          <button onClick={() => setUser(null)} className="text-sm underline">Sair</button>
        </div>
      </header>

      <div className="mx-auto max-w-[1232px] p-4">
        {!resumo ? <p className="text-gray-500">Carregando…</p> : (<>
          {/* Cartões: faturamento + um cartão por status */}
          <div className="mb-4 grid grid-cols-8 gap-3">
            <div className="rounded-xl bg-slate-800 p-3 text-white shadow">
              <p className="text-xs opacity-80">Faturamento hoje</p>
              <p className="text-xl font-bold">{brl(resumo.faturamento)}</p>
            </div>
            {STATUS.map(s => (
              <div key={s.k} className={`rounded-xl p-3 shadow ${s.cor}`}>
                <p className="text-xs">{s.nome}</p>
                <p className="text-3xl font-bold">{resumo.contagem[s.k] ?? 0}</p>
              </div>))}
          </div>

          {/* Tempos de hoje: médias dos pedidos entregues comparadas com a meta */}
          <h2 className="mb-2 font-bold">Tempos de hoje <span className="text-sm font-normal text-gray-500">· média de {resumo.tempos.entregues} entregue(s)</span></h2>
          <div className="mb-4 grid grid-cols-5 gap-3">
            {([["loja", "Loja", "clique → saída"], ["rota", "Rota", "saída → chegada"], ["porta", "Porta", "chegada → entregue"], ["total", "Total", "clique → entregue"]] as const).map(([k, nome, dica]) => (
              <div key={k} className={`rounded-xl p-3 shadow ${corMeta(resumo.tempos[k], resumo.tempos.metas[k])}`}>
                <p className="text-xs">{nome} <span className="opacity-60">· {dica}</span></p>
                <p className="font-mono text-3xl font-bold">{mmss(resumo.tempos[k])}</p>
                <p className="text-xs opacity-70">meta {mmss(resumo.tempos.metas[k])}</p>
              </div>))}
            {/* No prazo: % de entregues dentro da meta total e quantos atrasaram */}
            <div className={`rounded-xl p-3 shadow ${resumo.tempos.no_prazo_pct == null ? "bg-white text-gray-500" : resumo.tempos.no_prazo_pct >= 90 ? "bg-green-100 text-green-800" : resumo.tempos.no_prazo_pct >= 70 ? "bg-yellow-100 text-yellow-800" : "bg-red-100 text-red-700"}`}>
              <p className="text-xs">No prazo (≤ {mmss(resumo.tempos.metas.total)})</p>
              <p className="text-3xl font-bold">{resumo.tempos.no_prazo_pct == null ? "—" : `${resumo.tempos.no_prazo_pct}%`}</p>
              <p className="text-xs opacity-70">{resumo.tempos.atrasados} atrasado(s)</p>
            </div>
          </div>

          {/* Tabela com os pedidos de hoje (mais novos em cima) */}
          <div className="overflow-hidden rounded-xl bg-white shadow">
            <h2 className="border-b p-3 font-bold">Pedidos de hoje · {resumo.pedidos.length}</h2>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr><th className="p-2">Pedido</th><th>Hora</th><th>Status</th><th>Cliente / bairro</th><th className="text-right">Total</th><th className="pl-4">Separador</th><th>Entregador</th></tr>
              </thead>
              <tbody>
                {resumo.pedidos.map(p => (
                  <tr key={p.numero} className="border-t">
                    <td className="p-2 font-semibold">{p.numero}</td>
                    <td>{new Date(p.criado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })}</td>
                    <td>{ROTULO[p.status] ?? p.status}</td>
                    <td>{p.cliente}{p.bairro ? ` · ${p.bairro}` : ""}</td>
                    <td className="text-right">{brl(p.total)}</td>
                    <td className="pl-4">{p.separador ?? "—"}</td>
                    <td>{p.entregador ?? "—"}</td>
                  </tr>))}
                {!resumo.pedidos.length && <tr><td colSpan={7} className="p-4 text-center text-gray-400">Nenhum pedido hoje ainda.</td></tr>}
              </tbody>
            </table>
          </div>
        </>)}
      </div>
    </main>);
}
