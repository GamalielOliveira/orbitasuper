"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const itens = [
  { href: "/", label: "Início", icon: "⌂" },
  { href: "/categorias", label: "Categorias", icon: "▦" },
  { href: "/busca", label: "Busca", icon: "⌕" },
  { href: "/pedidos", label: "Pedidos", icon: "▤" },
  { href: "/menu", label: "Menu", icon: "☺" },
];

export default function BarraInferior({ qtd = 0 }: { qtd?: number }) {
  const p = usePathname();
  if (p.startsWith("/separacao") || p.startsWith("/entrega")) return null;
  return (
    <nav className="fixed bottom-3 left-1/2 z-40 flex w-[95%] max-w-md -translate-x-1/2 overflow-hidden rounded-2xl bg-blue-600 text-white shadow-lg">
      {itens.map((i) => (
        <Link key={i.href} href={i.href}
          className={`flex flex-1 flex-col items-center py-2 text-xs ${p === i.href ? "text-yellow-300" : ""}`}>
          <span className="text-xl">{i.icon}</span>{i.label}
        </Link>
      ))}
      <Link href="/sacola" className="relative flex flex-1 flex-col items-center bg-yellow-400 py-2 text-xs text-blue-800">
        <span className="text-xl">🛍</span>Sacola
        {qtd > 0 && <span className="absolute right-3 top-1 rounded-md bg-blue-600 px-1.5 text-white">{qtd}</span>}
      </Link>
    </nav>
  );
}