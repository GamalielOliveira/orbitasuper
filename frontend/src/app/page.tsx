"use client";
// Loja do cliente: só abre com login. Sem sessão -> /login.
// (Antes o catálogo era buscado no servidor do Next, sem token; agora é no navegador, com token.)
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Catalogo from "./Catalogo";
import { api, lerSessao } from "./sessao";

export default function Home() {
  const router = useRouter();
  const [produtos, setProdutos] = useState<Parameters<typeof Catalogo>[0]["inicial"] | null>(null);
  useEffect(() => {
    if (!lerSessao()) { router.replace("/login"); return; }
    api("/produtos", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(d => d && setProdutos(d));
  }, [router]);
  if (!produtos) return <main className="flex min-h-screen items-center justify-center text-gray-400">Carregando…</main>;
  return <Catalogo inicial={produtos} />;
}
