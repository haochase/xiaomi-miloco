import type { ComponentType, ReactNode, SVGProps } from "react";

export type AgentPanelIcon = ComponentType<
  SVGProps<SVGSVGElement> & { active?: boolean }
>;

export interface AgentPanelRenderContext {
  agentId: string;
  momentId?: string;
}

export interface AgentPanelContribution {
  id: string;
  labelKey: string;
  hintKey: string;
  capabilityId: string;
  Icon: AgentPanelIcon;
  render: (context: AgentPanelRenderContext) => ReactNode;
}
