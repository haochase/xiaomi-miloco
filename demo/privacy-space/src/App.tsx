import { useState } from "react";
import type { DemoState } from "./demoSchema";
import { SceneCanvas } from "./SceneCanvas";

export function App({ state }: { state: DemoState }) {
  const [privacy, setPrivacy] = useState(state.privacy);
  const replaySyntheticPrivacyResult = () => {
    const next = { ...privacy, status: "processed" as const, temporaryFrameCleared: true, errorCode: null };
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
        <SceneCanvas rooms={state.rooms} devices={state.devices} peopleCount={state.peopleCount} />

        <aside className="side-panel">
          <section className="panel-block privacy-card">
            <div className="block-heading">
              <h2>隐私处理</h2>
              <span className="quiet-label">单帧演示</span>
            </div>
            <p className="large-status">{privacy.temporaryFrameCleared ? "临时帧已清理" : privacy.status === "failed" ? "临时帧清理失败" : "等待处理"}</p>
            <div className="metric-row">
              <span>处理帧数</span><strong>{state.privacy.frameCount}</strong>
            </div>
            <div className="metric-row">
              <span>展示内容</span><strong>结构化摘要</strong>
            </div>
            {privacy.status !== "processed" && <button className="action-button" onClick={replaySyntheticPrivacyResult}>回放合成处理结果</button>}
            {privacy.errorCode && <p className="error-copy">错误码：{privacy.errorCode}</p>}
          </section>

          <section className="panel-block outfit-card">
            <div className="block-heading">
              <h2>今日建议</h2>
              <span className="quiet-label">{state.outfit.scene}</span>
            </div>
            <p className="suggestion-state">{state.outfit.status === "ready" ? "已从确认库存生成" : "当前无法生成"}</p>
            <ul>
              {state.outfit.candidates.map((candidate) => <li key={candidate}>{candidate}</li>)}
            </ul>
          </section>

          <section className="panel-block evidence-card">
            <div className="block-heading"><h2>空间证据</h2><span className="quiet-label">可校正</span></div>
            {state.rooms.map((room) => (
              <div className="evidence-row" key={room.id}>
                <span>{room.name}</span><span className={`evidence-tag ${room.evidence}`}>{room.evidence === "confirmed" ? "已确认" : "推断"}</span>
              </div>
            ))}
          </section>
        </aside>
      </section>
    </main>
  );
}
