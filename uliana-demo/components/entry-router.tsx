"use client";
import { useEffect, useState, type ReactNode } from "react";
import { PrototypeApp } from "@/components/prototype-app";
import { MobilePwaSupport } from "@/components/mobile-pwa-support";
import { MobileAuth } from "@/components/mobile-auth";
import { ExperimentalSensor } from "@/components/mobile-sensor";

const modes = {app:"select",pushup:"pushup",pullup:"pullup",processing:"processing",session:"session",progress:"progress",demo:"demo"} as const;
export function EntryRouter({children}:{children:ReactNode}){
  const [screen] = useState<keyof typeof modes|null>(() => typeof window === "undefined" ? null : new URLSearchParams(location.search).get("screen") as keyof typeof modes|null);
  const [runtimeMode, setRuntimeMode] = useState<"site"|"app"|"mobile">("site");
  const [runtimeReady, setRuntimeReady] = useState(() => process.env.NEXT_PUBLIC_STATIC_DEMO === "1");
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_STATIC_DEMO === "1") return;
    fetch("/api/runtime")
      .then(async (response) => response.ok ? await response.json() as {mode?: string} : Promise.reject())
      .then((runtime) => { const value = runtime as {mode?: "site"|"app"|"mobile";profile_id?:string}; setRuntimeMode(value.mode ?? "site"); if(value.profile_id) sessionStorage.setItem("uliana-profile-id",value.profile_id); })
      .catch(() => setRuntimeMode("site"))
      .finally(() => setRuntimeReady(true));
  }, []);
  if (process.env.NEXT_PUBLIC_STATIC_DEMO === "1" && screen !== "demo") return children;
  if (!runtimeReady) return null;
  if (runtimeMode === "mobile") return <MobileAuth><MobilePwaSupport/>{new URLSearchParams(typeof window === "undefined" ? "" : location.search).get("screen") === "sensor" ? <ExperimentalSensor /> : <PrototypeApp mode={screen && modes[screen] && screen !== "pullup" ? modes[screen] : "select"} appOnly mobile />}</MobileAuth>;
  if (runtimeMode === "app") return <PrototypeApp mode={screen && modes[screen] && screen !== "demo" ? modes[screen] : "select"} appOnly />;
  return screen && modes[screen] ? <PrototypeApp mode={modes[screen]}/> : children;
}
