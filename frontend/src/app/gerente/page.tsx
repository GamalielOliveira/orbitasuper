"use client";
// Painel do gerente · passo 1: números do dia e lista de pedidos.
import { useCallback, useEffect, useMemo, useState } from "react";
import Entregas, { type FiltroEntregas } from "./Entregas";
import Padroes from "./Padroes";
import Separadores from "./Separadores";
import Vendas from "./Vendas";

const API = "/api"; // passa pelo Next, que repassa para o backend (funciona também pelo túnel)

// Formato dos dados que o backend devolve em GET /gerente/resumo
type Pedido = { numero: string; status: string; cliente: string; bairro: string | null; total: string; criado_em: string; separador: string | null; entregador: string | null;
  itens: number; loja: number | null; rota: number | null; porta: number | null; total_seg: number | null; no_prazo: boolean | null;
  decorrido: number | null; idade: number | null; atrasado: boolean };
type Tempos = { loja: number | null; rota: number | null; porta: number | null; total: number | null;
  metas: { loja: number; rota: number; porta: number; total: number }; entregues: number; no_prazo_pct: number | null; atrasados: number };
type Entregador = { matricula: string; nome: string; entregas: number; rota: number | null; porta: number | null; total: number | null;
  atrasos: number; no_prazo_pct: number | null; pedido_atual: string | null; distancia_km: number | null };
type ColEnt = "nome" | "entregas" | "rota" | "porta" | "total" | "atrasos" | "no_prazo_pct" | "distancia_km";
type Resumo = { entregadores: Entregador[]; de: string; ate: string; hoje: string; contagem: Record<string, number>; faturamento: string; pedidos: Pedido[]; tempos: Tempos };

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

// Data de hoje em São Paulo no formato AAAA-MM-DD, deslocada em N dias
// Hoje em São Paulo (AAAA-MM-DD). Só é chamada depois que a página abre no navegador (useEffect),
// porque o Next 16 não aceita ler o relógio durante a renderização.
const hojeSP = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
// Soma N dias a uma data AAAA-MM-DD (conta em UTC para não sofrer com fuso/horário de verão)
const somaDias = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
type Periodo = "hoje" | "ontem" | "7d" | "custom";
// Agrupa status do banco nos mesmos grupos dos cartões (as etapas da rua viram "em_rota")
const grupo = (st: string) => ["atribuido", "a_caminho", "chegou"].includes(st) ? "em_rota" : st;
// Colunas que podem ser ordenadas clicando no cabeçalho
type Coluna = "numero" | "data" | "criado_em" | "status" | "cliente" | "itens" | "total" | "separador" | "entregador" | "loja" | "rota" | "porta" | "total_seg";
// Média de uma lista de números ignorando vazios
const media = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : null; };
// Cor de texto de uma célula de tempo vs meta
const corCel = (s: number | null, meta: number) => s == null ? "" : s <= meta ? "text-green-700" : s <= meta * 1.5 ? "text-yellow-700 font-semibold" : "text-red-700 font-bold";

