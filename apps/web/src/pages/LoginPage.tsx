/**
 * Pantalla de acceso.
 *
 * Detalles que no son decorativos:
 *
 * - No hay registro público. Las cuentas las crea un administrador; ofrecer un
 *   formulario de alta llevaría a un callejón sin salida.
 * - El campo de contraseña usa `autoComplete="current-password"` para que el
 *   gestor de contraseñas del navegador lo reconozca y no la guarde mal.
 * - El error se anuncia con `role="alert"` y se asocia al formulario, para que
 *   un lector de pantalla lo lea sin tener que buscarlo.
 */

import { useEffect, useRef, useState } from "react";

import { useSession } from "../auth/session-context";

export function LoginPage() {
  const { signIn, error, busy, clearError } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const emailRef = useRef<HTMLInputElement>(null);

  // El foco inicial va al primer campo: evita un tabulador en cada acceso.
  useEffect(() => {
    emailRef.current?.focus();
  }, []);

  return (
    <main className="auth">
      <div className="auth-card">
        <div className="brand auth-brand">
          <span className="mark" aria-hidden="true" />
          EAG · Licitaciones
        </div>

        <h1 className="auth-title">Acceso</h1>
        <p className="auth-lead">
          Preevaluación de oportunidades de contratación pública. La decisión de
          participar permanece en manos del analista.
        </p>

        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            void signIn(email, password);
          }}
        >
          <div className="field">
            <label htmlFor="email">Correo</label>
            <input
              id="email"
              ref={emailRef}
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (error) clearError();
              }}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                if (error) clearError();
              }}
            />
          </div>

          {error ? (
            <p className="auth-error" role="alert">
              {error}
            </p>
          ) : null}

          <button type="submit" className="btn btn-p auth-submit" disabled={busy}>
            {busy ? "Comprobando…" : "Entrar"}
          </button>
        </form>

        <p className="auth-note">
          Las cuentas se crean por invitación de un administrador. No hay
          registro público.
        </p>
      </div>
    </main>
  );
}
