export const instant = false;
import Catalogo from "./Catalogo";

export default async function Home() {
  const produtos = await (await fetch("http://localhost:8000/produtos", { cache: "no-store" })).json();
  return <Catalogo inicial={produtos} />;
}
