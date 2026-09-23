import { ArrowUpRight } from "lucide-react";

/**
 * Persistent header: company name, in-page navigation and the primary call to
 * action stay reachable while the visitor scrolls the review surface.
 */
export function SiteHeader() {
  return (
    <header className="site-bar">
      <div className="site-bar-inner">
        <a className="brand" href="#top" aria-label="ULIANA, back to top">
          <span className="brand-mark" aria-hidden="true">U<span>·</span></span>
          <span className="brand-copy">
            <span className="brand-name">ULIANA</span>
            <span className="brand-sub">Skoltech Team Hack10</span>
          </span>
        </a>

        <nav className="site-nav" aria-label="Page sections">
          <a href="#value">Why ULIANA</a>
          <a href="#thesis">How it helps</a>
          <a href="#how-it-works">How it works</a>
          <a href="#pilot">Sample</a>
          <a href="#traction">Traction</a>
        </nav>

        <a className="site-bar-cta" href={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/?screen=demo`}>
          Explore sample
          <ArrowUpRight aria-hidden="true" />
        </a>
      </div>
    </header>
  );
}