export default function Gerente() {
  // Login: guardamos o crachá (token) e o nome depois de entrar
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [resumo, setResumo] = useState<Resumo | null>(null);
  // Filtros e ordenação da tabela (ficam guardados no estado, então a atualização de 5s não os apaga)
  const [fStatus, setFStatus] = useState(""); const [fSep, setFSep] = useState(""); const [fEnt, setFEnt] = useState("");
  const [soAtrasados, setSoAtrasados] = useState(false); const [busca, setBusca] = useState("");
  // Período: hoje (padrão), ontem, últimos 7 dias ou personalizado (de/até)
  const [periodo, setPeriodo] = useState<Periodo>("hoje");
  // "hoje" começa vazio e é preenchido depois de montar a página (evita o aviso de Date.now do Next)
  const [hoje, setHoje] = useState("");
  const [de, setDe] = useState(""); const [ate, setAte] = useState("");
  useEffect(() => { const h = hojeSP(); setHoje(h); setDe(somaDias(h, -6)); setAte(h); }, []);
  const consulta = !hoje || periodo === "hoje" ? "" : periodo === "ontem" ? `?de=${somaDias(hoje, -1)}&ate=${somaDias(hoje, -1)}`
    : periodo === "7d" ? `?de=${somaDias(hoje, -6)}&ate=${hoje}` : `?de=${de}&ate=${ate}`;
  const [erroPer, setErroPer] = useState("");
  // Aba atual: visão geral (cartões + pedidos), entregas (análise) ou entregadores
  const [aba, setAba] = useState<"geral" | "vendas" | "entregas" | "padroes" | "separadores" | "entregadores">("geral");
  // filtro levado da aba Padrões para a aba Entregas (o "versao" força a tabela a reaplicar)
  const [filtroEnt, setFiltroEnt] = useState<{ f: FiltroEntregas; versao: number }>({ f: {}, versao: 0 });
  const [ordemEnt, setOrdemEnt] = useState<{ col: ColEnt; asc: boolean }>({ col: "entregas", asc: false }); // ordenação da tabela de entregadores
  const [ordem, setOrdem] = useState<{ col: Coluna; asc: boolean }>({ col: "criado_em", asc: false });

  // Aplica filtros + ordenação sobre a lista que veio do backend
  const linhas = useMemo(() => {
    if (!resumo) return [];
    const b = busca.trim().toLowerCase();
    const l = resumo.pedidos.filter(p =>
      (!fStatus || grupo(p.status) === fStatus) && (!fSep || p.separador === fSep) && (!fEnt || p.entregador === fEnt) &&
      (!soAtrasados || p.atrasado) && (!b || p.numero.toLowerCase().includes(b) || (p.bairro ?? "").toLowerCase().includes(b)));
    // valor usado na ordenação (o total vem como texto do backend, então vira número)
    const v = (p: Pedido) => { const x = ordem.col === "data" ? p.criado_em : p[ordem.col]; return x == null ? null : ordem.col === "total" ? Number(x) : x; };
    return [...l].sort((a, c) => {
      const x = v(a), y = v(c);
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; // vazios sempre no fim
      return (x < y ? -1 : x > y ? 1 : 0) * (ordem.asc ? 1 : -1);
    });
  }, [resumo, fStatus, fSep, fEnt, soAtrasados, busca, ordem]);

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
    const r = await fetch(`${API}/gerente/resumo${consulta}`, { headers: { Authorization: `Bearer ${user.token}` } });
    if (r.ok) { setResumo(await r.json()); setErroPer(""); }
    else if (r.status === 422) setErroPer((await r.json()).detail); // período inválido (ex.: mais de 31 dias)
    else if (r.status === 401) setUser(null); // crachá vencido: volta para o login
  }, [user, consulta]); // muda o período -> busca de novo

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

  // Texto do período nos títulos: "hoje" só quando for hoje
  const rotulo = !resumo ? "" : resumo.de === resumo.hoje && resumo.ate === resumo.hoje ? "hoje"
    : resumo.de === resumo.ate ? (periodo === "ontem" ? "ontem" : ddmm(resumo.de)) : periodo === "7d" ? "últimos 7 dias" : `${ddmm(resumo.de)} a ${ddmm(resumo.ate)}`;
  const METAS = resumo?.tempos.metas ?? { loja: 300, rota: 900, porta: 180, total: 1200 }; // metas vindas do backend

  return (
    <main className="min-h-screen bg-gray-100 text-gray-900">
      {/* Cabeçalho */}
      <header className="bg-slate-800 text-white">
        <div className="mx-auto flex items-center justify-between px-6 py-3">
          <span className="font-bold">📊 OrbitaSuper · Gerente · {user.nome}</span>
          <button onClick={() => setUser(null)} className="text-sm underline">Sair</button>
        </div>
      </header>

      <div className="px-6 py-4">
        {!resumo ? <p className="text-gray-500">Carregando…</p> : (<>
          {/* Barra de período: muda o intervalo de datas de todos os números da página */}
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            {([["hoje", "Hoje"], ["ontem", "Ontem"], ["7d", "Últimos 7 dias"], ["custom", "Personalizado"]] as [Periodo, string][]).map(([k, nome]) => (
              <button key={k} onClick={() => setPeriodo(k)} className={`rounded-full px-4 py-1.5 ${periodo === k ? "bg-slate-800 text-white" : "bg-white shadow"}`}>{nome}</button>))}
            {periodo === "custom" && (<>
              <input type="date" value={de} max={ate} onChange={e => setDe(e.target.value)} className="rounded-lg bg-white px-2 py-1 shadow" />
              <span>até</span>
              <input type="date" value={ate} min={de} max={hoje} onChange={e => setAte(e.target.value)} className="rounded-lg bg-white px-2 py-1 shadow" />
            </>)}
            {erroPer && <span className="text-red-600">{erroPer}</span>}
          </div>

          {/* Abas: separam os assuntos para a tela não ficar poluída (o período vale para todas) */}
          <div className="mb-4 flex gap-1 border-b">
            {([["geral", "Visão geral"], ["vendas", "Vendas"], ["entregas", "Entregas"], ["padroes", "Padrões"], ["separadores", "Separadores"], ["entregadores", "Entregadores"]] as const).map(([k, nome]) => (
              <button key={k} onClick={() => { if (k === "entregas" && aba !== "entregas") setFiltroEnt(x => ({ f: {}, versao: x.versao + 1 })); setAba(k); }}
                className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${aba === k ? "border-slate-800 text-slate-900" : "border-transparent text-gray-500 hover:text-gray-800"}`}>{nome}</button>))}
          </div>

          {aba === "geral" && (<>
          {/* Cartões: faturamento + um cartão por status */}
          <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
            <div className="rounded-xl bg-slate-800 p-3 text-white shadow">
              <p className="text-xs opacity-80">Faturamento {rotulo}</p>
              <p className="text-xl font-bold">{brl(resumo.faturamento)}</p>
            </div>
            {STATUS.map(s => (
              <div key={s.k} className={`rounded-xl p-3 shadow ${s.cor}`}>
                <p className="text-xs">{s.nome}</p>
                <p className="text-3xl font-bold">{resumo.contagem[s.k] ?? 0}</p>
              </div>))}
          </div>

          {/* Tempos de hoje: médias dos pedidos entregues comparadas com a meta */}
          <h2 className="mb-2 font-bold">Tempos {rotulo === "hoje" ? "de hoje" : `· ${rotulo}`} <span className="text-sm font-normal text-gray-500">· média de {resumo.tempos.entregues} entregue(s)</span></h2>
          <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
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

          </>)}

          {/* Aba Entregas: componente próprio (arquivo Entregas.tsx) */}
          {aba === "entregas" && <Entregas key={filtroEnt.versao} token={user.token} consulta={consulta} filtro={filtroEnt.f} />}

          {/* Aba Padrões: onde os atrasos se concentram; clicar num grupo abre Entregas já filtrada */}
          {/* Aba Separadores: desempenho de quem separa (arquivo Separadores.tsx) */}
          {/* Aba Vendas: faturamento e perdas (arquivo Vendas.tsx) */}
          {aba === "vendas" && <Vendas token={user.token} consulta={consulta} rotulo={rotulo} />}

          {aba === "separadores" && <Separadores token={user.token} consulta={consulta} rotulo={rotulo} />}

          {aba === "padroes" && <Padroes token={user.token} consulta={consulta} rotulo={rotulo}
            abrir={f => { setFiltroEnt(x => ({ f, versao: x.versao + 1 })); setAba("entregas"); }} />}

          {aba === "geral" && (<>
          {/* Pedidos do período (filtros + tabela) logo abaixo dos cartões */}
          <h2 className="mb-2 font-bold">Pedidos <span className="text-sm font-normal text-gray-500">· {rotulo}</span></h2>
          {/* Barra de filtros */}
          <div className="mb-2 flex flex-wrap items-center gap-3 rounded-xl bg-white p-3 text-sm shadow">
            <select value={fStatus} onChange={e => setFStatus(e.target.value)} className="rounded-lg bg-gray-100 px-2 py-2">
              <option value="">Todos os status</option>
              {STATUS.map(s => <option key={s.k} value={s.k}>{s.nome}</option>)}
            </select>
            <select value={fSep} onChange={e => setFSep(e.target.value)} className="rounded-lg bg-gray-100 px-2 py-2">
              <option value="">Todos os separadores</option>
              {[...new Set(resumo.pedidos.map(p => p.separador).filter(Boolean))].map(n => <option key={n}>{n}</option>)}
            </select>
            <select value={fEnt} onChange={e => setFEnt(e.target.value)} className="rounded-lg bg-gray-100 px-2 py-2">
              <option value="">Todos os entregadores</option>
              {[...new Set(resumo.pedidos.map(p => p.entregador).filter(Boolean))].map(n => <option key={n}>{n}</option>)}
            </select>
            <label className="flex items-center gap-1"><input type="checkbox" checked={soAtrasados} onChange={e => setSoAtrasados(e.target.checked)} /> Só atrasados</label>
            <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="Buscar pedido ou bairro" className="w-56 rounded-lg bg-gray-100 px-3 py-2 outline-none" />
            {(fStatus || fSep || fEnt || soAtrasados || busca) && <button onClick={() => { setFStatus(""); setFSep(""); setFEnt(""); setSoAtrasados(false); setBusca(""); }} className="text-blue-600 underline">Limpar</button>}
            <span className="ml-auto text-gray-500">{linhas.length} de {resumo.pedidos.length} pedidos</span>
          </div>

          {/* Tabela com os pedidos do período; clique no cabeçalho para ordenar */}
          <div className="overflow-x-auto rounded-xl bg-white shadow">
            <table className="w-full whitespace-nowrap text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr>
                  {([["numero", "Pedido"], ["data", "Data"], ["criado_em", "Hora"], ["status", "Status"], ["cliente", "Cliente / bairro"], ["itens", "Itens"], ["total", "Total R$"],
                    ["separador", "Separador"], ["entregador", "Entregador"], ["loja", "Loja"], ["rota", "Rota"], ["porta", "Porta"], ["total_seg", "Total tempo"]] as [Coluna, string][]).map(([c, nome]) => (
                    <th key={c} onClick={() => setOrdem(o => ({ col: c, asc: o.col === c ? !o.asc : true }))} className="cursor-pointer select-none px-3 py-2 hover:text-gray-900">
                      {nome}{ordem.col === c ? (ordem.asc ? " ▲" : " ▼") : ""}
                    </th>))}
                  <th className="px-3 py-2">No prazo</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map(p => (
                  <tr key={p.numero} className={`border-t ${p.atrasado ? "bg-red-50/50" : ""}`}>
                    <td className="px-3 py-2 font-semibold">{p.numero}</td>
                    <td className="px-3">{new Date(p.criado_em).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "America/Sao_Paulo" })}</td>
                    <td className="px-3">{new Date(p.criado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })}</td>
                    <td className="px-3">{ROTULO[p.status] ?? p.status}{p.decorrido != null && <span className="ml-1 text-xs text-gray-500">há {mmss(p.decorrido)}</span>}</td>
                    <td className="px-3">{p.cliente}{p.bairro ? ` · ${p.bairro}` : ""}</td>
                    <td className="px-3 text-center">{p.itens}</td>
                    <td className="px-3 text-right">{brl(p.total)}</td>
                    <td className="px-3">{p.separador ?? "—"}</td>
                    <td className="px-3">{p.entregador ?? "—"}</td>
                    <td className={`px-3 font-mono ${corCel(p.loja, METAS.loja)}`}>{mmss(p.loja)}</td>
                    <td className={`px-3 font-mono ${corCel(p.rota, METAS.rota)}`}>{mmss(p.rota)}</td>
                    <td className={`px-3 font-mono ${corCel(p.porta, METAS.porta)}`}>{mmss(p.porta)}</td>
                    <td className={`px-3 font-mono ${corCel(p.total_seg, METAS.total)}`}>{p.total_seg != null ? mmss(p.total_seg) : p.idade != null ? <span className="text-gray-400">{mmss(p.idade)}…</span> : "—"}</td>
                    <td className="px-3 text-center">{p.no_prazo == null ? (p.atrasado ? "⏰" : "—") : p.no_prazo ? "✅" : "⏰"}</td>
                  </tr>))}
                {!linhas.length && <tr><td colSpan={14} className="p-4 text-center text-gray-400">Nenhum pedido com esses filtros.</td></tr>}
              </tbody>
              {/* Rodapé: médias do conjunto filtrado */}
              {linhas.length > 0 && (
                <tfoot className="border-t-2 bg-gray-50 font-semibold">
                  <tr>
                    <td className="px-3 py-2" colSpan={5}>Média ({linhas.length})</td>
                    <td className="px-3 text-center">{(linhas.reduce((a, p) => a + p.itens, 0) / linhas.length).toFixed(1)}</td>
                    <td className="px-3 text-right">{brl(linhas.reduce((a, p) => a + Number(p.total), 0) / linhas.length)}</td>
                    <td colSpan={2} />
                    {(["loja", "rota", "porta", "total_seg"] as const).map(k => { const v = media(linhas.map(p => p[k])); const meta = METAS[k === "total_seg" ? "total" : k];
                      return <td key={k} className={`px-3 font-mono ${corCel(v, meta)}`}>{mmss(v)}</td>; })}
                    <td className="px-3 text-center">{(() => { const e = linhas.filter(p => p.no_prazo != null); return e.length ? `${Math.round(100 * e.filter(p => p.no_prazo).length / e.length)}%` : "—"; })()}</td>
                  </tr>
                </tfoot>)}
            </table>
          </div>
          </>)}

          {/* Aba Entregadores: desempenho de cada entregador no período */}
          {aba === "entregadores" && (<>
          {/* Entregadores: desempenho de cada um no período (clique no cabeçalho para ordenar) */}
          <h2 className="mb-2 font-bold">Entregadores <span className="text-sm font-normal text-gray-500">· {rotulo}</span></h2>
          <div className="mb-4 overflow-x-auto rounded-xl bg-white shadow">
            <table className="w-full whitespace-nowrap text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr>
                  {([["nome", "Entregador"], ["entregas", "Entregas"], ["rota", "Rota média"], ["porta", "Porta média"], ["total", "Total médio"],
                    ["atrasos", "Atrasos"], ["no_prazo_pct", "No prazo"], ["distancia_km", "Distância"]] as [ColEnt, string][]).map(([c, nome]) => (
                    <th key={c} onClick={() => setOrdemEnt(o => ({ col: c, asc: o.col === c ? !o.asc : c === "nome" }))} className="cursor-pointer select-none px-3 py-2 hover:text-gray-900">
                      {nome}{ordemEnt.col === c ? (ordemEnt.asc ? " ▲" : " ▼") : ""}
                    </th>))}
                  <th className="px-3 py-2">Agora</th>
                </tr>
              </thead>
              <tbody>
                {[...resumo.entregadores].sort((a, b) => {
                  const x = a[ordemEnt.col], y = b[ordemEnt.col];
                  if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; // vazios no fim
                  return (x < y ? -1 : x > y ? 1 : 0) * (ordemEnt.asc ? 1 : -1);
                }).map(e => (
                  <tr key={e.matricula} className="border-t">
                    <td className="px-3 py-2 font-semibold">{e.nome} <span className="text-xs font-normal text-gray-400">{e.matricula}</span></td>
                    <td className="px-3 text-center">{e.entregas}</td>
                    <td className={`px-3 font-mono ${corCel(e.rota, METAS.rota)}`}>{mmss(e.rota)}</td>
                    <td className={`px-3 font-mono ${corCel(e.porta, METAS.porta)}`}>{mmss(e.porta)}</td>
                    <td className={`px-3 font-mono ${corCel(e.total, METAS.total)}`}>{mmss(e.total)}</td>
                    <td className={`px-3 text-center ${e.atrasos ? "font-bold text-red-700" : ""}`}>{e.atrasos}</td>
                    <td className="px-3">{e.no_prazo_pct == null ? "—" : `${e.no_prazo_pct}%`}</td>
                    <td className="px-3">{e.distancia_km == null ? "—" : `${e.distancia_km.toLocaleString("pt-BR")} km`}</td>
                    <td className="px-3">{e.pedido_atual
                      ? <span className="rounded-full bg-purple-100 px-2 py-0.5 text-purple-800">🛵 em rota · {e.pedido_atual}</span>
                      : <span className="rounded-full bg-green-100 px-2 py-0.5 text-green-800">disponível</span>}</td>
                  </tr>))}
                {!resumo.entregadores.length && <tr><td colSpan={9} className="p-4 text-center text-gray-400">Nenhum entregador cadastrado.</td></tr>}
              </tbody>
            </table>
          </div>

          </>)}
        </>)}
      </div>
    </main>);
}
