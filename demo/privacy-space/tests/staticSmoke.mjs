import { readFile } from "node:fs/promises";

const root = new URL("../dist/", import.meta.url);
const html = await readFile(new URL("index.html", root), "utf8");
const asset = /src="(\/assets\/[^\"]+\.js)"/.exec(html)?.[1];
const stylesheet = /href="(\/assets\/[^\"]+\.css)"/.exec(html)?.[1];
if (!asset) throw new Error("missing bundled javascript asset");
if (!stylesheet) throw new Error("missing bundled stylesheet asset");
const js = await readFile(new URL(`.${asset}`, root), "utf8");

for (const required of ["家庭隐私空间", "今日建议", "空间证据", "事实源未启用", "事实源可用", "事实源暂不可用", "回放合成处理结果"]) {
  if (!js.includes(required)) throw new Error(`missing UI copy: ${required}`);
}
for (const forbidden of ["owner_id", "device_id", "api_key", "absolute_path", "raw_provider_answer", "provider_failed", "provider_invalid"]) {
  if (js.includes(forbidden)) throw new Error(`sensitive field leaked: ${forbidden}`);
}
const css = await readFile(new URL(`.${stylesheet}`, root), "utf8");
for (const breakpoint of ["@media(max-width:820px)", "@media(max-width:420px)"]) {
  if (!css.includes(breakpoint)) throw new Error(`missing responsive breakpoint: ${breakpoint}`);
}
console.log("static privacy-space smoke passed");
