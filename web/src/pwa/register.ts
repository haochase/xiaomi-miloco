import { shouldRegisterPwa } from "./cachePolicy";

export function registerPwa(): void {
  if (
    !shouldRegisterPwa({
      isSecureContext: window.isSecureContext,
      hasServiceWorker: "serviceWorker" in navigator,
    })
  ) {
    return;
  }

  const register = () => {
    void navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // PWA support is progressive. The panel remains usable without it.
    });
  };
  if (document.readyState === "complete") {
    register();
  } else {
    window.addEventListener("load", register, { once: true });
  }
}
