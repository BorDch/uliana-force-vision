"use client";
import { useEffect, useState, type ReactNode } from "react";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

type View = "signin"|"register"|"account";
export function MobileAuth({children}:{children:ReactNode}) {
  const [username,setUsername]=useState<string|null>(null),[ready,setReady]=useState(false),[view,setView]=useState<View>("signin"),[error,setError]=useState("");
  useEffect(()=>{fetch("/api/auth/me").then(async r=>{if(r.ok)setUsername(((await r.json()) as {username:string}).username)}).finally(()=>setReady(true))},[]);
  if(!ready) return <main className="auth-page"><p>Loading ULIANA…</p></main>;
  if(!username) return <AuthForm view={view} setView={setView} error={error} setError={setError} onAuthenticated={setUsername}/>;
  return <><button className="mobile-account-button" onClick={()=>setView("account")}>{username}</button>{view==="account"&&<Account username={username} close={()=>setView("signin")} signedOut={()=>{localStorage.removeItem("uliana-session-history");window.location.reload()}}/>}{children}</>;
}

function AuthForm({view,setView,error,setError,onAuthenticated}:{view:View;setView:(v:View)=>void;error:string;setError:(v:string)=>void;onAuthenticated:(v:string)=>void}) {
  const [busy,setBusy]=useState(false);
  const submit=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();setBusy(true);setError("");const data=new FormData(event.currentTarget);const registering=view==="register";try{const response=await fetch(`/api/auth/${registering?"register":"login"}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(registering?{username:data.get("username"),password:data.get("password"),password_confirmation:data.get("confirmation"),invitation_code:data.get("invitation")}:{username:data.get("username"),password:data.get("password")})});const payload=await response.json() as {username?:string;detail?:string};if(!response.ok)throw new Error(payload.detail||"Authentication failed.");onAuthenticated(payload.username!);window.location.href="/?screen=app"}catch(e){setError(e instanceof Error?e.message:"Authentication failed.")}finally{setBusy(false)}};
  return <main className="auth-page"><section className="auth-card"><Link className="proto-brand" href="/">ULIANA<span>·</span></Link><p className="eyebrow">Mobile pilot</p><h1>{view==="register"?"Create account":"Sign in"}</h1><form onSubmit={submit}><label>Username<input name="username" autoCapitalize="none" autoComplete="username" required minLength={3}/></label><label>Password<input name="password" type="password" autoComplete={view==="register"?"new-password":"current-password"} required minLength={10}/></label>{view==="register"&&<><label>Confirm password<input name="confirmation" type="password" autoComplete="new-password" required minLength={10}/></label><label>Pilot invitation code<input name="invitation" type="password" required/></label></>} {error&&<p className="form-error">{error}</p>}<button disabled={busy}>{busy?"Please wait…":view==="register"?"Create account":"Sign in"}</button></form><button className="auth-switch" onClick={()=>{setError("");setView(view==="register"?"signin":"register")}}>{view==="register"?"Already have an account? Sign in":"Create an account"}</button>{view==="signin"&&<small>Password recovery is not available during the pilot.</small>}</section></main>;
}

function Account({username,close,signedOut}:{username:string;close:()=>void;signedOut:()=>void}) {
  const [password,setPassword]=useState(""),[confirmation,setConfirmation]=useState(""),[error,setError]=useState("");
  const logout=async()=>{const r=await apiFetch("/api/auth/logout",{method:"POST"});if(r.ok)signedOut()};
  const remove=async()=>{if(confirmation!=="DELETE")return setError("Type DELETE to confirm.");const r=await apiFetch("/api/auth/account",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({password,confirmation})});if(r.ok)signedOut();else setError(((await r.json()) as {detail?:string}).detail??"Account deletion failed.")};
  return <div className="account-overlay"><section className="account-card"><button className="account-close" onClick={close}>Close</button><p className="eyebrow">Account</p><h2>{username}</h2><button onClick={logout}>Sign out</button><details><summary>Delete my account and data</summary><p>This permanently deletes your workouts, videos, results, and login sessions.</p><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></label><label>Type DELETE<input value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label>{error&&<p className="form-error">{error}</p>}<button className="danger" onClick={remove}>Delete my account and data</button></details></section></div>;
}
