"use client";

import { Code, Mail, Phone, Send } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

const CONTACT_EMAIL = "boris.cherkassov@skoltech.ru";
const CONTACT_PHONE_DISPLAY = "+7 903 190-58-26";
const CONTACT_PHONE_HREF = "tel:+79031905826";
const TELEGRAM_HANDLE = "@bor1s_cherkas0v";
const TELEGRAM_HREF = "https://t.me/bor1s_cherkas0v";
const REPO_HREF = "https://github.com/BorDch/uliana-force-vision";

type Errors = { name?: string; email?: string };

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function ContactSection() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [sent, setSent] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors: Errors = {};
    if (!name.trim()) nextErrors.name = "Please add a name so we know who we are replying to.";
    if (!email.trim()) nextErrors.email = "Please add an email address for the reply.";
    else if (!EMAIL_PATTERN.test(email.trim())) nextErrors.email = "That address is missing an @ or a domain.";

    setErrors(nextErrors);
    if (nextErrors.name) {
      setSent(false);
      nameRef.current?.focus();
      return;
    }
    if (nextErrors.email) {
      setSent(false);
      emailRef.current?.focus();
      return;
    }

    const subject = `ULIANA · message from ${name.trim()}`;
    const body = [
      `Name: ${name.trim()}`,
      `Email: ${email.trim()}`,
      `Role: ${role || "Not specified"}`,
      "",
      message.trim() || "(No message added.)",
      "",
      "Sent from the ULIANA landing page.",
    ].join("\n");
    window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    setSent(true);
  };

  return (
    <section id="contact" className="contact-section" aria-labelledby="contact-title">
      <div className="section-kicker" data-reveal="self">Call to action</div>
      <div className="contact-layout" data-reveal>
        <div className="contact-copy">
          <h2 id="contact-title">Talk to the team.</h2>
          <p className="contact-lede">
            We are looking for pilot partners, coaches and researchers to test ULIANA on real recorded sessions.
          </p>

          <ul className="contact-list">
            <li>
              <a className="contact-item" href={`mailto:${CONTACT_EMAIL}`}>
                <span className="contact-icon" aria-hidden="true"><Mail /></span>
                <span>
                  <span className="contact-label">Email</span>
                  <span className="contact-value">{CONTACT_EMAIL}</span>
                </span>
              </a>
            </li>
            <li>
              <a className="contact-item" href={CONTACT_PHONE_HREF}>
                <span className="contact-icon" aria-hidden="true"><Phone /></span>
                <span>
                  <span className="contact-label">Phone</span>
                  <span className="contact-value">{CONTACT_PHONE_DISPLAY}</span>
                </span>
              </a>
            </li>
            <li>
              <a
                className="contact-item"
                href={REPO_HREF}
                rel="noreferrer noopener"
                target="_blank"
              >
                <span className="contact-icon" aria-hidden="true"><Code /></span>
                <span>
                  <span className="contact-label">Source repository</span>
                  <span className="contact-value">github.com/BorDch/uliana-force-vision</span>
                </span>
              </a>
            </li>
          </ul>

          <a
            className="telegram-button"
            href={TELEGRAM_HREF}
            rel="noreferrer noopener"
            target="_blank"
          >
            <Send aria-hidden="true" />
            Message on Telegram
            <span className="telegram-handle">{TELEGRAM_HANDLE}</span>
          </a>
        </div>

        <form className="contact-form" onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="contact-name">Name</label>
            <input
              id="contact-name"
              name="name"
              type="text"
              autoComplete="name"
              required
              ref={nameRef}
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? "true" : undefined}
              aria-describedby={errors.name ? "contact-name-error" : undefined}
            />
            {errors.name ? <p className="field-error" id="contact-name-error">{errors.name}</p> : null}
          </div>

          <div className="field">
            <label htmlFor="contact-email">Email</label>
            <input
              id="contact-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              ref={emailRef}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={errors.email ? "true" : undefined}
              aria-describedby={errors.email ? "contact-email-error" : undefined}
            />
            {errors.email ? <p className="field-error" id="contact-email-error">{errors.email}</p> : null}
          </div>

          <div className="field">
            <label htmlFor="contact-role">Role</label>
            <select
              id="contact-role"
              name="role"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              <option value="">Select a role</option>
              <option value="Athlete">Athlete</option>
              <option value="Coach">Coach</option>
              <option value="Researcher">Researcher</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="contact-message">Message</label>
            <textarea
              id="contact-message"
              name="message"
              rows={4}
              placeholder="What would you like to test or ask about?"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
            />
          </div>

          <button type="submit" className="contact-submit">Send message</button>

          <p className="form-status" role="status" aria-live="polite">
            {sent
              ? `Thanks — your mail client should open. If it doesn't, write to ${CONTACT_EMAIL} directly.`
              : ""}
          </p>

          <a
            className="telegram-button telegram-button-inline"
            href={TELEGRAM_HREF}
            rel="noreferrer noopener"
            target="_blank"
          >
            <Send aria-hidden="true" />
            Message on Telegram
          </a>
        </form>
      </div>
    </section>
  );
}
