"use client";

import { useEffect } from "react";

/**
 * Progressive scroll motion for the landing page.
 *
 * GSAP, ScrollTrigger and Lenis are loaded with dynamic import() after the page
 * has painted, so they never block first paint. When a visitor prefers reduced
 * motion, nothing is loaded at all and the static layout is used as-is.
 *
 * Content stays visible without JavaScript: reveals only start inside this
 * effect, which means the exported HTML is always readable.
 */
export function MotionRoot() {
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches) return;

    let disposed = false;
    let teardown: (() => void) | undefined;

    const boot = async () => {
      const [{ gsap }, { ScrollTrigger }, { default: Lenis }] = await Promise.all([
        import("gsap"),
        import("gsap/ScrollTrigger"),
        import("lenis"),
      ]);
      if (disposed) return;

      gsap.registerPlugin(ScrollTrigger);

      const lenis = new Lenis({
        duration: 0.9,
        smoothWheel: true,
        wheelMultiplier: 1,
        touchMultiplier: 1.6,
      });
      const onLenisScroll = () => ScrollTrigger.update();
      lenis.on("scroll", onLenisScroll);
      const ticker = (time: number) => lenis.raf(time * 1000);
      gsap.ticker.add(ticker);
      gsap.ticker.lagSmoothing(0);

      const reducedNow = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      // Reveal groups: fade + 12px lift, staggered children, runs once per group.
      const revealTriggers = gsap.utils.toArray<HTMLElement>("[data-reveal]").map((group) => {
        const staggerTargets = group.dataset.reveal === "self"
          ? [group]
          : Array.from(group.children).filter((child): child is HTMLElement => child instanceof HTMLElement);
        if (!staggerTargets.length) return null;
        return gsap.from(staggerTargets, {
          opacity: 0,
          y: 12,
          duration: 0.5,
          ease: "power2.out",
          stagger: 0.06,
          clearProps: "transform",
          scrollTrigger: { trigger: group, start: "top 88%", once: true },
        });
      });

      // Numeric counters (rep counts and the 50 / 50 relative hand-zone split).
      const countTriggers = gsap.utils.toArray<HTMLElement>("[data-count-to]").map((node) => {
        const target = Number(node.dataset.countTo);
        if (!Number.isFinite(target)) return null;
        const suffix = node.dataset.countSuffix ?? "";
        const value = { current: 0 };
        return gsap.to(value, {
          current: target,
          duration: 0.9,
          ease: "power2.out",
          scrollTrigger: { trigger: node, start: "top 92%", once: true },
          onUpdate: () => {
            node.textContent = `${Math.round(value.current)}${suffix}`;
          },
          onComplete: () => {
            node.textContent = `${target}${suffix}`;
          },
        });
      });

      // Gentle parallax on the hero visual only.
      const heroVisual = document.querySelector<HTMLElement>(".scene-column");
      const parallax = heroVisual
        ? gsap.to(heroVisual, {
            y: -28,
            ease: "none",
            scrollTrigger: {
              trigger: ".hero-shell",
              start: "top top",
              end: "bottom top",
              scrub: 0.4,
            },
          })
        : null;

      // Anchor links move through Lenis so in-page jumps stay smooth and the
      // sticky header offset is respected.
      const onAnchorClick = (event: MouseEvent) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const anchor = (event.target as HTMLElement | null)?.closest?.("a[href^='#']");
        if (!(anchor instanceof HTMLAnchorElement)) return;
        const hash = anchor.getAttribute("href");
        if (!hash || hash === "#") return;
        const destination = document.getElementById(hash.slice(1));
        if (!destination) return;
        event.preventDefault();
        lenis.scrollTo(destination, { offset: -76, duration: 0.9 });
        window.history.replaceState(null, "", hash);
        destination.setAttribute("tabindex", "-1");
        destination.focus({ preventScroll: true });
      };
      document.addEventListener("click", onAnchorClick);

      teardown = () => {
        document.removeEventListener("click", onAnchorClick);
        gsap.ticker.remove(ticker);
        lenis.off("scroll", onLenisScroll);
        lenis.destroy();
        for (const trigger of [...revealTriggers, ...countTriggers]) trigger?.scrollTrigger?.kill();
        for (const trigger of [...revealTriggers, ...countTriggers]) trigger?.kill();
        parallax?.scrollTrigger?.kill();
        parallax?.kill();
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
        if (reducedNow()) {
          gsap.set("[data-reveal] > *", { clearProps: "all" });
        }
      };
    };

    boot().catch(() => {
      // Motion is an enhancement: a failed chunk leaves the static page intact.
    });

    return () => {
      disposed = true;
      teardown?.();
    };
  }, []);

  return null;
}
