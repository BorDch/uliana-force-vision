import { ArrowDownRight, Camera, CircleGauge, Play } from "lucide-react";

import { SessionDashboard } from "@/components/session-dashboard";
import { UlianaHero } from "@/components/uliana-hero";

export default function Home() {
  return (
    <main>
      <UlianaHero />

      <section id="problem" className="problem-section" aria-labelledby="problem-title">
        <div className="section-kicker">The problem</div>
        <div className="problem-layout">
          <h2 id="problem-title">A video shows what happened.<br />It does not make the set easy to read.</h2>
          <div className="problem-points">
            <p>When several repetitions happen in one clip, pace, depth and left–right patterns are hard to compare at a glance.</p>
            <p>ULIANA is a prototype for turning a recorded session into a focused review—not live coaching and not a medical assessment.</p>
          </div>
        </div>
        <div className="problem-rule"><span>One set</span><i /><span>Clear repetitions</span><i /><span>Two complementary views</span></div>
      </section>

      <SessionDashboard />

      <section id="how-it-works" className="how-section" aria-labelledby="how-title">
        <div className="section-kicker">From session to review</div>
        <div className="how-heading-row">
          <h2 id="how-title">A simple path through the prototype.</h2>
          <p>
            The evaluated pipeline works with recorded movement. The interface keeps the source, observations and illustrative sensor view clearly separated.
          </p>
        </div>

        <div className="process-grid">
          <article className="process-card">
            <span className="process-icon" aria-hidden="true"><Play /></span>
            <span className="process-number">01</span>
            <h3>Record</h3>
            <p>A phone captures a push-up set from a fixed viewpoint.</p>
          </article>
          <article className="process-card">
            <span className="process-icon" aria-hidden="true"><Camera /></span>
            <span className="process-number">02</span>
            <h3>Analyse</h3>
            <p>The evaluated pipeline processes the recording after the session—not as a live feed.</p>
          </article>
          <article className="process-card">
            <span className="process-icon" aria-hidden="true"><CircleGauge /></span>
            <span className="process-number">03</span>
            <h3>Review</h3>
            <p>Review the set summary, choose a repetition and compare both views.</p>
          </article>
        </div>
      </section>

      <footer>
        <a className="footer-brand" href="#top" aria-label="ULIANA, back to top">U<span>·</span></a>
        <p>Skoltech Team 10 · Recorded-session review prototype</p>
        <a href="#top">Back to top <ArrowDownRight aria-hidden="true" /></a>
      </footer>
    </main>
  );
}
