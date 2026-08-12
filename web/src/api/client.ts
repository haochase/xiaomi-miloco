/** fetch 包装：自动注入 Bearer token；统一错误。 */

import i18n from "@/i18n";

declare global {
  interface Window {
    __MILOCO_TOKEN__?: string;
    __MILOCO_OUTFIT_SIDECAR__?: boolean;
  }
}

export function resolveToken(): string {
  const injected = window.__MILOCO_TOKEN__;
  // 未被 backend SPA handler 注入时还是占位字面量 "__MILOCO_INJECT_TOKEN_HERE__"，
  // 走 guard 返空串避免把假 token 当真用（fetch 也就不带 Authorization 头）。
  // 用宽前缀 "__MILOCO_" 而不是只挡 "__MILOCO_INJECT_"——backend token 是
  // uuid.uuid4() 生成（hex+dash），永远不会以 __MILOCO_ 打头；多挡一层防止旧版
  // 字面量 "__MILOCO_TOKEN__"（旧 placeholder）若意外残留也会被识别。
  if (injected && !injected.startsWith("__MILOCO_")) return injected;
  return "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const token = resolveToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      msg = body.message ?? body.detail ?? msg;
    } catch {
      // ignore
    }
    throw new ApiError(resp.status, msg);
  }
  // backend NormalResponse 业务错(HTTP 200 但 body.code != 0)也当错处理。
  // 当前 backend 全走 HTTPException → handle_exception → 4xx,没用 200+code != 0
  // 这种约定。这条防御为前置兼容层 — 未来若引入 200 业务错码不漏。
  // resp.json() 解析失败：捕获后包成 ApiError,避免把原生 SyntaxError 透给调用方
  // (家用路由 captive portal 兜底页 / nginx 加 banner / 网络注入 等场景下,
  // backend 返 200 但 body 不是 JSON,toast 直接显英文 "Unexpected token < in JSON
  // at position 0" 住户看不懂)。
  let body: T & { code?: number; message?: string };
  try {
    body = (await resp.json()) as T & { code?: number; message?: string };
  } catch {
    throw new ApiError(resp.status, i18n.t("api.invalidJson"));
  }
  if (typeof body.code === "number" && body.code !== 0) {
    // `||` 而非 `??`：?? 只挡 null/undefined,空串 "" 也是合法 message,但住户看到
    // "" 跟"无错误"无法区分,需要用 ?code? 兜底让住户至少看到 code 编码。
    throw new ApiError(resp.status, body.message || i18n.t("api.bizError", { code: body.code }));
  }
  return body as T;
}
