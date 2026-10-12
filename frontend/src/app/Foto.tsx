export default function Foto({ src, className = "" }: { src: string | null; className?: string }) {
  if (src && src.startsWith("http"))
    return <img src={src} alt="" loading="lazy" className={`object-contain ${className}`} />;
  return <span>{src || "📦"}</span>;
}
