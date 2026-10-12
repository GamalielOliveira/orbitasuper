"use client";
import { useEffect, useMemo, useState } from "react";
import Mapa, { type Pino } from "../Mapa";

const API = "/api";
type Ped = {
  numero: string; status: string; endereco: string | null; total: string; reembolso: string | null;
  rua: string | null; numero_end: string | null; complemento: string | null; bairro: string | null; cidade: string | null; uf: string | null; cep: string | null; referencia: string | null;
  lat: number | null; lon: number | null; loja_lat: number | null; loja_lon: number | null;
  loja_seg: number | null; rota_seg: number | null; porta_seg: number | null; total_seg: number | null;
  desde_saida_seg: number | null; desde_chegada_seg: number | null;
};
type Pos = { lat: number; lon: number; velocidade_kmh: number; atualizado: string };

const fmt = (s: number | null) => s == null ? "—" : s >= 3600 ? `${Math.floor(s / 3600)}h${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}` : `${Math.floor(s / 60)}min ${s % 60}s`;
const brl = (v: number | string) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function Entrega() {
  const [user, setUser] = useState<{ token: string; nome: string } | null>(null);
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  const [ped, setPed] = useState<Ped | null>(null);
  const [prontos, setProntos] = useState(0);
  const [pos, setPos] = useState<Pos | null>(null);
  const [placar, setPlacar] = useState<Ped | null>(null);
  const [agora, setAgora] = useState(Date.now());
  // cronômetro ancorado no relógio do servidor (sobrevive a recarga da página)
  const [saiu, setSaiu] = useState<number | null>(null);
  const [chegou, setChegou] = useState<number | null>(null);
  const ancorar = (d: Ped | null) => {
    setSaiu(d?.desde_saida_seg != null ? Date.now() - d.desde_saida_seg * 1000 : null);
    setChegou(d?.desde_chegada_seg != null ? Date.now() - d.desde_chegada_seg * 1000 : null);
  };

  const h = () => ({ Authorization: `Bearer ${user!.token}` });
  async function atualizar() {
    if (!user) return;
    const r = await fetch(`${API}/entrega/minha`, { headers: h() });
    if (r.ok) { const d = await r.json(); setPed(d.pedido); ancorar(d.pedido); setProntos(d.prontos_na_loja); }
    else if (r.status === 401) setUser(null);
  }
  useEffect(() => { atualizar(); const t = setInterval(atualizar, 5000); return () => clearInterval(t); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setInterval(() => setAgora(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!ped) { setPos(null); return; }
    const buscar = async () => { const r = await fetch(`${API}/entrega/${ped.numero}/posicao`); setPos(r.ok ? await r.json() : null); };
    buscar(); const t = setInterval(buscar, 10000); return () => clearInterval(t);
  }, [ped?.numero]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (d.status === "entregue") { setPlacar(d); setPed(null); ancorar(null); }
    else { setPed(d); ancorar(d); }
    atualizar();
  }

  const pinos = useMemo(() => {
    const l: Pino[] = [];
    if (ped?.loja_lat != null && ped.loja_lon != null) l.push({ lat: ped.loja_lat, lon: ped.loja_lon, cor: "#1e3a8a", rotulo: "Loja" });
    if (ped?.lat != null && ped.lon != null) l.push({ lat: Number(ped.lat), lon: Number(ped.lon), cor: "#dc2626", rotulo: "Cliente" });
    if (pos) l.push({ lat: pos.lat, lon: pos.lon, cor: "#16a34a", rotulo: "Você (GPS)" });
    return l;
  }, [ped?.loja_lat, ped?.loja_lon, ped?.lat, ped?.lon, pos]);

  if (!user) return (
    <main className="flex min-h-screen items-center justify-center bg-green-800 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">OrbitaSuper</p>
        <p className="mb-5 text-sm text-gray-500">Área do colaborador · Entrega 🛵</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Matrícula" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} placeholder="PIN" type="password" maxLength={4} className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-green-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);

  const linha1 = ped?.rua ? `${ped.rua}, ${ped.numero_end}${ped.complemento ? ` - ${ped.complemento}` : ""}` : ped?.endereco;
  const linha2 = ped?.rua ? `${ped.bairro} · ${ped.cidade}/${ped.uf}${ped.cep ? ` · CEP ${ped.cep}` : ""}` : null;
  const gmaps = ped?.lat != null && ped.lon != null ? `https://www.google.com/maps/dir/?api=1&destination=${ped.lat},${ped.lon}` : null;
  const seg = (t: number | null) => t == null ? null : Math.max(0, Math.floor((agora - t) / 1000));
  const etapa = ped?.status === "atribuido" ? "Retire na loja" : ped?.status === "a_caminho" ? "A caminho do cliente" : "Na porta do cliente";
  const botao = "w-full rounded-2xl py-6 text-2xl font-bold text-white shadow-lg transition active:scale-95";

  return (
    <main className="min-h-screen bg-gray-100 pb-6 text-gray-900">
      <header className="sticky top-0 z-[1000] bg-green-800 text-white">
        <div className="mx-auto flex max-w-[1232px] items-center justify-between px-4 py-3">
          <span className="truncate font-bold">🛵 {user.nome}</span>
          <span className="flex shrink-0 items-center gap-3 text-sm"><span>{prontos} na loja</span><button onClick={() => setUser(null)} className="underline">Sair</button></span>
        </div>
      </header>
      <div className="mx-auto max-w-[1232px] p-3 md:p-4">
        {erro && <p className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{erro}</p>}
        {placar && (
          <div className="mb-4 rounded-xl bg-white p-4 shadow">
            <p className="mb-2 text-lg font-bold text-green-700">✅ {placar.numero} entregue!</p>
            <div className="grid grid-cols-2 gap-2 text-center text-sm md:grid-cols-4">
              {([["Loja", placar.loja_seg], ["Rota", placar.rota_seg], ["Porta", placar.porta_seg], ["Total", placar.total_seg]] as const).map(([t, v]) => (
                <div key={t} className="rounded-lg bg-gray-50 p-2"><p className="text-gray-500">{t}</p><p className="text-lg font-bold">{fmt(v)}</p></div>))}
            </div>
          </div>)}

        {!ped ? (
          <div className="mx-auto max-w-lg rounded-xl bg-white p-6 text-center shadow md:p-8">
            <p className="mb-1 text-5xl">📦</p>
            <p className="mb-4 text-gray-600">{prontos} pedido(s) pronto(s) na loja</p>
            <button onClick={() => { setPlacar(null); acao("/entrega/pegar"); }} disabled={!prontos} className={`${botao} bg-green-600 disabled:bg-gray-300`}>Pegar entrega</button>
          </div>
        ) : (
          <div className="flex flex-col gap-3 md:grid md:grid-cols-[400px_1fr] md:gap-4">
            <div className="order-1 rounded-xl bg-white p-4 shadow md:p-5">
              <div className="flex items-baseline justify-between">
                <p className="text-3xl font-bold">{ped.numero}</p>
                <span className="rounded-full bg-green-100 px-3 py-1 text-sm font-semibold text-green-800">{etapa}</span>
              </div>
              {linha1 && (
                <div className="my-3 rounded-lg bg-gray-50 p-3">
                  <p className="text-lg font-semibold leading-snug">📍 {linha1}</p>
                  {linha2 && <p className="text-sm text-gray-600">{linha2}</p>}
                  {ped.referencia && <p className="mt-1 text-sm text-blue-800">Ref.: {ped.referencia}</p>}
                </div>)}
              {gmaps && <a href={gmaps} target="_blank" rel="noreferrer" className="mb-3 block rounded-xl border-2 border-blue-600 py-3 text-center text-lg font-semibold text-blue-700 active:bg-blue-50">🧭 Abrir no Google Maps</a>}
              <p className="mb-3 text-sm text-gray-500">Valor {brl(ped.total)} · já pago{Number(ped.reembolso) > 0 ? ` · reembolso ${brl(ped.reembolso!)}` : ""}</p>
              {ped.status === "a_caminho" && saiu && <p className="mb-3 text-center text-4xl font-bold text-green-700">⏱ {fmt(seg(saiu))}</p>}
              {ped.status === "chegou" && chegou && <p className="mb-3 text-center text-sm text-gray-600">Rota {fmt(saiu && chegou ? Math.floor((chegou - saiu) / 1000) : null)} · <b className="text-2xl text-orange-600">na porta ⏱ {fmt(seg(chegou))}</b></p>}
              {ped.status === "atribuido" && <button onClick={() => acao(`/entrega/${ped.numero}/retirei`)} className={`${botao} bg-blue-600`}>📦 Retirei o pedido</button>}
              {ped.status === "a_caminho" && <button onClick={() => acao(`/entrega/${ped.numero}/cheguei`)} className={`${botao} bg-orange-500`}>📍 Cheguei</button>}
              {ped.status === "chegou" && <button onClick={() => acao(`/entrega/${ped.numero}/entreguei`)} className={`${botao} bg-green-600`}>✅ Entreguei</button>}
            </div>
            <div className="order-2 rounded-xl bg-white p-2 shadow md:p-3">
              {pinos.length ? <Mapa pinos={pinos} className="h-[50vh] md:h-[600px]" /> :
                <div className="flex h-[50vh] items-center justify-center rounded-xl bg-gray-50 text-gray-500 md:h-[600px]">Pedido sem coordenadas e sem GPS.</div>}
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
                <span><b className="text-red-600">●</b> Cliente</span><span><b className="text-green-600">●</b> Você</span><span><b className="text-blue-900">●</b> Loja</span>
                <span className="md:ml-auto">{pos ? `GPS ${new Date(pos.atualizado).toLocaleTimeString("pt-BR")} · ${pos.velocidade_kmh} km/h` : "Sem GPS: ligue o Traccar Client"}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>);
}
