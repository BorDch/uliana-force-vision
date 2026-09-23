"use client";
import { useEffect, useState, type ReactNode } from "react";
import { PrototypeApp } from "@/components/prototype-app";
import { MobilePwaSupport } from "@/components/mobile-pwa-support";
import { MobileAuth } from "@/components/mobile-auth";
import { ExperimentalSensor } from "@/components/mobile-sensor";
import { MobileLiveSession } from "@/components/mobile-live-session";

const modes = {app:"select",pushup:"pushup",pullup:"pullup",processing:"processing",session:"session",progress:"progress",demo:"demo"} as const;
export function EntryRouter({children}:{children:ReactNode}){
  const [screen] = useState<string|null>(() => typeof window === "undefined" ? null : new URLSearchParams(location.search).get("screen"));
  const [runtimeMode, setRuntimeMode] = useState<"site"|"app"|"mobile">("site");
  const [runtimeReady, setRuntimeReady] = useState(() => process.env.NEXT_PUBLIC_STATIC_DEMO === "1");
  useEffect(() => {
    if (location.pathname === "/app/" && screen === "live") history.replaceState(null, "", "/app?screen=live");
    if (process.env.NEXT_PUBLIC_STATIC_DEMO === "1") return;
    fetch("/api/runtime")
      .then(async (response) => response.ok ? await response.json() as {mode?: string} : Promise.reject())
      .then((runtime) => { const value = runtime as {mode?: "site"|"app"|"mobile";profile_id?:string}; setRuntimeMode(value.mode ?? "site"); if(value.profile_id) sessionStorage.setItem("uliana-profile-id",value.profile_id); })
      .catch(() => setRuntimeMode("site"))
      .finally(() => setRuntimeReady(true));
  }, [screen]);
  if (process.env.NEXT_PUBLIC_STATIC_DEMO === "1" && screen !== "demo") return children;
  if (!runtimeReady) return null;
  const selected = screen && screen in modes ? modes[screen as keyof typeof modes] : null;
  if (runtimeMode === "mobile") return <MobileAuth><MobilePwaSupport/>{screen === "live" ? <MobileLiveSession /> : screen === "sensor" ? <ExperimentalSensor /> : <PrototypeApp mode={selected && screen !== "pullup" ? selected : "select"} appOnly mobile />}</MobileAuth>;
  if (runtimeMode === "app") return <PrototypeApp mode={selected && screen !== "demo" ? selected : "select"} appOnly />;
  return selected ? <PrototypeApp mode={selected}/> : children;
}
