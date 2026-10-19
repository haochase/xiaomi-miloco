import type { DemoDevice, DemoRoom } from "./demoSchema";
import { scenePresentation } from "./scenePresentation";

export function SceneCanvas({
  rooms,
  devices,
  peopleCount,
}: {
  rooms: DemoRoom[];
  devices: DemoDevice[];
  peopleCount: number | null;
}) {
  const presentation = scenePresentation(rooms, peopleCount);
  return (
    <section className="scene-card" aria-label="家庭空间结构化视图">
      <div className="scene-toolbar"><span>结构化空间视图</span><span>{presentation.peopleLabel}</span></div>
      {presentation.mode === "list" ? (
        <div className="room-list">
          {rooms.length === 0 ? "房间信息未提供" : rooms.map((room) => (
            <div className="room-list-item" key={room.id}><strong>{room.name}</strong><span>{room.width === null || room.depth === null ? "空间尺寸未知" : `${room.width} × ${room.depth} m`} · {room.evidence === "confirmed" ? "已确认" : room.evidence === "inferred" ? "有依据推断" : "未确认"}</span></div>
          ))}
        </div>
      ) : <div className="floorplan">
        {rooms.map((room, index) => (
          <div className={`room room-${index + 1}`} key={room.id}>
            <span className="room-name">{room.name}</span>
            <span className="room-size">{room.width === null || room.depth === null ? "空间尺寸未知" : `${room.width} × ${room.depth} m`} · {room.evidence === "confirmed" ? "已确认" : room.evidence === "inferred" ? "有依据推断" : "未知"}</span>
            {room.width !== null && room.depth !== null && <div className="furniture sofa" />}
            {room.width !== null && room.depth !== null && <div className="furniture table" />}
          </div>
        ))}
        {peopleCount !== null && peopleCount > 0 && <div className="person-marker" aria-label="匿名人物">●</div>}
      </div>}
      <div className="device-strip">
        {devices.map((device) => <span className={`device-chip ${device.online ? "online" : "offline"}`} key={device.type}>{device.label}</span>)}
      </div>
    </section>
  );
}
