"use client";
import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";
import { mobileCopy } from "@/lib/mobile-copy";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{outcome: "accepted"|"dismissed"}> };
export function MobilePwaSupport() {
  const [prompt, setPrompt] = useState<InstallEvent | null>(null);
  const [show, setShow] = useState(() => typeof window !== "undefined" && !(matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & {standalone?: boolean}).standalone) && localStorage.getItem("uliana-install-tip-dismissed") !== "1");
  const [ios] = useState(() => typeof navigator !== "undefined" && /iphone|ipad|ipod/i.test(navigator.userAgent));
  useEffect(() => {
    document.documentElement.classList.add("uliana-mobile");
    const handler = (event: Event) => { event.preventDefault(); setPrompt(event as InstallEvent); setShow(true); };
    window.addEventListener("beforeinstallprompt", handler);
    if ("serviceWorker" in navigator) {
      let refreshing=false;
      navigator.serviceWorker.addEventListener("controllerchange",()=>{if(!refreshing){refreshing=true;window.location.reload()}});
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(registration=>registration.update()).catch(() => undefined);
    }
    return () => { document.documentElement.classList.remove("uliana-mobile"); window.removeEventListener("beforeinstallprompt", handler); };
  }, []);
  if (!show) return null;
  const dismiss = () => { localStorage.setItem("uliana-install-tip-dismissed", "1"); setShow(false); };
  return <aside className="install-tip" aria-label={mobileCopy.install}><Download /><div><strong>{mobileCopy.install}</strong><span>{ios ? mobileCopy.iosInstall : prompt ? "Install ULIANA for quick access from your home screen." : mobileCopy.androidInstall}</span>{prompt && <button onClick={async () => { await prompt.prompt(); await prompt.userChoice; setPrompt(null); setShow(false); }}>Install app</button>}</div><button className="install-dismiss" onClick={dismiss} aria-label="Dismiss install instructions"><X /></button></aside>;
}
