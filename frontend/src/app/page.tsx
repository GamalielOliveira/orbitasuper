import Catalogo from "./Catalogo";
export const instant = false;

export default async function Home() {
  const produtos = await (await fetch("http://localhost:8000/produtos", { cache: "no-store" })).json();
  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-purple-700">Daki Réplica</h1>
        <span className="text-sm text-gray-500">Entrega em até 15 min</span>
      </header>
      <Catalogo inicial={produtos} />
    </main>
  );
}
