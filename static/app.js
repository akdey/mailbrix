(function () {
  // 1. Theme toggle (system -> light -> dark)
  const themeBtn = document.getElementById("theme-toggle");
  const savedTheme = localStorage.getItem("mb-theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", savedTheme);
  }
  function updateThemeLabel() {
    if (!themeBtn) return;
    const current = document.documentElement.getAttribute("data-theme");
    themeBtn.textContent = current === "dark" ? "Dark" : current === "light" ? "Light" : "Auto";
  }
  updateThemeLabel();
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : current === "light" ? null : "dark";
      if (next) {
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("mb-theme", next);
      } else {
        document.documentElement.removeAttribute("data-theme");
        localStorage.removeItem("mb-theme");
      }
      updateThemeLabel();
    });
  }

  // 2. Tabs (accessible focusgroup + fallback)
  if (!("focusGroup" in HTMLElement.prototype)) {
    try {
      import("https://cdn.jsdelivr.net/npm/@microsoft/focusgroup-polyfill/+esm")
        .then(({ polyfill }) => polyfill())
        .catch(() => {});
    } catch {}
  }

  const tablist = document.querySelector(".tablist");
  if (tablist) {
    const tabs = Array.from(tablist.querySelectorAll("button"));
    const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

    function selectTab(nextTab, { focus = false } = {}) {
      for (const tab of tabs) {
        const isSelected = tab === nextTab;
        tab.ariaSelected = String(isSelected);
        tab.toggleAttribute("focusgroupstart", isSelected);
      }
      for (const panel of panels) {
        const matches = panel.getAttribute("aria-labelledby") === nextTab.id;
        if (matches) {
          panel.removeAttribute("hidden");
          panel.setAttribute("tabindex", "0");
        } else {
          panel.setAttribute("hidden", "until-found");
          panel.removeAttribute("tabindex");
        }
      }
      try {
        nextTab.scrollIntoView({ block: "nearest", inline: "nearest", container: "nearest" });
      } catch {
        nextTab.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
      if (focus) nextTab.focus();
    }

    tablist.addEventListener("click", (event) => {
      const tab = event.target.closest("button");
      if (tab) selectTab(tab);
    });

    tablist.addEventListener("focusin", (event) => {
      const tab = event.target.closest("button");
      if (tab && tab.ariaSelected !== "true") selectTab(tab);
    });

    tablist.addEventListener("keydown", (event) => {
      if ("focusGroup" in HTMLElement.prototype) return;
      const idx = tabs.indexOf(document.activeElement);
      if (idx === -1) return;
      let nextIdx = null;
      if (event.key === "ArrowRight") nextIdx = (idx + 1) % tabs.length;
      else if (event.key === "ArrowLeft") nextIdx = (idx - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") nextIdx = 0;
      else if (event.key === "End") nextIdx = tabs.length - 1;
      if (nextIdx !== null) {
        event.preventDefault();
        selectTab(tabs[nextIdx], { focus: true });
      }
    });

    for (const panel of panels) {
      panel.addEventListener("beforematch", () => {
        const tabId = panel.getAttribute("aria-labelledby");
        const tab = tabs.find((t) => t.id === tabId);
        if (tab) selectTab(tab);
      });
    }
  }

  // 4. Copy buttons
  for (const btn of document.querySelectorAll("button.copy-btn")) {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (!target) return;
      const text = target.textContent;
      const prev = btn.textContent;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
        btn.textContent = "Copied";
        setTimeout(() => {
          btn.textContent = prev;
        }, 1500);
      } catch {
        btn.textContent = "Failed";
      }
    });
  }

  // 5. Credential Generator
  function randomBytes(length) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return bytes;
  }

  function toBase64Url(bytes) {
    let binary = "";
    for (const b of bytes) binary += String.fromCharCode(b);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function toHex(bytes) {
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function sha256Fallback(ascii) {
    const rightRotate = (value, amount) => (value >>> amount) | (value << (32 - amount));
    const mathPow = Math.pow;
    const maxWord = mathPow(2, 32);
    let i, j;
    let result = "";
    const words = [];
    const asciiBitLength = ascii.length * 8;
    let hash = (sha256Fallback.h = sha256Fallback.h || []);
    const k = (sha256Fallback.k = sha256Fallback.k || []);
    let primeCounter = k.length;
    const isComposite = {};
    for (let candidate = 2; primeCounter < 64; candidate++) {
      if (!isComposite[candidate]) {
        for (i = 0; i < 313; i += candidate) isComposite[i] = candidate;
        hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
        k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
      }
    }
    ascii += "\x80";
    while ((ascii.length % 64) - 56) ascii += "\x00";
    for (i = 0; i < ascii.length; i++) {
      j = ascii.charCodeAt(i);
      if (j >> 8) return "";
      words[i >> 2] |= j << (((3 - i) % 4) * 8);
    }
    words[words.length] = (asciiBitLength / maxWord) | 0;
    words[words.length] = asciiBitLength;
    for (j = 0; j < words.length; ) {
      const w = words.slice(j, (j += 16));
      const oldHash = hash;
      hash = hash.slice(0, 8);
      for (i = 0; i < 64; i++) {
        const w15 = w[i - 15], w2 = w[i - 2];
        const a = hash[0], e = hash[4];
        const temp1 =
          hash[7] +
          (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)) +
          ((e & hash[5]) ^ (~e & hash[6])) +
          k[i] +
          (w[i] =
            i < 16
              ? w[i]
              : (w[i - 16] +
                  (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3)) +
                  w[i - 7] +
                  (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))) |
                0);
        const temp2 =
          (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)) +
          ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
        hash = [(temp1 + temp2) | 0].concat(hash);
        hash[4] = (hash[4] + temp1) | 0;
      }
      for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
    }
    for (i = 0; i < 8; i++) {
      for (j = 3; j + 1; j--) {
        const b = (hash[i] >> (j * 8)) & 255;
        result += (b < 16 ? 0 : "") + b.toString(16);
      }
    }
    return result;
  }

  async function sha256Hex(text) {
    const data = new TextEncoder().encode(text);
    if (window.crypto && window.crypto.subtle) {
      const digest = await window.crypto.subtle.digest("SHA-256", data);
      return toHex(new Uint8Array(digest));
    }
    return sha256Fallback(unescape(encodeURIComponent(text)));
  }

  const genBtn = document.getElementById("gen-btn");
  if (genBtn) {
    genBtn.addEventListener("click", async () => {
      try {
        const rawId = document.getElementById("gen-app-id").value.trim() || "my-app";
        const fromName = document.getElementById("gen-from-name").value.trim();
        const rateLimit = Math.max(1, parseInt(document.getElementById("gen-rate-limit").value, 10) || 60);
        const useHmac = document.getElementById("gen-hmac").checked;

        const suffix = rawId.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase() || "APP";
        const envVarName = `TENANT_${suffix}`;

        const rawApiKey = `er_${toBase64Url(randomBytes(32))}`;
        const keyHash = await sha256Hex(rawApiKey);
        const signingSecret = useHmac ? toHex(randomBytes(32)) : null;

        const tenantConfig = {};
        if (suffix.toLowerCase() !== rawId) tenantConfig.app_id = rawId;
        tenantConfig.key_hash = keyHash;
        if (signingSecret) tenantConfig.signing_secret = signingSecret;
        if (fromName) tenantConfig.from_name = fromName;
        tenantConfig.rate_limit_per_min = rateLimit;

        document.getElementById("gen-server-out").textContent =
          `${envVarName}=${JSON.stringify(tenantConfig)}`;

        const clientLines = [
          `MAILBRIX_URL=${window.location.origin}`,
          `MAILBRIX_APP_ID=${rawId}`,
          `MAILBRIX_API_KEY=${rawApiKey}`,
        ];
        if (signingSecret) clientLines.push(`MAILBRIX_SIGNING_SECRET=${signingSecret}`);
        document.getElementById("gen-client-out").textContent = clientLines.join("\n");

        const out = document.getElementById("gen-output");
        out.hidden = false;
        out.scrollIntoView({ behavior: "smooth", block: "nearest" });
        genBtn.textContent = "Generated ✓";
        setTimeout(() => {
          genBtn.textContent = "Generate Credentials";
        }, 1500);
      } catch (err) {
        genBtn.textContent = "Error generating keys";
        console.error(err);
      }
    });
  }

  // 6. Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
