"use client";
import { useEffect, useState } from "react";

const API = "http://localhost:8000";
type Ped = { numero: string; status: string; endereco: string; total: string; loja_seg: number | null; rota_seg: number | null; total_seg: number | null };
type Pos = { lat: number; lon: number; velocidade_kmh: number; atualizado: string };

const fmt = (s: number | null) => s == null ? "—" : s >= 3600 ? `${Math.floor(s / 3600)}h${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}` : `${Math.floor(s / 60)}min ${s % 60}s`;

export default function Entrega() {
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [ped, setPed] = useState<Ped | null>(null);
  const [prontos, setProntos] = useState(0);
  const [pos, setPos] = useState<Pos | null>(null);
  const [placar, setPlacar] = useState<Ped | null>(null);
  const [agora, setAgora] = useState(Date.now());
  const [saiu, setSaiu] = useState<number | null>(null);

  const h = () => ({ Authorization: `Bearer ${user!.token}` });
  async function atualizar() {
    if (!user) return;
    const r = await fetch(`${API}/entrega/minha`, { headers: h() });
    if (r.ok) { const d = await r.json(); setPed(d.pedido); setProntos(d.prontos_na_loja); }
  }
  useEffect(() => { atualizar(); const t = setInterval(atualizar, 5000); return () => clearInterval(t); }, [user]);
  useEffect(() => { const t = setInterval(() => setAgora(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!ped) { setPos(null); return; }
    const buscar = async () => { const r = await fetch(`${API}/entrega/${ped.numero}/posicao`); if (r.ok) setPos(await r.json()); };
    buscar(); const t = setInterval(buscar, 10000); return () => clearInterval(t);
  }, [ped?.numero]);

  async function entrar() {
    const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matricula: mat, pin }) });
    const d = await r.json();
    if (!r.ok) return setErro(d.detail);
    if (d.funcao === "separador") return setErro("Esta área é só para entregadores.");
    setUser({ token: d.token, nome: d.nome }); setErro("");
  }
  async function acao(caminho: string) {
    const r = await fetch(`${API}${caminho}`, { method: "POST", headers: h() });
    const d = await r.json();
    if (!r.ok) return setErro(d.detail);
    setErro("");
    if (d.status === "a_caminho") setSaiu(Date.now());
    if (d.status === "entregue") { setPlacar(d); setPed(null); setSaiu(null); }
    else setPed(d);
    atualizar();
  }

  if (!user) return (
    <main className="flex min-h-screen items-center justify-center bg-green-800 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">daki</p>
        <p className="mb-5 text-sm text-gray-500">Área do colaborador · Entrega 🛵</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Matrícula" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} placeholder="PIN" type="password" maxLength={4} className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-green-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);

  const d = 0.004;
  return (
    <main className="mx-auto min-h-screen max-w-md bg-gray-100 p-4 text-gray-900">
      <header className="mb-4 flex items-center justify-between rounded-xl bg-green-800 px-4 py-3 text-white">
        <span className="font-bold">🛵 {user.nome}</span>
        <button onClick={() => setUser(null)} className="text-sm underline">Sair</button>
      </header>
      {erro && <p className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{erro}</p>}

      {placar && (
        <div className="mb-4 rounded-xl bg-white p-4 shadow">
          <p className="mb-2 text-lg font-bold text-green-700">✅ {placar.numero} entregue!</p>
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div className="rounded-lg bg-gray-50 p-2"><p className="text-gray-500">Loja</p><p className="font-bold">{fmt(placar.loja_seg)}</p></div>
            <div className="rounded-lg bg-gray-50 p-2"><p className="text-gray-500">Rota</p><p className="font-bold">{fmt(placar.rota_seg)}</p></div>
            <div className="rounded-lg bg-gray-50 p-2"><p className="text-gray-500">Clique→porta</p><p className="font-bold">{fmt(placar.total_seg)}</p></div>
          </div>
        </div>)}

      {!ped ? (
        <div className="rounded-xl bg-white p-6 text-center shadow">
          <p className="mb-1 text-4xl">📦</p>
          <p className="mb-4 text-gray-600">{prontos} pedido(s) pronto(s) na loja</p>
          <button onClick={() => { setPlacar(null); acao("/entrega/pegar"); }} disabled={!prontos}
            className="w-full rounded-xl bg-green-600 py-4 text-lg font-bold text-white transition active:scale-95 disabled:bg-gray-300">Pegar entrega</button>
        </div>
      ) : (
        <div className="rounded-xl bg-white p-4 shadow">
          <p className="text-sm text-gray-500">Pedido</p>
          <p className="text-2xl font-bold">{ped.numero}</p>
          <p className="mt-2 text-sm">📍 {ped.endereco}</p>
          <p className="mb-3 text-sm text-gray-500">Valor R$ {Number(ped.total).toFixed(2).replace(".", ",")} · já pago</p>

          {pos ? (
            <>
              <iframe className="mb-2 h-56 w-full rounded-lg border"
                src={`https://www.openstreetmap.org/export/embed.html?bbox=${pos.lon - d},${pos.lat - d},${pos.lon + d},${pos.lat + d}&layer=mapnik&marker=${pos.lat},${pos.lon}`} />
              <p className="mb-3 text-xs text-gray-500">GPS atualizado {new Date(pos.atualizado).toLocaleTimeString("pt-BR")} · {pos.velocidade_kmh} km/h</p>
            </>
          ) : <p className="mb-3 rounded-lg bg-yellow-50 p-2 text-xs text-yellow-800">Sem posição do GPS. Ligue o Traccar Client.</p>}

          {ped.status === "a_caminho" && saiu && (
            <p className="mb-3 text-center text-3xl font-bold text-green-700">⏱ {fmt(Math.floor((agora - saiu) / 1000))}</p>)}

          {ped.status === "atribuido" && (
            <button onClick={() => acao(`/entrega/${ped.numero}/retirei`)} className="w-full rounded-xl bg-blue-600 py-5 text-xl font-bold text-white transition active:scale-95">📦 Retirei o pedido</button>)}
          {ped.status === "a_caminho" && (
            <button onClick={() => acao(`/entrega/${ped.numero}/entreguei`)} className="w-full rounded-xl bg-green-600 py-5 text-xl font-bold text-white transition active:scale-95">✅ Entreguei</button>)}
        </div>
      )}
    </main>);
}
