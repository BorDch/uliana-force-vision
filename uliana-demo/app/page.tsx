import { ArrowRight, BarChart3, Camera, CheckCircle2, Eye, Layers3, Play, Smartphone, Users } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { UlianaHero } from "@/components/uliana-hero";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function Home() {
  return <main id="main">
    <SiteHeader />
    {/* 1. Company name and slogan */}<UlianaHero />

    {/* 2. Value proposition */}<section id="value" className="landing-section value-section" aria-labelledby="value-title">
      <div className="landing-section-heading" data-reveal><p className="section-kicker">Understand today’s workout</p><h2 id="value-title">How did I actually perform—and what should I focus on next?</h2></div>
      <div className="value-story" data-reveal><p className="value-lead">A recording shows what happened. <strong>ULIANA explains what to review and tracks what changes.</strong></p><p>It counts complete repetitions, divides the video into individual movements, highlights a representative moment, and summarises supported camera observations in plain language. You leave with one clear focus for your next session—not another video you have to interpret alone.</p><div className="value-contrast" aria-label="From recording to session review"><article><Camera aria-hidden="true" /><span><b>Before</b>One continuous recording to search and interpret</span></article><ArrowRight aria-hidden="true" /><article><CheckCircle2 aria-hidden="true" /><span><b>With ULIANA</b>A clear, actionable session summary</span></article></div></div>
    </section>

    {/* 3. Business thesis */}<section id="thesis" className="landing-section thesis-consumer" aria-labelledby="thesis-title">
      <div className="landing-section-heading" data-reveal><p className="section-kicker">Why ULIANA creates value</p><h2 id="thesis-title">One recording becomes structured evidence you can use.</h2></div>
      <div className="thesis-copy" data-reveal><p>Most workout recordings remain videos the user must interpret alone. ULIANA structures the set into individual repetitions, connects every supported observation to the exact video moment, and builds a comparable history across sessions.</p><p>Reliability checks mark an assessment unavailable when the camera angle or landmark quality is insufficient. Missing evidence is never presented as a positive result.</p><p>ULIANA is designed first for people training independently. Trainers and gyms may later use it to help clients review sessions between coached workouts.</p></div>
      <ol className="evidence-flow" aria-label="ULIANA analysis flow" data-reveal>{["Record", "Detect repetitions", "Explain supported observations", "Review the exact moment", "Compare compatible sessions"].map((item, index) => <li key={item}><span>{index + 1}</span>{item}</li>)}</ol>
      <aside className="future-module" data-reveal><div><Layers3 aria-hidden="true" /></div><section><p className="section-kicker">Future module</p><h3>Measurements video cannot provide</h3><p>A future sensor-equipped mat is intended to measure pressure, left/right loading and contact position. These measurements are not part of the current public camera result.</p></section></aside>
    </section>

    {/* 4. How the solution works */}<section id="how-it-works" className="landing-section how-consumer" aria-labelledby="how-title">
      <div className="landing-section-heading" data-reveal><p className="section-kicker">How it works</p><h2 id="how-title">From recorded set to focused review.</h2></div>
      <ol className="journey-steps" data-reveal><li><span>01</span><Smartphone aria-hidden="true" /><h3>Position your phone.</h3><p>Keep your full body visible from a supported camera angle.</p></li><li><span>02</span><Camera aria-hidden="true" /><h3>Record your set.</h3><p>Capture or upload a short standard push-up session.</p></li><li><span>03</span><Eye aria-hidden="true" /><h3>Let ULIANA structure it.</h3><p>The local application detects pose landmarks and complete movement cycles.</p></li><li><span>04</span><Play aria-hidden="true" /><h3>Review the result.</h3><p>See the annotated video, repetition count, supported body-alignment and range-of-motion observations, and the exact moment that deserves attention.</p></li><li><span>05</span><BarChart3 aria-hidden="true" /><h3>Repeat the setup.</h3><p>Record from the same viewpoint later to compare compatible sessions and follow your progress.</p></li></ol>
      <p className="how-caption" data-reveal>Phone recording → pose overlay → numbered repetitions → Coach Summary → Watch repetition → compatible-session progress</p>
    </section>

    {/* 5. Call to action */}<section id="pilot" className="landing-section sample-cta" aria-labelledby="cta-title">
      <div data-reveal><p className="section-kicker">See a session review</p><h2 id="cta-title">See what ULIANA adds to a recording.</h2><p>Open a prepared camera-analysis result to explore the annotated video, numbered repetitions, supported movement observations and Coach Summary. The public sample does not upload or analyse your own video.</p><span className="prepared-label">Prepared sample result — no visitor video is uploaded.</span></div>
      <div className="cta-actions" data-reveal><a className="landing-button landing-button-primary" href={`${base}/?screen=demo`}>Explore a sample review <ArrowRight aria-hidden="true" /></a><a className="landing-button landing-button-secondary" href="mailto:boris.cherkassov@skoltech.ru?subject=ULIANA%20pilot">Join the pilot</a><p>Independent exercisers, trainers and gyms can help test the complete local prototype with real recorded sessions.</p></div>
    </section>

    {/* 6. Social proof and traction */}<section id="traction" className="landing-section evidence-section" aria-labelledby="traction-title">
      <div className="landing-section-heading" data-reveal><p className="section-kicker">Early evidence</p><h2 id="traction-title">Tested with people, recordings and previously unseen participants.</h2></div>
      <div className="evidence-cards" data-reveal><article><Users aria-hidden="true" /><p className="evidence-type">Customer discovery</p><h3>40 initial responses</h3><p>Thirty-eight answered the subsequent questions. Of those, 26 (68.4%) felt only somewhat confident or not confident about their technique. Voice feedback was selected by 24 (63.2%), visual feedback by 20 (52.6%), and progress tracking by 20 (52.6%). Eighteen (47.4%) were likely or very likely to use the proposed product; only five reported dissatisfaction with existing solutions.</p><small>Exploratory signals—not proof of market demand or population-wide prevalence.</small></article><article><Camera aria-hidden="true" /><p className="evidence-type">Real recordings</p><h3>30 videos · 10 participants</h3><p>The prototype dataset contains three camera viewpoints per participant. Development participants were kept separate from holdout participants.</p></article><article><CheckCircle2 aria-hidden="true" /><p className="evidence-type">Held-out evaluation</p><h3>9 of 9 within ±1 repetition</h3><p>The frozen evaluation used nine recordings from three previously unseen participants. Predictions were available for all nine; six counts were exact and mean absolute error was 0.333 repetitions. Viewpoint classification was correct for all nine recordings.</p></article></div>
      <p className="evidence-limit" data-reveal>Early feasibility results from a small prototype study; not a medical assessment or universal performance guarantee.</p>
    </section>
    <footer className="landing-footer"><a href="#top">ULIANA</a><p>Recorded-session review for independent exercise.</p><a href={`${base}/?screen=demo`}>Explore the sample <ArrowRight aria-hidden="true" /></a></footer>
  </main>;
}
