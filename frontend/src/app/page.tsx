type Produto = { sku: string; nome: string; categoria: string; preco: string; estoque: number; proxima_validade: string | null };

export default async function Home() {
  const res = await fetch("http://localhost:8000/produtos", { cache: "no-store" });
  const produtos: Produto[] = await res.json();
  const categorias = [...new Set(produtos.map(p => p.categoria))];

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-purple-700">Daki Réplica</h1>
        <span className="text-sm text-gray-500">Entrega em até 15 min</span>
      </header>
      {categorias.map(cat => (
        <section key={cat} className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">{cat}</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {produtos.filter(p => p.categoria === cat).map(p => (
              <div key={p.sku} className="rounded-xl bg-white p-4 shadow-sm">
                <p className="font-medium text-gray-900">{p.nome}</p>
                <p className="mt-1 text-lg font-bold text-purple-700">R$ {Number(p.preco).toFixed(2).replace(".", ",")}</p>
                <p className={`mt-1 text-xs ${p.estoque > 0 ? "text-green-600" : "text-red-600"}`}>
                  {p.estoque > 0 ? `${p.estoque} em estoque` : "Esgotado"}
                </p>
                <button disabled={p.estoque === 0} className="mt-3 w-full rounded-lg bg-purple-600 py-2 text-sm text-white disabled:bg-gray-300">
                  Adicionar
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
