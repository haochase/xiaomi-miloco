import type { DemoRoom } from "./demoSchema";

export function scenePresentation(rooms: DemoRoom[], peopleCount: number | null) {
  return {
    mode: rooms.length > 0 && peopleCount !== null &&
      rooms.every((room) => room.width !== null && room.depth !== null && room.evidence === "confirmed")
      ? "floorplan" as const
      : "list" as const,
    peopleLabel: peopleCount === null ? "活动人数未知" : `${peopleCount} 位匿名活动者`,
  };
}
