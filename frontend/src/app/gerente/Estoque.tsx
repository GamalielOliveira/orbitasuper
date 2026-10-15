"use client";
// Aba "Estoque": situação atual de cada produto (não depende do período).
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

const API = "/api";
type Sit = "vencido" | "zerado" | "baixo" | "vencendo" | "ok";
type Prod = { sku: string; nome: string; categoria: string; total: number; reservado: number; livre: number; minimo: number; lotes: number; validade: string | null; situacao: Sit };
type Dados = { cartoes: { zerados: number; abaixo_minimo: number; vencidos_un: number; vencidos_valor: number; vencendo: number }; produtos: Prod[] };
type Lote = { id: number; validade: string | null; entrada_em: string | null; quantidade: number; reservado: number; vencido: boolean };
type Mov = { id: number; hora: string; lote_id: number; tipo: string; campo: string; quantidade: number; saldo_quantidade: number; saldo_reservado: number; pedido: string | null; funcionario: string | null; motivo: string | null };
type Col = "nome" | "categoria" | "total" | "reservado" | "livre" | "minimo" | "lotes" | "validade" | "situacao";

const POR_PAGINA = 50;
const SIT: Record<Sit, [string, string]> = {   // rótulo e cor de cada situação
  vencido: ["Vencido", "bg-red-100 text-red-800"], zerado: ["Zerado", "bg-gray-800 text-white"],
  baixo: ["Baixo", "bg-orange-100 text-orange-800"], vencendo: ["Vencendo", "bg-yellow-100 text-yellow-800"], ok: ["OK", "bg-green-100 text-green-800"],
};
const ORDEM_SIT: Record<Sit, number> = { vencido: 0, zerado: 1, baixo: 2, vencendo: 3, ok: 4 };
const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
// Data de hoje em São Paulo no formato AAAA-MM-DD (para os campos de data)
const hojeSP = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
const dataBR = (d: string | null) => d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(2, 4)}` : "—";

function Cartao({ titulo, valor, sub, ruim }: { titulo: string; valor: string | number; sub?: string; ruim: boolean }) {
  return (
    <div className="rounded-xl bg-white p-3 shadow">
      <p className="text-xs text-gray-500">{titulo}</p>
      <p className={`text-xl font-bold ${ruim ? "text-red-700" : "text-slate-900"}`}>{valor}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>);
}

type Chamar = (caminho: string, metodo: string, corpo?: object) => Promise<Record<string, unknown> | null>;
const inp = "rounded border px-1.5 py-0.5 text-xs";
const btn = "rounded border px-2 py-0.5 text-xs font-semibold hover:bg-gray-100 disabled:opacity-40";

// Detalhe de um produto: lotes + ações + extrato (carrega quando a linha abre e após cada ação)
function Detalhe({ sku, token, minimo, chamar, versao }: { sku: string; token: string; minimo: number; chamar: Chamar; versao: number }) {
  const [d, setD] = useState<{ lotes: Lote[]; movimentacoes: Mov[] } | null>(null);
  const [ajuste, setAjuste] = useState<{ lote: number; contagem: string; motivo: string } | null>(null);   // lote com o form de inventário aberto
  const [hoje] = useState(hojeSP);   // lido uma vez ao abrir (não chamar Date durante o render)
  const [ent, setEnt] = useState({ quantidade: "", validade: "", entrada: hoje });
  const [edVal, setEdVal] = useState<{ lote: number; validade: string } | null>(null);   // lote com o form de validade aberto
  const [min, setMin] = useState(String(minimo));
  useEffect(() => {
    fetch(`${API}/gerente/estoque/${encodeURIComponent(sku)}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null).then(setD);
  }, [sku, token, versao]);
  if (!d) return <p className="text-xs text-gray-400">Carregando…</p>;
  const base = `/gerente/estoque/${encodeURIComponent(sku)}`;

  const darBaixa = (l: Lote) => {
    if (confirm(`Dar baixa de ${l.quantidade} un. do lote #${l.id} (vencido)? Isso registra perda.`)) chamar(`/gerente/estoque/lotes/${l.id}/baixa`, "POST");
  };
  const salvarAjuste = async () => {
    if (!ajuste) return;
    if (await chamar(`/gerente/estoque/lotes/${ajuste.lote}/ajuste`, "POST", { contagem: Number(ajuste.contagem), motivo: ajuste.motivo })) setAjuste(null);
  };
  const salvarEntrada = async () => {
    if (await chamar(`${base}/entrada`, "POST", { quantidade: Number(ent.quantidade), validade: ent.validade || null, entrada_em: ent.entrada || null }))
      setEnt({ quantidade: "", validade: "", entrada: hoje });
  };
  const salvarValidade = async () => {
    if (!edVal) return;
    if (await chamar(`/gerente/estoque/lotes/${edVal.lote}/validade`, "PATCH", { validade: edVal.validade || null })) setEdVal(null);
  };
  // datas no formato AAAA-MM-DD comparam certo como texto
  const valMin = ent.entrada > hoje ? ent.entrada : hoje;
  const valErro = ent.validade && ent.validade < ent.entrada ? "Validade antes da entrada" : ent.validade && ent.validade < hoje ? "Validade já passou" : "";
  const entErro = ent.entrada > hoje ? "Entrada no futuro" : "";

  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-4 lg:grid-cols-[minmax(500px,auto)_1fr]">   {/* gap-x-8: espaço entre Lotes e Extrato */}
      <div className="space-y-3">
        <div>
          <p className="mb-1 text-xs font-bold text-gray-600">Lotes</p>
          {/* [&_td]:px-2 = respiro de 8px em todas as células; min-w evita colunas espremidas */}
          <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] whitespace-nowrap text-xs [&_td]:px-2 [&_th]:px-2 [&_th]:py-1">
            <thead className="text-left text-gray-500"><tr><th>Lote</th><th>Entrada</th><th>Validade</th><th className="text-right">Qtd</th><th className="text-right">Reserv.</th><th /></tr></thead>
            <tbody>
              {d.lotes.map(l => (
                <Fragment key={l.id}>
                  <tr className={`border-t ${l.vencido && l.quantidade > 0 ? "font-semibold text-red-700" : ""}`}>
                    <td className="py-0.5">#{l.id}</td><td className="text-gray-500">{dataBR(l.entrada_em)}</td><td>{dataBR(l.validade)}{l.vencido ? " ⚠" : ""}</td>
                    <td className="text-right">{l.quantidade}</td><td className="text-right">{l.reservado}</td>
                    <td className="text-right"><div className="inline-flex gap-1.5">
                      {l.vencido && l.quantidade > 0 && <button onClick={() => darBaixa(l)} className={`${btn} border-red-300 text-red-700`}>Dar baixa</button>}
                      <button onClick={() => setEdVal(x => x?.lote === l.id ? null : { lote: l.id, validade: l.validade ?? "" })} className={btn}>Validade</button>
                      <button onClick={() => setAjuste(a => a?.lote === l.id ? null : { lote: l.id, contagem: String(l.quantidade), motivo: "" })} className={btn}>Ajustar</button>
                    </div></td>
                  </tr>
                  {/* Editar validade: fica no extrato como ajuste de 0 un. */}
                  {edVal?.lote === l.id && (
                    <tr><td colSpan={6} className="bg-white py-1">
                      <div className="flex flex-wrap items-center gap-1">
                        <span>Nova validade:</span>
                        <input type="date" min={l.entrada_em ?? undefined} value={edVal.validade} onChange={e => setEdVal({ ...edVal, validade: e.target.value })} className={inp} />
                        <button disabled={(edVal.validade || null) === l.validade || (!!l.entrada_em && !!edVal.validade && edVal.validade < l.entrada_em)} onClick={salvarValidade} className={btn}>Salvar</button>
                        {edVal.validade === hoje && <span className="text-yellow-700">⚠ vence hoje</span>}
                        {!!l.entrada_em && !!edVal.validade && edVal.validade < l.entrada_em && <span className="text-red-700">antes da entrada</span>}
                      </div>
                    </td></tr>)}
                  {/* Ajuste de inventário: informa a contagem física; a diferença vai pro extrato */}
                  {ajuste?.lote === l.id && (
                    <tr><td colSpan={6} className="bg-white py-1">
                      <div className="flex flex-wrap items-center gap-1">
                        <span>Contagem:</span>
                        <input type="number" min={l.reservado} value={ajuste.contagem} onChange={e => setAjuste({ ...ajuste, contagem: e.target.value })} className={`${inp} w-16`} />
                        <input value={ajuste.motivo} onChange={e => setAjuste({ ...ajuste, motivo: e.target.value })} placeholder="Motivo (obrigatório)" className={`${inp} flex-1`} />
                        <button disabled={ajuste.motivo.trim().length < 3 || ajuste.contagem === ""} onClick={salvarAjuste} className={btn}>Salvar</button>
                      </div>
                      {l.reservado > 0 && <p className="text-[10px] text-gray-400">Mínimo {l.reservado} (reservado para pedidos em aberto)</p>}
                    </td></tr>)}
                </Fragment>))}
            </tbody>
          </table>
          </div>
        </div>
        {/* Entrada de mercadoria: cria um lote novo */}
        <div className="rounded border bg-white p-2 text-xs">
          <p className="mb-1 font-bold text-gray-600">Entrada de mercadoria</p>
          <div className="flex flex-wrap items-center gap-1">
            <input type="number" min={1} value={ent.quantidade} onChange={e => setEnt({ ...ent, quantidade: e.target.value })} placeholder="Qtd" className={`${inp} w-16`} />
            <label className="flex items-center gap-1">Entrada
              <input type="date" max={hoje} value={ent.entrada} onChange={e => setEnt({ ...ent, entrada: e.target.value })} className={inp} /></label>
            <label className="flex items-center gap-1">Validade
              <input type="date" min={valMin} value={ent.validade} onChange={e => setEnt({ ...ent, validade: e.target.value })} className={inp} title="opcional" /></label>
            <button disabled={!(Number(ent.quantidade) > 0) || !ent.entrada || !!valErro || !!entErro} onClick={salvarEntrada} className={btn}>Registrar</button>
          </div>
          {(valErro || entErro) && <p className="mt-1 text-red-700">{entErro || valErro}</p>}
          {!valErro && ent.validade === hoje && <p className="mt-1 text-yellow-700">⚠ Validade é hoje: o lote vence amanhã e não poderá mais ser vendido.</p>}
        </div>
        {/* Estoque mínimo: abaixo disso aparece como "baixo" */}
        <div className="flex items-center gap-1 text-xs">
          <span className="font-bold text-gray-600">Estoque mínimo:</span>
          <input type="number" min={0} value={min} onChange={e => setMin(e.target.value)} className={`${inp} w-16`} />
          <button disabled={min === "" || Number(min) === minimo} onClick={() => chamar(`${base}/minimo`, "PATCH", { minimo: Number(min) })} className={btn}>Salvar</button>
        </div>
      </div>
      <div>
        <p className="mb-1 text-xs font-bold text-gray-600">Extrato (últimas 50)</p>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full whitespace-nowrap text-xs [&_td]:px-2 [&_th]:px-2 [&_th]:py-1">
            <thead className="sticky top-0 bg-gray-50 text-left text-gray-500"><tr><th>Hora</th><th>Lote</th><th>Tipo</th><th className="text-right">Qtd</th><th className="text-right">Saldo</th><th className="text-right">Reserv.</th><th className="pl-2">Pedido</th><th>Func.</th><th>Motivo</th></tr></thead>
            <tbody>
              {d.movimentacoes.map(m => (
                <tr key={m.id} className="border-t">
                  <td className="py-0.5">{m.hora}</td><td>#{m.lote_id}</td><td>{m.tipo}</td>
                  <td className={`text-right font-mono ${m.quantidade < 0 ? "text-red-700" : "text-green-700"}`}>{m.quantidade > 0 ? "+" : ""}{m.quantidade}{m.campo === "reservado" ? " r" : ""}</td>
                  <td className="text-right">{m.saldo_quantidade}</td><td className="text-right">{m.saldo_reservado}</td>
                  <td className="pl-2">{m.pedido ?? "—"}</td><td>{m.funcionario ?? "—"}</td>
                  <td className="max-w-48 truncate" title={m.motivo ?? ""}>{m.motivo ?? ""}</td>
                </tr>))}
              {!d.movimentacoes.length && <tr><td colSpan={9} className="text-gray-400">Sem movimentações.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="mt-1 text-[10px] text-gray-400">&quot;r&quot; = mexeu na reserva (não no estoque físico)</p>
      </div>
    </div>);
}

