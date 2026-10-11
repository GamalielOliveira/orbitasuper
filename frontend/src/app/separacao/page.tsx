"use client";
import { useEffect, useState } from "react";

const API = "http://localhost:8000";
type Item = { id: number; sku: string; nome: string; corredor: number; imagem_url: string; quantidade: number; lote: number; validade: string | null };
type Sub = { sku: string; nome: string; imagem_url: string; estoque: number };
type Escolha = { status: "separado" | "faltando" | "substituido"; substituto_sku?: string };

export default function Separacao() {
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [fila, setFila] = useState<{ numero: string; itens: number; espera_seg: number }[]>([]);
  const [pedido, setPedido] = useState<{ numero: string; itens: Item[] } | null>(null);
  const [esc, setEsc] = useState<Record<number, Escolha>>({});
  const [subs, setSubs] = useState<{ item: number; lista: Sub[] } | null>(null);
  const [msg, setMsg] = useState("");

  const h = () => ({ Authorization: `Bearer ${user!.token}`, "Content-Type": "application/json" });
  const carregarFila = async () => { if (!user) return; const r = await fetch(`${API}/separacao/fila`, { headers: h() }); if (r.ok) setFila(await r.json()); };
  useEffect(() => { carregarFila(); const t = setInterval(carregarFila, 5000); return () => clearInterval(t); }, [user]);

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
    setPedido(d); setEsc({}); setMsg("");
  }
  async function abrirSubs(item: Item) {
    const r = await fetch(`${API}/separacao/substitutos/${item.sku}`, { headers: h() });
    setSubs({ item: item.id, lista: await r.json() });
  }
  async function concluir() {
    const corpo = pedido!.itens.map(i => ({ id: i.id, ...esc[i.id] }));
    const r = await fetch(`${API}/separacao/${pedido!.numero}/concluir`, { method: "POST", headers: h(), body: JSON.stringify(corpo) });
    const d = await r.json();
    setMsg(r.ok ? `✅ ${d.numero} pronto para entrega${d.faltas ? ` · ${d.faltas} item(ns) em falta` : ""}` : `❌ ${d.detail}`);
    setPedido(null); carregarFila();
  }
  const fmt = (s: number) => s >= 3600 ? `${Math.floor(s / 3600)}h${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}` : `${Math.floor(s / 60)} min`;
  const tudoMarcado = pedido && pedido.itens.every(i => esc[i.id]);

  if (!user) return (
    <main className="flex min-h-screen items-center justify-center bg-blue-900 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">daki</p>
        <p className="mb-5 text-sm text-gray-500">Área do colaborador · Separação</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Matrícula" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} placeholder="PIN" type="password" maxLength={4} className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);

  return (
    <main className="min-h-screen bg-gray-100 p-4 text-gray-900">
      <header className="mb-4 flex items-center justify-between rounded-xl bg-blue-900 px-4 py-3 text-white">
        <span className="font-bold">📦 Separação · {user.nome}</span>
        <button onClick={() => setUser(null)} className="text-sm underline">Sair</button>
      </header>
      {msg && <p className="mb-4 rounded-xl bg-white p-3 text-sm shadow">{msg}</p>}

      {!pedido ? (
        <div className="rounded-xl bg-white p-4 shadow">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-bold">Fila · {fila.length} pedido(s)</h2>
            <button onClick={pegar} disabled={!fila.length} className="rounded-xl bg-green-600 px-5 py-3 font-semibold text-white transition active:scale-95 disabled:bg-gray-300">Pegar próximo ▶</button>
          </div>
          {fila.map((f, i) => (
            <div key={f.numero} className={`mb-2 flex justify-between rounded-lg p-3 ${i === 0 ? "bg-green-50 ring-2 ring-green-400" : "bg-gray-50"}`}>
              <span className="font-semibold">{f.numero}</span><span>{f.itens} itens</span>
              <span className={f.espera_seg > 600 ? "font-bold text-red-600" : "text-gray-600"}>⏱ {fmt(f.espera_seg)}</span>
            </div>))}
          {!fila.length && <p className="text-gray-500">Nenhum pedido pago aguardando. 🎉</p>}
        </div>
      ) : (
        <div className="rounded-xl bg-white p-4 shadow">
          <h2 className="mb-3 text-lg font-bold">Separando {pedido.numero} · siga a ordem dos corredores</h2>
          {pedido.itens.map(i => {
            const e = esc[i.id];
            return (
              <div key={i.id} className={`mb-3 rounded-xl border-2 p-3 ${e?.status === "separado" ? "border-green-400 bg-green-50" : e?.status === "faltando" ? "border-red-400 bg-red-50" : e?.status === "substituido" ? "border-yellow-400 bg-yellow-50" : "border-gray-200"}`}>
                <div className="flex items-center gap-3">
                  <span className="rounded-lg bg-blue-900 px-2 py-1 text-xs font-bold text-white">C{i.corredor}</span>
                  <span className="text-3xl">{i.imagem_url}</span>
                  <div className="flex-1">
                    <p className="font-semibold">{i.quantidade}x {i.nome}</p>
                    <p className="text-xs text-gray-500">Lote #{i.lote}{i.validade ? ` · validade ${new Date(i.validade + "T12:00").toLocaleDateString("pt-BR")}` : ""}</p>
                    {e?.substituto_sku && <p className="text-xs font-semibold text-yellow-700">🔁 Substituído por {e.substituto_sku}</p>}
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <button onClick={() => setEsc({ ...esc, [i.id]: { status: "separado" } })} className="rounded-lg bg-green-600 py-2 text-sm text-white transition active:scale-95">✔ Separado</button>
                  <button onClick={() => setEsc({ ...esc, [i.id]: { status: "faltando" } })} className="rounded-lg bg-red-600 py-2 text-sm text-white transition active:scale-95">✖ Faltando</button>
                  <button onClick={() => abrirSubs(i)} className="rounded-lg bg-yellow-500 py-2 text-sm text-white transition active:scale-95">🔁 Substituir</button>
                </div>
              </div>);
          })}
          <button onClick={concluir} disabled={!tudoMarcado} className="mt-2 w-full rounded-xl bg-blue-600 py-4 font-bold text-white transition active:scale-95 disabled:bg-gray-300">Concluir separação</button>
        </div>
      )}

      {subs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setSubs(null)}>
          <div className="w-96 rounded-2xl bg-white p-5" onClick={e => e.stopPropagation()}>
            <h3 className="mb-3 font-bold">Escolha o substituto</h3>
            {subs.lista.map(s => (
              <button key={s.sku} onClick={() => { setEsc({ ...esc, [subs.item]: { status: "substituido", substituto_sku: s.sku } }); setSubs(null); }}
                className="mb-2 flex w-full items-center gap-3 rounded-lg border p-3 text-left transition hover:bg-yellow-50 active:scale-95">
                <span className="text-2xl">{s.imagem_url}</span><span className="flex-1">{s.nome}</span><span className="text-xs text-green-600">{s.estoque} em estoque</span>
              </button>))}
            {!subs.lista.length && <p className="text-sm text-gray-500">Sem substituto com estoque nesta categoria. Marque como faltando.</p>}
          </div>
        </div>)}
    </main>);
}
