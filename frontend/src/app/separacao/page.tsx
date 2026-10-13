"use client";
import { useCallback, useEffect, useState } from "react";
import Foto from "../Foto";

const API = "/api";
type Item = { id: number; sku: string; nome: string; corredor: number; imagem_url: string | null; quantidade: number; lote: number; validade: string | null };
type Sub = { sku: string; nome: string; imagem_url: string | null; preco: string; estoque: number };
type Escolha = { status: "separado" | "faltando" | "substituido"; substituto_sku?: string; substituto_nome?: string };
type Card = { numero: string; itens: number; total: string; separador: string | null; entregador: string | null; status: string; etapa_seg: number; desde_criado_seg: number };
type Quadro = { pagos: Card[]; em_separacao: Card[]; prontos: Card[]; em_rota: Card[] };

const brl = (v: number | string) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (s: number) => s >= 3600 ? `${Math.floor(s / 3600)}h${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
// metas por etapa (segundos): acima de meta fica amarelo, acima do dobro fica vermelho
const META: Record<keyof Quadro, number> = { pagos: 120, em_separacao: 300, prontos: 180, em_rota: 1200 };
const cor = (s: number, m: number) => s > 2 * m ? "bg-red-100 text-red-700" : s > m ? "bg-yellow-100 text-yellow-800" : "bg-green-100 text-green-700";

export default function Separacao() {
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [quadro, setQuadro] = useState<Quadro>({ pagos: [], em_separacao: [], prontos: [], em_rota: [] });
  const [pedido, setPedido] = useState<{ numero: string; itens: Item[] } | null>(null);
  const [esc, setEsc] = useState<Record<number, Escolha>>({});
  const [atual, setAtual] = useState(0);
  const [subs, setSubs] = useState<{ item: number; lista: Sub[] } | null>(null);
  const [msg, setMsg] = useState("");
  const [inicio, setInicio] = useState<number | null>(null);
  const [agora, setAgora] = useState(0); // relógio: preenchido só no navegador (useEffect abaixo)

  const h = useCallback(() => ({ Authorization: `Bearer ${user?.token}`, "Content-Type": "application/json" }), [user]);
  const carregar = useCallback(async () => {
    if (!user) return;
    const r = await fetch(`${API}/operacao/quadro`, { headers: h() });
    if (r.ok) setQuadro(await r.json()); else if (r.status === 401) setUser(null);
  }, [user, h]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 5000); return () => clearInterval(t); }, [carregar]);
  useEffect(() => { setAgora(Date.now()); const t = setInterval(() => setAgora(Date.now()), 1000); return () => clearInterval(t); }, []);

  async function entrar() {
    const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matricula: mat, pin }) });
    const d = await r.json();
    if (!r.ok) return setErro(d.detail);
    if (d.funcao === "entregador") return setErro("Esta área é só para separadores.");
    setUser({ token: d.token, nome: d.nome }); setErro("");
  }
  async function pegar() {
    const r = await fetch(`${API}/separacao/pegar`, { method: "POST", headers: h() });
    const d = await r.json(); if (!r.ok) return setMsg(d.detail);
    setPedido(d); setEsc({}); setAtual(0); setMsg(""); setInicio(Date.now()); carregar();
  }
  const marcar = useCallback((idx: number, e: Escolha) => {
    if (!pedido) return;
    const novo = { ...esc, [pedido.itens[idx].id]: e };
    setEsc(novo);
    const prox = pedido.itens.findIndex((it, i) => i > idx && !novo[it.id]);
    const qualquer = pedido.itens.findIndex(it => !novo[it.id]);
    setAtual(prox >= 0 ? prox : qualquer >= 0 ? qualquer : idx);
  }, [pedido, esc]);
  const abrirSubs = useCallback(async (idx: number) => {
    if (!pedido) return;
    const item = pedido.itens[idx]; setAtual(idx);
    const r = await fetch(`${API}/separacao/substitutos/${encodeURIComponent(item.sku)}`, { headers: h() });
    setSubs({ item: idx, lista: r.ok ? await r.json() : [] });
  }, [pedido, h]);
  async function concluir() {
    if (!pedido) return;
    const corpo = pedido.itens.map(i => ({ id: i.id, status: esc[i.id].status, substituto_sku: esc[i.id].substituto_sku }));
    const r = await fetch(`${API}/separacao/${pedido.numero}/concluir`, { method: "POST", headers: h(), body: JSON.stringify(corpo) });
    const d = await r.json();
    setMsg(r.ok ? `✅ ${d.numero} pronto para entrega · total ${brl(d.total)}${Number(d.reembolso) > 0 ? ` · reembolso ${brl(d.reembolso)}` : ""}${d.faltas ? ` · ${d.faltas} falta(s)` : ""}` : `❌ ${d.detail}`);
    setPedido(null); setInicio(null); carregar();
  }

  // atalhos: S separado, F faltando, R substituir, 1-5 escolhe substituto, Esc fecha, setas navegam
  useEffect(() => {
    if (!pedido) return;
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.target as HTMLElement)?.tagName === "INPUT") return;
      const k = ev.key.toLowerCase();
      if (subs) {
        if (k === "escape") setSubs(null);
        const n = Number(k);
        if (n >= 1 && n <= subs.lista.length) { const s = subs.lista[n - 1]; marcar(subs.item, { status: "substituido", substituto_sku: s.sku, substituto_nome: s.nome }); setSubs(null); }
        return;
      }
      if (k === "s") marcar(atual, { status: "separado" });
      else if (k === "f") marcar(atual, { status: "faltando" });
      else if (k === "r") abrirSubs(atual);
      else if (k === "arrowdown") setAtual(a => Math.min(a + 1, pedido.itens.length - 1));
      else if (k === "arrowup") setAtual(a => Math.max(a - 1, 0));
      else return;
      ev.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pedido, subs, atual, marcar, abrirSubs]);

  if (!user) return (
    <main className="flex min-h-screen items-center justify-center bg-blue-900 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">OrbitaSuper</p>
        <p className="mb-5 text-sm text-gray-500">Área do colaborador · Separação</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Matrícula" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} placeholder="PIN" type="password" maxLength={4} className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);

  const feitos = pedido ? pedido.itens.filter(i => esc[i.id]).length : 0;
  const total = pedido?.itens.length || 0;
  const colunas: { k: keyof Quadro; titulo: string; topo: string }[] = [
    { k: "pagos", titulo: "Pagos · fila", topo: "border-blue-500" },
    { k: "em_separacao", titulo: "Em separação", topo: "border-yellow-500" },
    { k: "prontos", titulo: "Prontos", topo: "border-green-500" },
    { k: "em_rota", titulo: "Em rota", topo: "border-purple-500" }];

  return (
    <main className="min-h-screen bg-gray-100 text-gray-900">
      <header className="bg-blue-900 text-white">
        <div className="mx-auto flex max-w-[1232px] items-center justify-between px-4 py-3">
          <span className="font-bold">📦 OrbitaSuper · Separação · {user.nome}</span>
          <span className="flex items-center gap-4 text-sm">
            <span>Fila {quadro.pagos.length} · Separando {quadro.em_separacao.length} · Prontos {quadro.prontos.length} · Rota {quadro.em_rota.length}</span>
            <button onClick={() => { setUser(null); setPedido(null); }} className="underline">Sair</button>
          </span>
        </div>
      </header>
      <div className="mx-auto max-w-[1232px] p-4">
        {msg && <p className="mb-4 rounded-xl bg-white p-3 text-sm shadow">{msg}</p>}

        {!pedido ? (<>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-bold">Quadro da loja</h2>
            <button onClick={pegar} disabled={!quadro.pagos.length} className="rounded-xl bg-green-600 px-6 py-3 font-semibold text-white transition active:scale-95 disabled:bg-gray-300">Pegar próximo ▶</button>
          </div>
          <div className="grid grid-cols-4 gap-4">
            {colunas.map(c => (
              <section key={c.k} className={`min-h-[420px] rounded-xl border-t-4 bg-white p-3 shadow ${c.topo}`}>
                <h3 className="mb-3 flex justify-between font-bold"><span>{c.titulo}</span><span className="rounded-full bg-gray-100 px-2 text-sm">{quadro[c.k].length}</span></h3>
                {quadro[c.k].map((p, i) => (
                  <div key={p.numero} className={`mb-2 rounded-lg border p-3 text-sm ${c.k === "pagos" && i === 0 ? "ring-2 ring-green-400" : ""}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{p.numero}</span>
                      <span className={`rounded px-2 py-0.5 font-mono text-xs ${cor(p.etapa_seg, META[c.k])}`}>⏱ {fmt(p.etapa_seg)}</span>
                    </div>
                    <p className="mt-1 text-gray-500">{p.itens} itens · {brl(p.total)}</p>
                    {p.separador && c.k === "em_separacao" && <p className="text-xs text-yellow-800">👤 {p.separador}</p>}
                    {p.entregador && <p className="text-xs text-purple-800">🛵 {p.entregador}{p.status === "atribuido" ? " · aguardando retirada" : ""}</p>}
                  </div>))}
                {!quadro[c.k].length && <p className="text-sm text-gray-400">—</p>}
              </section>))}
          </div>
        </>) : (
          <div className="grid grid-cols-[1fr_300px] gap-4">
            <div className="space-y-3">
              {pedido.itens.map((i, idx) => {
                const e = esc[i.id];
                const borda = e?.status === "separado" ? "border-green-400 bg-green-50" : e?.status === "faltando" ? "border-red-400 bg-red-50" : e?.status === "substituido" ? "border-yellow-400 bg-yellow-50" : "border-gray-200 bg-white";
                return (
                  <div key={i.id} onClick={() => setAtual(idx)} className={`flex cursor-pointer items-center gap-4 rounded-xl border-2 p-3 shadow-sm ${borda} ${idx === atual ? "ring-4 ring-blue-400" : ""}`}>
                    <div className="flex h-[120px] w-[120px] shrink-0 items-center justify-center rounded-lg bg-white text-6xl"><Foto src={i.imagem_url} className="h-[120px] w-[120px]" /></div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="rounded-lg bg-blue-900 px-2 py-1 text-sm font-bold text-white">Corredor {i.corredor}</span>
                        <span className="rounded-lg bg-gray-900 px-2 py-1 text-sm font-bold text-white">{i.quantidade}x</span>
                      </div>
                      <p className="text-lg font-semibold leading-tight">{i.nome}</p>
                      <p className="text-xs text-gray-500">Lote #{i.lote}{i.validade ? ` · validade ${new Date(i.validade + "T12:00").toLocaleDateString("pt-BR")}` : ""} · {i.sku}</p>
                      {e?.status === "substituido" && <p className="text-sm font-semibold text-yellow-700">🔁 Substituído por {e.substituto_nome}</p>}
                    </div>
                    <div className="flex w-36 shrink-0 flex-col gap-2" onClick={ev => ev.stopPropagation()}>
                      <button onClick={() => marcar(idx, { status: "separado" })} className="rounded-lg bg-green-600 py-2 text-sm text-white active:scale-95">✔ Separado <kbd className="opacity-70">S</kbd></button>
                      <button onClick={() => marcar(idx, { status: "faltando" })} className="rounded-lg bg-red-600 py-2 text-sm text-white active:scale-95">✖ Faltando <kbd className="opacity-70">F</kbd></button>
                      <button onClick={() => abrirSubs(idx)} className="rounded-lg bg-yellow-500 py-2 text-sm text-white active:scale-95">🔁 Substituir <kbd className="opacity-70">R</kbd></button>
                    </div>
                  </div>);
              })}
            </div>
            <aside className="sticky top-4 h-fit rounded-xl bg-white p-4 shadow">
              <p className="text-sm text-gray-500">Separando</p>
              <p className="text-2xl font-bold">{pedido.numero}</p>
              {inicio && agora > 0 && <p className={`mt-2 inline-block rounded px-2 py-1 font-mono text-lg ${cor(Math.floor((agora - inicio) / 1000), META.em_separacao)}`}>⏱ {fmt(Math.floor((agora - inicio) / 1000))}</p>}
              <p className="mt-4 mb-1 text-sm font-semibold">{feitos}/{total} itens</p>
              <div className="h-3 overflow-hidden rounded-full bg-gray-200"><div className="h-full bg-green-500 transition-all" style={{ width: `${total ? feitos / total * 100 : 0}%` }} /></div>
              <button onClick={concluir} disabled={feitos < total} className="mt-4 w-full rounded-xl bg-blue-600 py-4 font-bold text-white transition active:scale-95 disabled:bg-gray-300">Concluir separação</button>
              <div className="mt-4 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
                <p className="mb-1 font-semibold">Atalhos (item destacado)</p>
                <p><kbd>S</kbd> separado · <kbd>F</kbd> faltando · <kbd>R</kbd> substituir</p>
                <p><kbd>↑</kbd><kbd>↓</kbd> muda item · <kbd>1-5</kbd> escolhe substituto · <kbd>Esc</kbd> fecha</p>
              </div>
            </aside>
          </div>
        )}
      </div>

      {subs && pedido && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setSubs(null)}>
          <div className="w-[560px] rounded-2xl bg-white p-5" onClick={e => e.stopPropagation()}>
            <h3 className="mb-1 font-bold">Substituto para {pedido.itens[subs.item].nome}</h3>
            <p className="mb-3 text-xs text-gray-500">Mesma subcategoria e conservação, preço mais próximo. Tecle 1-5.</p>
            {subs.lista.map((s, n) => (
              <button key={s.sku} onClick={() => { marcar(subs.item, { status: "substituido", substituto_sku: s.sku, substituto_nome: s.nome }); setSubs(null); }}
                className="mb-2 flex w-full items-center gap-3 rounded-lg border p-2 text-left transition hover:bg-yellow-50 active:scale-95">
                <span className="w-6 text-center font-bold text-gray-400">{n + 1}</span>
                <span className="flex h-16 w-16 shrink-0 items-center justify-center text-3xl"><Foto src={s.imagem_url} className="h-16 w-16" /></span>
                <span className="flex-1 text-sm">{s.nome}</span>
                <span className="text-right"><span className="block font-bold">{brl(s.preco)}</span><span className="text-xs text-green-600">{s.estoque} em estoque</span></span>
              </button>))}
            {!subs.lista.length && <p className="text-sm text-gray-500">Sem substituto com estoque. Marque como faltando (F).</p>}
          </div>
        </div>)}
    </main>);
}
