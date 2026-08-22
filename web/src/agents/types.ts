import type { ComponentType, ReactNode, SVGProps } from "react";

export type AgentIcon = ComponentType<
  SVGProps<SVGSVGElement> & { active?: boolean }
>;

export interface AgentPanelContribution {
  readonly id: string;
  readonly capabilityId: string;
  readonly labelKey: string;
  readonly Icon: AgentIcon;
  readonly order: number;
  readonly render: () => ReactNode;
}
