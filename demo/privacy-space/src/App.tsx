import { useState } from "react";
import type { DemoState } from "./demoSchema";
import { SceneCanvas } from "./SceneCanvas";
import { redactRgbaFrame } from "./redactFrame";
import { rgbaPixelsToCss } from "./pixelPreview";
import { refreshDemoScenario } from "./demoRefresh";
import { finishRefresh, startRefresh, type DemoRefreshState } from "./refreshState";
import { providerPresentation } from "./providerPresentation";

const syntheticFrame = new Uint8ClampedArray([
  70, 120, 100, 255, 70, 120, 100, 255,
  190, 140, 110, 255, 190, 140, 110, 255,
]);

export function App({ state }: { state: DemoState }) {
  const scenario = new URLSearchParams(window.location.search).get("scenario");
  const [facts, setFacts] = useState(state);
  const [refreshState, setRefreshState] = useState<DemoRefreshState>({ status: "idle", errorCode: null });
  const [privacy, setPrivacy] = useState(state.privacy);
  const [previewPixels, setPreviewPixels] = useState<Uint8ClampedArray | null>(null);
  const replaySyntheticPrivacyResult = () => {
    const result = redactRgbaFrame(
      { width: 2, height: 2, pixels: syntheticFrame },
      [{ x: 1, y: 0, width: 1, height: 2 }],
    );
    setPreviewPixels(result.pixels);
    const next = { ...privacy, status: "processed" as const, temporaryFrameCleared: false, frameCount: 1, errorCode: null };
    setPrivacy(next);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">MILОCO / PRIVACY VIEW</p>
          <h1>家庭隐私空间</h1>
          <p className="subtitle">用结构化状态展示家庭感知与穿搭建议，不展示原始画面</p>
        </div>
        <div className="privacy-pill" data-status={privacy.status}>
          <span className="status-dot" />
          {privacy.status === "processed" ? "本地摘要已完成" : privacy.status === "failed" ? "处理失败" : "等待处理"}
        </div>
      </header>

      <section className="workspace">
        <SceneCanvas rooms={facts.rooms} devices={facts.devices} peopleCount={facts.peopleCount} />

        <aside className="side-panel">
          <section className="panel-block privacy-card">
            <div className="block-heading">
              <h2>隐私处理</h2>
              <span className="quiet-label">单帧演示</span>
            </div>
            <p className="large-status">{privacy.status === "processed" ? "合成帧仅在内存处理" : privacy.status === "failed" ? "处理未完成" : "等待处理"}</p>
            <div className="metric-row">
              <span>处理帧数</span><strong>{privacy.frameCount}</strong>
            </div>
            <div className="metric-row">
              <span>展示内容</span><strong>结构化摘要</strong>
            </div>
            <div className="comparison" aria-label="合成帧遮挡示例">
              <div className="comparison-frame"><span>合成输入</span>{rgbaPixelsToCss(syntheticFrame, 2, 2).map((color, index) => <i key={index} style={{ backgroundColor: color }} />)}</div>
              <div className="comparison-frame"><span>{previewPixels ? "已遮挡" : "待处理"}</span>{rgbaPixelsToCss(previewPixels ?? syntheticFrame, 2, 2).map((color, index) => <i key={index} style={{ backgroundColor: color }} />)}</div>
            </div>
            {privacy.status !== "processed" && <button className="action-button" onClick={replaySyntheticPrivacyResult}>回放合成处理结果</button>}
            {privacy.errorCode && <p className="error-copy">错误码：{privacy.errorCode}</p>}
          </section>

          <section className="panel-block outfit-card">
            <div className="block-heading">
              <h2>今日建议</h2>
              <span className="quiet-label">{facts.outfit.scene}</span>
            </div>
            <p className="suggestion-state">{facts.outfit.status === "ready" ? "已从确认库存生成" : "当前无法生成"}</p>
            <ul>
              {facts.outfit.candidates.map((candidate) => <li key={candidate}>{candidate}</li>)}
            </ul>
          </section>

          <section className="panel-block evidence-card">
            <div className="block-heading"><h2>空间证据</h2><span className="quiet-label">{providerPresentation({ status: facts.sourceStatus, label: "", errorCode: null })} · {facts.factsFreshness === "fresh" ? "事实有效" : "事实未知"}</span></div>
            {facts.rooms.map((room) => (
              <div className="evidence-row" key={room.id}>
                <span>{room.name}</span><span className={`evidence-tag ${room.evidence}`}>{room.evidence === "confirmed" ? "已确认" : room.evidence === "inferred" ? "推断" : "未知"}</span>
              </div>
            ))}
            <button className="action-button" disabled={refreshState.status === "loading"} onClick={() => {
              const loading = startRefresh(refreshState);
              setRefreshState(loading);
              try {
                setFacts(refreshDemoScenario(scenario));
                setRefreshState(finishRefresh(loading, true));
              } catch {
                setRefreshState(finishRefresh(loading, false));
              }
            }}>{refreshState.status === "loading" ? "正在读取" : "重新读取合成事实"}</button>
            {refreshState.status === "succeeded" && <p className="refresh-copy">本地合成事实已重新读取</p>}
            {refreshState.status === "failed" && <p className="error-copy">错误码：{refreshState.errorCode}</p>}
          </section>
        </aside>
      </section>
    </main>
  );
}
