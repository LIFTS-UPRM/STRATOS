"use client";

import { startTransition, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

function MicrosoftLogo() {
  return (
    <span className={styles.microsoftLogo} aria-hidden="true">
      <span className={styles.logoTileRed} />
      <span className={styles.logoTileGreen} />
      <span className={styles.logoTileBlue} />
      <span className={styles.logoTileYellow} />
    </span>
  );
}

function LoadingSpinner() {
  return <span className={styles.spinner} aria-hidden="true" />;
}

export default function Home() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      startTransition(() => {
        router.push("/chat");
      });
    }, 1100);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [isLoading, router]);

  return (
    <main className={styles.page}>
      <div className={styles.overlay} />
      <section className={styles.loginCard} aria-label="Login panel">
        <div className={styles.authPanel}>
          <h1 className={styles.title}>Sign in to:</h1>
          <div className={styles.brandLockup}>
            <Image
              src="/assets/STRATOS_LOGO_PNG_NO_BG/Color_text.png"
              alt="STRATOS"
              width={438}
              height={365}
              priority
              className={styles.brandLogo}
            />
        </div>
          <p className={styles.subtitle}>
            Continue with your organization credentials to access mission chat and operations.
          </p>
        </div>
        <button
          className={styles.loginButton}
          type="button"
          disabled={isLoading}
          aria-busy={isLoading}
          onClick={() => setIsLoading(true)}
        >
          <span className={styles.loginButtonMain}>
            <MicrosoftLogo />
            <span className={styles.loginButtonText}>
              {isLoading ? "Connecting to Microsoft" : "Sign in with Microsoft"}
            </span>
          </span>
          <span className={styles.loginButtonMeta}>
            {isLoading ? (
              <>
                <LoadingSpinner />
                <span>Loading</span>
              </>
            ) : (
              <span>Continue</span>
            )}
          </span>
        </button>
      </section>
    </main>
  );
}