export default function Estoque({ token }: { token: string }) {
  const [d, setD] = useState<Dados | null>(null);
  const [cat, setCat] = useState("");
  const [sit, setSit] = useState<"" | Sit>("");
  const [busca, setBusca] = useState("");
  const [todos, setTodos] = useState(false);   // por padrão só mostra o que precisa de atenção
  const [pag, setPag] = useState(0);
  const [ordem, setOrdem] = useState<{ col: Col; asc: boolean }>({ col: "situacao", asc: true });
  const [aberto, setAberto] = useState<string | null>(null);
  const [toast, setToast] = useState<{ txt: string; erro: boolean } | null>(null);
  const [versao, setVersao] = useState(0);   // muda após cada ação para recarregar o detalhe

  const carregar = useCallback(async () => {
    const r = await fetch(`${API}/gerente/estoque`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) setD(await r.json());
  }, [token]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 60000); return () => clearInterval(t); }, [carregar]);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 5000); return () => clearTimeout(t); }, [toast]);

  // Chama uma ação do gerente; mostra aviso e recarrega tudo se deu certo
  const chamar: Chamar = useCallback(async (caminho, metodo, corpo) => {
    const r = await fetch(`${API}${caminho}`, { method: metodo, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: corpo ? JSON.stringify(corpo) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const det = Array.isArray(j.detail) ? "Dados inválidos" : (j.detail ?? `Erro ${r.status}`);
      setToast({ txt: det, erro: true }); return null;
    }
    setToast({ txt: "Feito ✔", erro: false }); setVersao(v => v + 1); carregar();
    return j;
  }, [token, carregar]);

  const baixarTodos = async () => {
    if (!confirm("Dar baixa (perda) em TODOS os lotes vencidos? Lotes com reserva serão pulados.")) return;
    const j = await chamar("/gerente/estoque/baixar-vencidos", "POST");
    if (j) {
      const pulados = (j.pulados as string[]) ?? [];
      setToast({ txt: `${j.lotes} lote(s), ${j.unidades} un. baixadas${pulados.length ? ` · pulados: ${pulados.join("; ")}` : ""}`, erro: pulados.length > 0 });
    }
  };

  const categorias = useMemo(() => d ? [...new Set(d.produtos.map(p => p.categoria))].sort() : [], [d]);
  const filtrados = useMemo(() => {
    if (!d) return [];
    const b = busca.trim().toLowerCase();
    const lista = d.produtos.filter(p =>
      (todos || sit || p.situacao !== "ok") && (!sit || p.situacao === sit) && (!cat || p.categoria === cat) &&
      (!b || p.nome.toLowerCase().includes(b) || p.sku.toLowerCase().includes(b)));
    const val = (p: Prod) => ordem.col === "situacao" ? ORDEM_SIT[p.situacao] : p[ordem.col];
    return lista.sort((a, x) => {
      const p = val(a), q = val(x);
      if (p == null && q == null) return 0; if (p == null) return 1; if (q == null) return -1;
      return (p < q ? -1 : p > q ? 1 : 0) * (ordem.asc ? 1 : -1);
    });
  }, [d, busca, todos, sit, cat, ordem]);

  if (!d) return <p className="text-gray-500">Carregando…</p>;
  const k = d.cartoes;
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
  const p0 = Math.min(pag, paginas - 1);
  const pagina = filtrados.slice(p0 * POR_PAGINA, (p0 + 1) * POR_PAGINA);
  const mudou = <T,>(f: (v: T) => void) => (v: T) => { f(v); setPag(0); setAberto(null); };   // filtro mudou: volta à página 1
  const cab: [Col, string][] = [["nome", "Produto"], ["categoria", "Categoria"], ["total", "Total"], ["reservado", "Reserv."], ["livre", "Livre"],
    ["minimo", "Mín."], ["lotes", "Lotes"], ["validade", "Validade"], ["situacao", "Situação"]];

  return (
    <div className="space-y-4">
      {/* Aviso rápido (some sozinho) */}
      {toast && <div className={`fixed bottom-4 right-4 z-50 max-w-md rounded-lg px-4 py-2 text-sm text-white shadow-lg ${toast.erro ? "bg-red-700" : "bg-green-700"}`}>{toast.txt}</div>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Cartao titulo="Zerados" valor={k.zerados} ruim={k.zerados > 0} sub="sem saldo livre" />
        <Cartao titulo="Abaixo do mínimo" valor={k.abaixo_minimo} ruim={k.abaixo_minimo > 0} />
        <div className="relative">
          <Cartao titulo="Lotes vencidos" valor={`${k.vencidos_un} un.`} sub={brl(k.vencidos_valor)} ruim={k.vencidos_un > 0} />
          {k.vencidos_un > 0 && <button onClick={baixarTodos} className="absolute right-2 top-2 rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white hover:bg-red-700">Baixar todos vencidos</button>}
        </div>
        <Cartao titulo="Vencendo em 3 dias" valor={k.vencendo} sub="produtos" ruim={k.vencendo > 0} />
      </div>

      <div className="rounded-xl bg-white shadow">
        {/* Filtros */}
        <div className="flex flex-wrap items-center gap-2 border-b p-3 text-sm">
          <input value={busca} onChange={e => mudou(setBusca)(e.target.value)} placeholder="Buscar nome ou SKU" className="w-56 rounded border px-2 py-1" />
          <select value={cat} onChange={e => mudou(setCat)(e.target.value)} className="rounded border px-2 py-1">
            <option value="">Todas as categorias</option>
            {categorias.map(c => <option key={c}>{c}</option>)}
          </select>
          <select value={sit} onChange={e => mudou(setSit)(e.target.value as "" | Sit)} className="rounded border px-2 py-1">
            <option value="">Todas as situações</option>
            {(Object.keys(SIT) as Sit[]).map(s => <option key={s} value={s}>{SIT[s][0]}</option>)}
          </select>
          <label className="flex items-center gap-1"><input type="checkbox" checked={todos} onChange={e => mudou(setTodos)(e.target.checked)} /> mostrar todos (inclui OK)</label>
          <span className="ml-auto text-gray-500">{filtrados.length} produto(s)</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>{cab.map(([c, nome]) => (
                <th key={c} onClick={() => setOrdem(o => ({ col: c, asc: o.col === c ? !o.asc : true }))} className="cursor-pointer select-none px-3 py-2 hover:text-gray-900">
                  {nome}{ordem.col === c ? (ordem.asc ? " ▲" : " ▼") : ""}
                </th>))}</tr>
            </thead>
            <tbody>
              {pagina.map(p => (
                <Fragment key={p.sku}>
                  <tr onClick={() => setAberto(a => a === p.sku ? null : p.sku)} className={`cursor-pointer border-t hover:bg-blue-50 ${aberto === p.sku ? "bg-blue-50" : ""}`}>
                    <td className="max-w-72 truncate px-3 py-1.5" title={p.sku}>{aberto === p.sku ? "▾" : "▸"} {p.nome} <span className="text-xs text-gray-400">{p.sku}</span></td>
                    <td className="px-3 text-gray-600">{p.categoria}</td>
                    <td className="px-3 text-right">{p.total}</td>
                    <td className="px-3 text-right">{p.reservado}</td>
                    <td className={`px-3 text-right font-semibold ${p.livre < p.minimo ? "text-red-700" : ""}`}>{p.livre}</td>
                    <td className="px-3 text-right text-gray-500">{p.minimo}</td>
                    <td className="px-3 text-center">{p.lotes}</td>
                    <td className="px-3">{dataBR(p.validade)}</td>
                    <td className="px-3"><span className={`rounded-full px-2 py-0.5 text-xs ${SIT[p.situacao][1]}`}>{SIT[p.situacao][0]}</span></td>
                  </tr>
                  {aberto === p.sku && <tr><td colSpan={9} className="bg-gray-50 px-6 py-3"><Detalhe key={p.sku} sku={p.sku} token={token} minimo={p.minimo} chamar={chamar} versao={versao} /></td></tr>}
                </Fragment>))}
              {!pagina.length && <tr><td colSpan={9} className="p-4 text-center text-gray-400">{todos || sit ? "Nada encontrado." : "Tudo OK por aqui. 🎉 Marque “mostrar todos” para ver o estoque inteiro."}</td></tr>}
            </tbody>
          </table>
        </div>

        {/* Paginação: 50 por página (são ~3000 produtos) */}
        {paginas > 1 && (
          <div className="flex items-center justify-end gap-2 border-t p-2 text-sm">
            <button disabled={p0 === 0} onClick={() => { setPag(p0 - 1); setAberto(null); }} className="rounded border px-2 disabled:opacity-40">‹</button>
            <span>página {p0 + 1} de {paginas}</span>
            <button disabled={p0 >= paginas - 1} onClick={() => { setPag(p0 + 1); setAberto(null); }} className="rounded border px-2 disabled:opacity-40">›</button>
          </div>)}
      </div>
    </div>);
}
