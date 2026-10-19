import type { DemoDevice, DemoRoom } from "./demoSchema";

export function SceneCanvas({
  rooms,
  devices,
  peopleCount,
}: {
  rooms: DemoRoom[];
  devices: DemoDevice[];
  peopleCount: number;
}) {
  return (
    <section className="scene-card" aria-label="家庭空间结构化视图">
      <div className="scene-toolbar"><span>结构化空间视图</span><span>{peopleCount} 位匿名活动者</span></div>
      <div className="floorplan">
        {rooms.map((room, index) => (
          <div className={`room room-${index + 1}`} key={room.id}>
            <span className="room-name">{room.name}</span>
            <span className="room-size">{room.width} × {room.depth} m · {room.evidence === "confirmed" ? "已确认" : "有依据推断"}</span>
            <div className="furniture sofa" />
            <div className="furniture table" />
          </div>
        ))}
        <div className="person-marker" aria-label="匿名人物">●</div>
      </div>
      <div className="device-strip">
        {devices.map((device) => <span className={`device-chip ${device.online ? "online" : "offline"}`} key={device.type}>{device.label}</span>)}
      </div>
    </section>
  );
}
